"""Job runner: one job at a time on one worker thread, progress and results in SQLite/JSON, cancellation.

Long work never runs on the event loop: requests only put a job in the queue; the worker thread runs the engine.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import queue
import threading
from concurrent.futures import Executor
from typing import Any

import core
from core.engine import K_LADDER

from server import units
from server.finalize import finalize_candidates, rounds_info, sanitize
from server.schemas import DesignRequest
from server.store import FINISHED, count_active, get_job, save_results, set_message_if_running, update_job_status

MATERIALS_DB = units.MATERIALS
build_spec = units.to_search_spec
is_infeasible = units.is_infeasible
K_LADDER = list(K_LADDER)
MAX_QUEUE = int(os.environ.get("MAX_QUEUE", "10"))


# ---------------------------------------------------------------------------
# Candidate helpers
# ---------------------------------------------------------------------------

def hash_lattice_edges(edges: list[list[int]] | list[tuple[int, int]]) -> str:
    """Canonical hash of undirected lattice edges."""
    canonical_edges = tuple(sorted({(min(e[0], e[1]), max(e[0], e[1])) for e in edges if len(e) >= 2}))
    return hashlib.sha256(str(canonical_edges).encode("utf-8")).hexdigest()


def drop_geometric_duplicates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the first of each distinct (edge set, relative density). Kept for callers that only have edges."""
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


def dedupe_designs(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the first of each distinct design. The engine's id hashes the adjacency AND the node positions, so two
    lattices with the same edge list but different geometry stay apart; the same lattice at two densities too."""
    seen: set[tuple[str, float]] = set()
    out = []
    for c in candidates:
        key = (c["id"], round(float(c.get("rel_density", 0.0)), 5))
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def rank_candidates(candidates: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """Matches first, then lowest error; each distinct design once."""
    ordered = sorted(candidates, key=lambda c: (not c.get("matches_targets", False), c.get("match_error_pct", 1e9)))
    top = dedupe_designs(ordered)[:n]
    for i, cand in enumerate(top, start=1):
        cand["rank"] = i
    return top


# ---------------------------------------------------------------------------
# One job, start to finish (runs on the worker thread)
# ---------------------------------------------------------------------------

def run_job_sync(job_id: str, request: DesignRequest, *, k_values: list[int] | None = None,
                 should_stop: Any = None) -> None:
    stop = should_stop or (lambda: False)
    rounds_acc: list[dict[str, Any]] = []

    def on_progress(ev: dict[str, Any]) -> None:
        meta: dict[str, Any] = {}
        if ev.get("round") is not None:
            meta["round"], meta["k"] = ev["round"], ev.get("k")
        if ev.get("row"):
            rounds_acc.append(ev["row"])
            meta["rounds"] = rounds_info(rounds_acc)
        update_job_status(job_id, status="running", stage=ev.get("stage"), progress=ev.get("progress"),
                          message=ev.get("message"), meta=sanitize(meta) or None)

    try:
        material = units.MATERIALS.get(request.material.lower())
        if material is None:
            raise ValueError(f"unknown material '{request.material}'")
        update_job_status(job_id, status="running", stage="search", progress=0.02, message="Loading models...")
        engine = core.start_engine()
        if not engine.ok:
            raise RuntimeError(engine.status.get("reason") or "models not loaded")
        if stop():
            update_job_status(job_id, status="cancelled", message="Cancelled before the search started.")
            return

        result = engine.run(request, on_progress, stop, ladder=k_values or K_LADDER)

        update_job_status(job_id, status="running", stage="rank", progress=0.95, message="Ranking top candidates...")
        top = rank_candidates(result["candidates"], request.n_results or 5)
        top = finalize_candidates(top, job_id, request, material, list(request.part.size_mm), request.part.cell_mm)
        save_results(job_id, sanitize(top))
        meta = sanitize({"rounds": rounds_info(result["rounds"]), "infeasible": result["infeasible"],
                         "skipped_invalid": result.get("skipped_invalid", 0)})
        if result.get("skipped_invalid"):
            old = (get_job(job_id, include_candidates=False) or {}).get("warnings") or []
            meta["warnings"] = old + [f"{result['skipped_invalid']} candidate(s) skipped: the solver result was not "
                                      f"physical (not finite, or stiffer than any beam lattice can be)."]

        matched = any(c.get("matches_targets") for c in top)
        if result.get("stopped") or stop():
            status, msg = "cancelled", f"Stopped after round {len(result['rounds'])}; showing the best designs so far."
        elif not top:
            status, msg = "failed", "No valid lattice found for this target (no_valid_design)."
            meta["failure_reason"] = "no_valid_design"
        elif result.get("fallback") == "nearest_stored":
            status, msg = "done", ("The search found no valid design; showing the nearest stored lattices "
                                   "(solver-verified, not generated for this request).")
        elif matched:
            status, msg = "done", f"Found {sum(c.get('matches_targets', False) for c in top)} design(s) meeting every target."
        elif result["infeasible"]:
            status, msg = "done", "This request cannot be met at this density; showing the closest designs found."
        else:
            status, msg = "done", f"No design meets every target; closest is off by {top[0]['match_error_pct']}%."
        update_job_status(job_id, status=status, stage="rank", progress=1.0 if status == "done" else None,
                          message=msg, meta=meta)
    except Exception as e:  # noqa: BLE001 - catch-all for the worker
        update_job_status(job_id, status="failed", message=f"Pipeline execution failed: {e!s}")


# ---------------------------------------------------------------------------
# The queue
# ---------------------------------------------------------------------------

class QueueFull(Exception):
    pass


class JobRunner:
    """One worker thread; jobs wait in a FIFO queue (their position is derived from SQLite)."""

    def __init__(self) -> None:
        self._q: queue.Queue = queue.Queue()
        self._flags: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def _ensure_thread(self) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, name="job-worker", daemon=True)
                self._thread.start()

    def submit(self, job_id: str, request: Any) -> None:
        """`request` is a DesignRequest, or any object with run(job_id, should_stop) (e.g. an implant assembly task)."""
        running, queued = count_active()
        if queued >= MAX_QUEUE:
            raise QueueFull(f"{queued} jobs are already waiting; try again in a few minutes")
        with self._lock:
            self._flags[job_id] = threading.Event()
        self._q.put((job_id, request))
        self._ensure_thread()

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        job = get_job(job_id, include_candidates=False)
        if job is None or job["status"] in FINISHED:
            return job
        with self._lock:
            flag = self._flags.get(job_id)
        if flag is not None:
            flag.set()
        if job["status"] == "queued":
            return update_job_status(job_id, status="cancelled", message="Cancelled while waiting in the queue.")
        set_message_if_running(job_id, "Stopping after the current search round...")
        return get_job(job_id, include_candidates=False)

    def _loop(self) -> None:
        while True:
            job_id, request = self._q.get()
            flag = self._flags.get(job_id) or threading.Event()
            try:
                job = get_job(job_id, include_candidates=False)
                if job is None or job["status"] != "queued" or flag.is_set():
                    continue                                   # cancelled while waiting
                if hasattr(request, "run"):
                    request.run(job_id, flag.is_set)
                else:
                    run_job_sync(job_id, request, should_stop=flag.is_set)
            except Exception as e:  # noqa: BLE001
                update_job_status(job_id, status="failed", message=f"Pipeline execution failed: {e!s}")
            finally:
                with self._lock:
                    self._flags.pop(job_id, None)


runner = JobRunner()


async def run_pipeline(
    job_id: str,
    request: DesignRequest | dict[str, Any] | None = None,
    process_pool: Executor | None = None,        # unused; kept so older callers still work
    thread_pool: Executor | None = None,
    k_values: list[int] | None = None,
    request_data: dict[str, Any] | None = None,
    stage_delay: float | None = None,
) -> None:
    """Run one job to completion off the event loop (used by tests and scripts; the API uses `runner`)."""
    payload = request if request is not None else (request_data or {})
    if isinstance(payload, dict):
        if "part" not in payload:
            payload = {**payload, "part": {"size_mm": [40.0, 40.0, 40.0], "cell_mm": 10.0}}
        request = DesignRequest(**payload)
    await asyncio.get_running_loop().run_in_executor(
        thread_pool, lambda: run_job_sync(job_id, request, k_values=k_values))


run_mock_pipeline = run_pipeline
