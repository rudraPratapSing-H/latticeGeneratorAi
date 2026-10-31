"""Background pipeline: adaptive search (K = 100, 300, 1000) with solver verification of every candidate."""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from concurrent.futures import Executor, ThreadPoolExecutor
from typing import Any

import core

try:
    from server.schemas import DesignRequest
    from server.store import save_results, update_job_status
    from server.units import calculate_volume_cm3, mass_to_relative_density
except ImportError:
    from schemas import DesignRequest
    from store import save_results, update_job_status
    from units import calculate_volume_cm3, mass_to_relative_density

# Global dictionary mapping job_id to event queue for SSE streaming
active_sse_queues: dict[str, asyncio.Queue] = {}

MATERIALS_DB: dict[str, dict[str, Any]] = {
    "ti64": {"id": "ti64", "name": "Ti-6Al-4V", "E_gpa": 114.0, "yield_mpa": 880.0, "density_g_cm3": 4.43},
}

K_LADDER = [100, 300, 1000]
TIME_BUDGET_S = float(os.environ.get("TIME_BUDGET_S", "120"))
RHO_MIN, RHO_MAX = 0.05, 0.25      # relative densities the predictor was trained on


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


def _axes(v: Any) -> list[float | None] | None:
    """AxisValues -> [x, y, z] (None for ignored axes), or None when every axis is ignored."""
    if v is None:
        return None
    vals = [getattr(v, a) for a in "xyz"] if not isinstance(v, dict) else [v.get(a) for a in "xyz"]
    return None if all(x is None for x in vals) else vals


def build_spec(request: DesignRequest, material: dict[str, Any]) -> dict[str, Any]:
    """Physical request -> the plain dict core.search_round takes (weight becomes a relative density)."""
    t = request.target
    mode = lambda m: getattr(m, "value", m)  # noqa: E731
    weight_mode = mode(request.modes.weight)
    vol = calculate_volume_cm3(request.part.size_mm)
    rho_lim = t.rel_density
    if rho_lim is None:
        rho_lim = mass_to_relative_density(t.max_mass_g, vol, material["density_g_cm3"])
    rho = rho_max = None
    if rho_lim is not None:
        if weight_mode == "about":
            rho = rho_lim
        else:
            rho_max = rho_lim
    return {
        "material": material,
        "stiffness_gpa": _axes(t.stiffness_gpa),
        "strength_mpa": None if t.yield_strength_mpa else _axes(t.strength_mpa),
        "yield_strength_mpa": _axes(t.yield_strength_mpa),
        "rho": rho,
        "rho_max": rho_max,
        "modes": {"stiffness": mode(request.modes.stiffness), "strength": mode(request.modes.strength),
                  "weight": weight_mode},
        "tol": request.tolerance_pct / 100.0,
        "cell_mm": request.part.cell_mm,
        "part_mm": list(request.part.size_mm),
    }


def is_infeasible(spec: dict[str, Any]) -> bool:
    """The three stiffness targets cannot add up to more than density x E (a plain cubic lattice sits exactly on it)."""
    stiff = spec.get("stiffness_gpa")
    rho_top = spec["rho"] if spec["rho"] is not None else (spec["rho_max"] or RHO_MAX)
    return bool(stiff and None not in stiff and sum(stiff) > 1.05 * rho_top * spec["material"]["E_gpa"])


def rank_candidates(candidates: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """Matches first, then lowest error; each distinct design once."""
    ordered = sorted(candidates, key=lambda c: (not c.get("matches_targets", False), c.get("match_error_pct", 1e9)))
    top = drop_geometric_duplicates(ordered)[:n]
    for i, cand in enumerate(top, start=1):
        cand["rank"] = i
    return top


async def _emit(job_id: str, stage: str, progress: float, message: str, **extra: Any) -> None:
    update_job_status(job_id=job_id, status=extra.get("status", "running"), stage=stage, progress=progress,
                      message=message)
    await active_sse_queues[job_id].put({"stage": stage, "progress": progress, "message": message, **extra})


async def run_pipeline(
    job_id: str,
    request: DesignRequest | dict[str, Any] | None = None,
    process_pool: Executor | None = None,  # kept for call compatibility; the solver runs inside the search thread
    thread_pool: Executor | None = None,
    k_values: list[int] | None = None,
    request_data: dict[str, Any] | None = None,
    stage_delay: float | None = None,
) -> None:
    """Round r searches K starting points, solver-verifies the unsteered, early and steered lattices of each,
    and stops as soon as a design meets every target; otherwise escalates to the next K."""
    active_sse_queues.setdefault(job_id, asyncio.Queue())

    req_payload = request if request is not None else (request_data or {})
    if isinstance(req_payload, dict):
        if "part" not in req_payload:
            req_payload = {**req_payload, "part": {"size_mm": [40.0, 40.0, 40.0], "cell_mm": 10.0}}
        request = DesignRequest(**req_payload)

    k_values = list(k_values or K_LADDER)
    if thread_pool is None:
        try:
            from server.app import thread_pool as app_pool
            thread_pool = app_pool
        except (ImportError, AttributeError):
            thread_pool = ThreadPoolExecutor(max_workers=1)

    loop = asyncio.get_running_loop()
    material = MATERIALS_DB.get(request.material.lower())

    try:
        if material is None:
            raise ValueError(f"unknown material '{request.material}'")
        spec = build_spec(request, material)
        if spec["stiffness_gpa"] is None and spec["strength_mpa"] is None and spec["yield_strength_mpa"] is None:
            raise ValueError("give at least one stiffness or strength target")

        infeasible = is_infeasible(spec)
        if infeasible:
            k_values = k_values[:1]
        await _emit(job_id, "search", 0.02, "Loading models...")
        await loop.run_in_executor(thread_pool, core.load_models)

        cache: dict = {}
        found: list[dict[str, Any]] = []
        matched = False
        t_start = time.time()
        n_rounds = len(k_values)
        for r, k in enumerate(k_values):
            base = 0.9 * r / n_rounds
            span = 0.9 / n_rounds
            await _emit(job_id, "search", round(base + 0.1 * span, 3),
                        f"Round {r + 1}/{n_rounds}: steering {k} starting lattices...")
            t_round = time.time()
            round_cands = await loop.run_in_executor(thread_pool, core.search_round, spec, k, cache)
            await _emit(job_id, "repair", round(base + 0.5 * span, 3),
                        f"Decoded and merged duplicates: {len(round_cands)} distinct lattices")
            await _emit(job_id, "verify", round(base + 0.9 * span, 3),
                        f"Solver verified {len(round_cands)} lattices (unsteered, early, final)")
            found = drop_geometric_duplicates(found + round_cands)
            if any(c.get("matches_targets") for c in round_cands):
                matched = True
                break
            if r + 1 < n_rounds:
                projected = (time.time() - t_start) + (time.time() - t_round) / k * k_values[r + 1]
                if projected > TIME_BUDGET_S:
                    await _emit(job_id, "search", round(base + span, 3), "Time budget reached; stopping escalation")
                    break
                await _emit(job_id, "search", round(base + span, 3),
                            f"No design meets every target. Escalating to {k_values[r + 1]} candidates...")

        await _emit(job_id, "rank", 0.95, "Ranking top candidates...")
        top = rank_candidates(found, request.n_results or 5)
        for c in top:                      # ids are unique across jobs, so /api/designs/{id} finds exactly this design
            c["id"] = f"{job_id}_{c['id']}"
        save_results(job_id, top)

        if not top:
            final_msg = "No valid lattice found for this target."
        elif matched:
            final_msg = f"Found {sum(c.get('matches_targets', False) for c in top)} design(s) meeting every target."
        elif infeasible:
            final_msg = "This request cannot be met at this density; showing the closest designs found."
        else:
            final_msg = f"No design meets every target; closest is off by {top[0]['match_error_pct']}%."
        update_job_status(job_id=job_id, status="done", stage="rank", progress=1.0, message=final_msg)
        await active_sse_queues[job_id].put({"status": "done", "stage": "rank", "progress": 1.0, "message": final_msg})

    except Exception as e:  # noqa: BLE001 - catch-all for background task
        err_msg = f"Pipeline execution failed: {e!s}"
        update_job_status(job_id=job_id, status="failed", message=err_msg)
        await active_sse_queues[job_id].put({"status": "failed", "message": err_msg})


run_mock_pipeline = run_pipeline
