"""Background pipeline: adaptive search (K = 100, 300, 1000) with solver verification of every candidate."""

from __future__ import annotations

import asyncio
import hashlib
from concurrent.futures import Executor, ThreadPoolExecutor
from typing import Any

import core
from core.engine import K_LADDER

from server import units
from server.schemas import DesignRequest
from server.store import save_results, update_job_status

# Global dictionary mapping job_id to event queue for SSE streaming
active_sse_queues: dict[str, asyncio.Queue] = {}

MATERIALS_DB = units.MATERIALS
build_spec = units.to_search_spec
is_infeasible = units.is_infeasible
K_LADDER = list(K_LADDER)


def hash_lattice_edges(edges: list[list[int]] | list[tuple[int, int]]) -> str:
    """Canonical hash of undirected lattice edges, to detect geometric duplicates."""
    canonical_edges = tuple(sorted({(min(e[0], e[1]), max(e[0], e[1])) for e in edges if len(e) >= 2}))
    return hashlib.sha256(str(canonical_edges).encode("utf-8")).hexdigest()


def drop_geometric_duplicates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the first of each distinct (edge set, relative density)."""
    seen: set[tuple[str, float]] = set()
    unique: list[dict[str, Any]] = []
    for cand in candidates:
        lattice = cand.get("lattice")
        edges = lattice.get("edges", []) if isinstance(lattice, dict) else []
        key = (hash_lattice_edges(edges), round(float(cand.get("rel_density", 0.0)), 5))
        if key not in seen:
            seen.add(key)
            unique.append(cand)
    return unique


def rank_candidates(candidates: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """Matches first, then lowest error; each distinct design once."""
    ordered = sorted(candidates, key=lambda c: (not c.get("matches_targets", False), c.get("match_error_pct", 1e9)))
    top = drop_geometric_duplicates(ordered)[:n]
    for i, cand in enumerate(top, start=1):
        cand["rank"] = i
    return top


async def run_pipeline(
    job_id: str,
    request: DesignRequest | dict[str, Any] | None = None,
    process_pool: Executor | None = None,  # kept for call compatibility; the solver pool lives in the engine
    thread_pool: Executor | None = None,
    k_values: list[int] | None = None,
    request_data: dict[str, Any] | None = None,
    stage_delay: float | None = None,
) -> None:
    """Run the engine's adaptive search for one job and store the ranked, solver-verified candidates."""
    queue = active_sse_queues.setdefault(job_id, asyncio.Queue())

    req_payload = request if request is not None else (request_data or {})
    if isinstance(req_payload, dict):
        if "part" not in req_payload:
            req_payload = {**req_payload, "part": {"size_mm": [40.0, 40.0, 40.0], "cell_mm": 10.0}}
        request = DesignRequest(**req_payload)

    if thread_pool is None:
        try:
            from server.app import thread_pool as app_pool
            thread_pool = app_pool
        except (ImportError, AttributeError):
            thread_pool = ThreadPoolExecutor(max_workers=1)

    loop = asyncio.get_running_loop()

    def on_progress(ev: dict[str, Any]) -> None:           # called from the engine thread
        update_job_status(job_id=job_id, status="running", stage=ev.get("stage"), progress=ev.get("progress"),
                          message=ev.get("message"))
        loop.call_soon_threadsafe(queue.put_nowait, {k: ev[k] for k in ("stage", "progress", "message") if k in ev})

    try:
        if request.material.lower() not in units.MATERIALS:
            raise ValueError(f"unknown material '{request.material}'")
        update_job_status(job_id=job_id, status="running", stage="search", progress=0.02, message="Loading models...")
        engine = await loop.run_in_executor(thread_pool, core.start_engine)
        if not engine.ok:
            raise RuntimeError(engine.status.get("reason") or "models not loaded")

        result = await loop.run_in_executor(
            thread_pool, lambda: engine.run(request, on_progress, None, ladder=k_values or K_LADDER))

        update_job_status(job_id=job_id, status="running", stage="rank", progress=0.95, message="Ranking top candidates...")
        top = rank_candidates(result["candidates"], request.n_results or 5)
        for c in top:                      # ids are unique across jobs, so /api/designs/{id} finds exactly this design
            c["id"] = f"{job_id}_{c['id']}"
        save_results(job_id, top)

        matched = any(c.get("matches_targets") for c in top)
        if not top:
            final_msg = "No valid lattice found for this target."
        elif matched:
            final_msg = f"Found {sum(c.get('matches_targets', False) for c in top)} design(s) meeting every target."
        elif result["infeasible"]:
            final_msg = "This request cannot be met at this density; showing the closest designs found."
        else:
            final_msg = f"No design meets every target; closest is off by {top[0]['match_error_pct']}%."
        update_job_status(job_id=job_id, status="done", stage="rank", progress=1.0, message=final_msg)
        await queue.put({"status": "done", "stage": "rank", "progress": 1.0, "message": final_msg})

    except Exception as e:  # noqa: BLE001 - catch-all for background task
        err_msg = f"Pipeline execution failed: {e!s}"
        update_job_status(job_id=job_id, status="failed", message=err_msg)
        await queue.put({"status": "failed", "message": err_msg})


run_mock_pipeline = run_pipeline
