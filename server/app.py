from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import AsyncGenerator
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from sse_starlette.sse import EventSourceResponse

import core

try:
    from server.jobs import QueueFull, runner
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
    from server import demo, preflight
    from server.design_service import submit_design
    from server.finalize import sanitize
    from server.picker import BadTarget, material_or_raise, plausibility, reach_for_request
    from server.store import (
        DEFAULT_RUNS_DIR,
        create_job,
        fail_stale_jobs,
        find_by_cache_key,
        get_job,
        init_db,
        save_request,
        update_job_status,
    )
except ImportError:
    from jobs import QueueFull, runner
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
    import preflight
    from finalize import sanitize
    from picker import BadTarget, material_or_raise, plausibility, reach_for_request
    from store import (
        DEFAULT_RUNS_DIR,
        create_job,
        fail_stale_jobs,
        get_job,
        init_db,
        save_request,
        update_job_status,
    )

SSE_PING_S = float(os.environ.get("SSE_PING_S", "15"))     # heartbeat so proxies do not drop an idle stream


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Create the job table, fail jobs a previous process left unfinished, warm up the engine in the background."""
    init_db()
    fail_stale_jobs()
    demo.install()                                  # stored demo targets, so the demo works without the GPU
    threading.Thread(target=core.start_engine, name="engine-warmup", daemon=True).start()
    yield
    core.shutdown()


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
    return JSONResponse(status_code=422, content=_error_body(exc.code, exc.message, field=exc.field, **exc.extra))


from server.implants import router as implants_router  # noqa: E402

app.include_router(implants_router)

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
        return sanitize(reach.get_table().limits(m))
    except reach.ReachUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/api/reach", response_model=ReachResponse)
async def post_reach(payload: ReachRequest) -> dict:
    """Level (covered / extended / outside / infeasible), distance and the nearest achievable target."""
    from core import reach
    m = material_or_raise(payload.material)
    plausibility(payload, m)
    try:
        return sanitize(await asyncio.get_running_loop().run_in_executor(None, reach_for_request, payload, m))
    except reach.ReachUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post(
    "/api/designs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobCreateResponse,
)
async def create_design(payload: DesignRequest) -> dict[str, str]:
    """Check the request against the dataset, reuse an identical earlier job, otherwise queue it. Returns 202."""
    try:
        return await asyncio.get_running_loop().run_in_executor(None, submit_design, payload)      # BadTarget -> 422
    except QueueFull as e:
        raise HTTPException(status_code=429, detail=str(e), headers={"Retry-After": "60"})


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
async def get_job_endpoint(job_id: str) -> JobResponse:
    """Query current status, stage, progress, and results of a design job from SQLite."""
    job_data = get_job(job_id)
    if not job_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )
    return JobResponse(**sanitize(job_data))


@app.post("/api/jobs/{job_id}/cancel")
@app.delete("/api/jobs/{job_id}")
async def cancel_job(job_id: str) -> dict:
    """Stop a job: a queued job is cancelled at once, a running one after its current search round."""
    job = runner.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found")
    return {"job_id": job_id, "status": job["status"], "message": job["message"]}


@app.get("/api/jobs/{job_id}/events")
async def get_job_events(job_id: str) -> EventSourceResponse:
    """Server-Sent Events: one event whenever the job's state changes, a comment ping every SSE_PING_S seconds,
    then a final `close`. Reads the job record, so any number of listeners see the same stream. The page falls
    back to polling GET /api/jobs/{id} every 2 s if the stream drops."""
    if get_job(job_id, include_candidates=False) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found")

    async def event_generator():
        last = None
        while True:
            job = get_job(job_id, include_candidates=False)
            if job is None:
                break
            snap = {k: job.get(k) for k in ("job_id", "status", "stage", "round", "k", "progress", "message",
                                            "queue_position")}
            if snap != last:
                last = snap
                yield {"data": json.dumps(snap)}
            if job["status"] in ("done", "failed", "cancelled"):
                yield {"event": "close", "data": json.dumps(snap)}
                break
            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator(), ping=SSE_PING_S)


def _find_candidate_in_runs(design_id: str) -> Candidate | None:
    """Locate a saved candidate in runs/*/results.json (ids are unique per job)."""
    for results_file in Path(DEFAULT_RUNS_DIR).glob("*/results.json"):
        try:
            with open(results_file, encoding="utf-8") as f:
                cands = json.load(f)
            for c in cands:
                if isinstance(c, dict) and c.get("id") == design_id:
                    return Candidate(**sanitize(c))
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
