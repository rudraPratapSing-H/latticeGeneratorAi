from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import AsyncGenerator
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from sse_starlette.sse import EventSourceResponse

import core

try:
    from server.jobs import active_sse_queues, run_pipeline
    from server.schemas import (
        AxisValues,
        Candidate,
        DesignRequest,
        FailureMode,
        FailureModeAxis,
        HealthResponse,
        JobCreateResponse,
        JobResponse,
        LatticeSpec,
        Material,
        PropertyEvaluation,
        ReachRequest,
        ReachResponse,
    )
    from server.picker import BadTarget, material_or_raise, plausibility, reach_for_request
    from server.store import DEFAULT_RUNS_DIR, create_job, fail_stale_jobs, get_job, init_db, save_request
except ImportError:
    from jobs import active_sse_queues, run_pipeline
    from schemas import (
        AxisValues,
        Candidate,
        DesignRequest,
        FailureMode,
        FailureModeAxis,
        HealthResponse,
        JobCreateResponse,
        JobResponse,
        LatticeSpec,
        Material,
        PropertyEvaluation,
        ReachRequest,
        ReachResponse,
    )
    from picker import BadTarget, material_or_raise, plausibility, reach_for_request
    from store import DEFAULT_RUNS_DIR, create_job, fail_stale_jobs, get_job, init_db, save_request

# Initialize executor pools for physics solver and GPU search
WORKERS = int(os.environ.get("WORKERS", max(1, (os.cpu_count() or 2) - 1)))
process_pool = ProcessPoolExecutor(max_workers=WORKERS)
thread_pool = ThreadPoolExecutor(max_workers=1)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context initializing SQLite on startup and cleaning up pools."""
    init_db()
    fail_stale_jobs()
    asyncio.get_running_loop().run_in_executor(thread_pool, core.start_engine)   # warm up without blocking startup
    yield
    process_pool.shutdown(wait=False)
    thread_pool.shutdown(wait=False)


app = FastAPI(
    title="Lattice Design ML/Physics Engine Backend",
    description="Backend API for 3D lattice inverse design, surrogate property prediction, and physics verification.",
    version="0.1.0",
    lifespan=lifespan,
)

def _error_body(code: str, message: str, detail=None, **extra) -> dict:
    """One error shape everywhere: {"error": {"code", "message"}}. `detail` is kept for older clients."""
    return {"error": {"code": code, "message": message, **extra}, "detail": detail if detail is not None else message}


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc: RequestValidationError) -> JSONResponse:
    """422 without echoing the raw input (a NaN in the input would make the default handler crash with a 500)."""
    errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    first = errors[0] if errors else {"loc": [], "msg": "invalid request"}
    where = ".".join(str(x) for x in first["loc"] if x != "body")
    msg = f"{where}: {first['msg']}" if where else first["msg"]
    return JSONResponse(status_code=422, content=_error_body("bad_target", msg, errors))


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request, exc: StarletteHTTPException) -> JSONResponse:
    code = {404: "not_found", 409: "conflict", 429: "queue_full", 503: "unavailable"}.get(exc.status_code, "error")
    return JSONResponse(status_code=exc.status_code, content=_error_body(code, str(exc.detail)),
                        headers=getattr(exc, "headers", None))


@app.exception_handler(BadTarget)
async def bad_target_handler(request, exc: BadTarget) -> JSONResponse:
    return JSONResponse(status_code=422, content=_error_body(exc.code, exc.message, field=exc.field))


# Initialize database at module load time as well
init_db()

# CORS middleware allowing all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/health", response_model=HealthResponse)
async def get_health() -> dict:
    """Backend service health check."""
    return {"status": "ok", **core.health()}


@app.get("/api/materials", response_model=list[Material])
async def get_materials() -> list:
    """List supported materials with mechanical properties."""
    return [
        {
            "id": "ti64",
            "name": "Ti-6Al-4V",
            "E_gpa": 114,
            "yield_mpa": 880,
            "density_g_cm3": 4.43,
        }
    ]


@app.get("/api/limits")
async def get_limits(material: str = "ti64") -> dict:
    """Per-density ranges the dataset covers for this material (form hints and validation)."""
    from core import reach
    m = material_or_raise(material)
    try:
        return reach.get_table().limits(m)
    except reach.ReachUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/api/reach", response_model=ReachResponse)
async def post_reach(payload: ReachRequest) -> dict:
    """Level (covered / extended / outside / infeasible), distance and the nearest achievable target."""
    from core import reach
    m = material_or_raise(payload.material)
    plausibility(payload, m)
    try:
        return await asyncio.get_running_loop().run_in_executor(None, reach_for_request, payload, m)
    except reach.ReachUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post(
    "/api/designs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobCreateResponse,
)
async def create_design(
    payload: DesignRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """Generate a UUID, insert job into SQLite, start background simulation, and return 202."""
    job_id = f"j_{uuid.uuid4().hex[:8]}"

    save_request(job_id, payload.model_dump(mode="json"))
    create_job(
        job_id=job_id,
        status="queued",
        stage=None,
        progress=0.0,
        message="Job queued for processing",
    )

    if job_id not in active_sse_queues:
        active_sse_queues[job_id] = asyncio.Queue()

    background_tasks.add_task(run_pipeline, job_id, payload)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
async def get_job_endpoint(job_id: str) -> JobResponse:
    """Query current status, stage, progress, and results of a design job from SQLite."""
    job_data = get_job(job_id)
    if not job_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )
    return JobResponse(**job_data)


@app.get("/api/jobs/{job_id}/events")
async def get_job_events(job_id: str) -> EventSourceResponse:
    """Server-Sent Events: one event whenever the job's stage, progress or message changes, then a final `close`.

    Reads the job record, so any number of listeners (extra tabs, reconnects) see the same stream.
    """
    if get_job(job_id, include_candidates=False) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found")

    async def event_generator():
        last = None
        while True:
            job = get_job(job_id, include_candidates=False)
            if job is None:
                break
            snap = {
                "job_id": job_id,
                "status": job["status"],
                "stage": job["stage"],
                "progress": job["progress"],
                "message": job["message"],
            }
            if snap != last:
                last = snap
                yield {"data": json.dumps(snap)}
            if job["status"] in ("done", "failed"):
                yield {"event": "close", "data": json.dumps(snap)}
                break
            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())


def _find_candidate_in_runs(design_id: str) -> Candidate | None:
    """Locate a saved candidate in runs/*/results.json (ids are unique per job)."""
    for results_file in Path(DEFAULT_RUNS_DIR).glob("*/results.json"):
        try:
            with open(results_file, encoding="utf-8") as f:
                cands = json.load(f)
            for c in cands:
                if isinstance(c, dict) and c.get("id") == design_id:
                    return Candidate(**c)
        except (OSError, json.JSONDecodeError, ValueError):
            pass
    return None


@app.get("/api/designs/{design_id}", response_model=Candidate)
async def get_design(design_id: str) -> Candidate:
    """Retrieve one saved candidate (lattice geometry, predicted and verified properties)."""
    saved_cand = _find_candidate_in_runs(design_id)
    if saved_cand is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Design {design_id} not found")
    return saved_cand
