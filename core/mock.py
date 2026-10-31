"""ML surrogate search and physics solver verification interface.

Implements core.search(target, k) for GPU-based surrogate candidate search,
and core.verify(lattice_states, rel_density, material) for physics verification
evaluating 3 states per candidate (unsteered, 1/3, final).
"""

from __future__ import annotations

import random
from typing import Any


def _make_lattice_topology(variant: int) -> dict[str, Any]:
    """Generate a valid lattice topology for candidate variants."""
    base_nodes = [
        [0.0, 0.0, 0.0],
        [10.0, 0.0, 0.0],
        [0.0, 10.0, 0.0],
        [10.0, 10.0, 0.0],
        [0.0, 0.0, 10.0],
        [10.0, 0.0, 10.0],
        [0.0, 10.0, 10.0],
        [10.0, 10.0, 10.0],
    ]
    # Edge configurations with geometric variations
    edge_patterns = [
        [[0, 1], [1, 3], [3, 2], [2, 0], [4, 5], [5, 7], [7, 6], [6, 4], [0, 4], [1, 5], [2, 6], [3, 7]],
        [[0, 7], [1, 6], [2, 5], [3, 4], [0, 1], [2, 3], [4, 5], [6, 7]],
        [[0, 3], [1, 2], [4, 7], [5, 6], [0, 5], [1, 4], [2, 7], [3, 6]],
        [[0, 1], [1, 2], [2, 3], [3, 0], [0, 6], [1, 7], [2, 4], [3, 5]],
        [[0, 2], [2, 4], [4, 6], [6, 0], [1, 3], [3, 5], [5, 7], [7, 1]],
    ]
    edges = edge_patterns[variant % len(edge_patterns)]
    return {
        "format": "octant27",
        "nodes": base_nodes,
        "edges": edges,
        "cell_size_mm": 10.0,
        "strut_radius_mm": round(0.35 + (variant % 10) * 0.02, 2),
    }


def search(target: dict[str, Any], k: int) -> list[dict[str, Any]]:
    """Simulate PyTorch GPU surrogate model search producing k candidates.

    Each candidate contains 3 states: unsteered, 1/3, and final.
    """
    candidates = []
    # Seed determination for reproducibility per k
    rnd = random.Random(k + 42)

    for i in range(k):
        cand_id = f"cand_{k}_{i:04d}"
        rel_density = round(rnd.uniform(0.08, 0.35), 3)
        mass_g = round(rel_density * 64.0 * 4.43, 1)  # standard volume 64cm3, Ti64 density

        # 3 states per candidate: unsteered, 1/3, final
        states = {
            "unsteered": {
                "state_name": "unsteered",
                "lattice": _make_lattice_topology(i),
                "predicted": {
                    "stiffness_gpa": {
                        "x": round(rnd.uniform(6.0, 14.0), 2),
                        "y": round(rnd.uniform(6.0, 14.0), 2),
                        "z": round(rnd.uniform(8.0, 16.0), 2),
                    },
                    "yield_strength_mpa": {
                        "x": round(rnd.uniform(70.0, 130.0), 1),
                        "y": round(rnd.uniform(70.0, 130.0), 1),
                        "z": round(rnd.uniform(90.0, 150.0), 1),
                    },
                    "buckling_strength_mpa": {
                        "x": round(rnd.uniform(80.0, 140.0), 1),
                        "y": round(rnd.uniform(80.0, 140.0), 1),
                        "z": round(rnd.uniform(100.0, 160.0), 1),
                    },
                    "strength_mpa": {
                        "x": round(rnd.uniform(70.0, 130.0), 1),
                        "y": round(rnd.uniform(70.0, 130.0), 1),
                        "z": round(rnd.uniform(90.0, 150.0), 1),
                    },
                    "governing_failure": {"x": "yield", "y": "yield", "z": "yield"},
                },
            },
            "one_third": {
                "state_name": "one_third",
                "lattice": _make_lattice_topology(i + 1),
                "predicted": {
                    "stiffness_gpa": {
                        "x": round(rnd.uniform(7.0, 11.0), 2),
                        "y": round(rnd.uniform(7.0, 11.0), 2),
                        "z": round(rnd.uniform(10.0, 14.0), 2),
                    },
                    "yield_strength_mpa": {
                        "x": round(rnd.uniform(80.0, 110.0), 1),
                        "y": round(rnd.uniform(80.0, 110.0), 1),
                        "z": round(rnd.uniform(100.0, 130.0), 1),
                    },
                    "buckling_strength_mpa": {
                        "x": round(rnd.uniform(90.0, 120.0), 1),
                        "y": round(rnd.uniform(90.0, 120.0), 1),
                        "z": round(rnd.uniform(110.0, 140.0), 1),
                    },
                    "strength_mpa": {
                        "x": round(rnd.uniform(80.0, 110.0), 1),
                        "y": round(rnd.uniform(80.0, 110.0), 1),
                        "z": round(rnd.uniform(100.0, 130.0), 1),
                    },
                    "governing_failure": {"x": "yield", "y": "yield", "z": "yield"},
                },
            },
            "final": {
                "state_name": "final",
                "lattice": _make_lattice_topology(i + 2),
                "predicted": {
                    "stiffness_gpa": {
                        "x": round(rnd.uniform(7.5, 9.5), 2),
                        "y": round(rnd.uniform(7.5, 9.5), 2),
                        "z": round(rnd.uniform(11.0, 13.0), 2),
                    },
                    "yield_strength_mpa": {
                        "x": round(rnd.uniform(85.0, 100.0), 1),
                        "y": round(rnd.uniform(85.0, 100.0), 1),
                        "z": round(rnd.uniform(105.0, 125.0), 1),
                    },
                    "buckling_strength_mpa": {
                        "x": round(rnd.uniform(95.0, 115.0), 1),
                        "y": round(rnd.uniform(95.0, 115.0), 1),
                        "z": round(rnd.uniform(115.0, 135.0), 1),
                    },
                    "strength_mpa": {
                        "x": round(rnd.uniform(85.0, 100.0), 1),
                        "y": round(rnd.uniform(85.0, 100.0), 1),
                        "z": round(rnd.uniform(105.0, 125.0), 1),
                    },
                    "governing_failure": {"x": "yield", "y": "yield", "z": "yield"},
                },
            },
        }

        candidates.append({
            "id": cand_id,
            "rel_density": rel_density,
            "mass_g": mass_g,
            "lattice_states": states,
        })

    return candidates


def verify(
    lattice_states: dict[str, Any] | list[dict[str, Any]],
    rel_density: float,
    material: dict[str, Any],
    target: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Physics solver evaluating 3 states per candidate (unsteered, 1/3, final).

    Returns evaluated list of states, each with verified properties and match error.
    """
    if isinstance(lattice_states, dict):
        states_list = list(lattice_states.values())
    else:
        states_list = lattice_states

    # Material properties
    E_mat = float(material.get("E_gpa", 114.0))
    sig_mat = float(material.get("yield_mpa", 880.0))

    evaluated_states = []
    for state_idx, state in enumerate(states_list):
        # Physics approximation based on relative density with state steering refinement
        state_modifier = 1.0 + (state_idx * 0.05)
        # Gibson-Ashby scaling: E* ~ E_s * (rho*)^2
        eff_E = E_mat * (rel_density ** 1.8) * state_modifier
        eff_yield = sig_mat * (rel_density ** 1.5) * state_modifier
        eff_buckle = eff_yield * 1.15

        verified_props = {
            "stiffness_gpa": {
                "x": round(eff_E * 0.95, 2),
                "y": round(eff_E * 0.95, 2),
                "z": round(eff_E * 1.25, 2),
            },
            "yield_strength_mpa": {
                "x": round(eff_yield * 0.95, 1),
                "y": round(eff_yield * 0.95, 1),
                "z": round(eff_yield * 1.15, 1),
            },
            "buckling_strength_mpa": {
                "x": round(eff_buckle * 0.95, 1),
                "y": round(eff_buckle * 0.95, 1),
                "z": round(eff_buckle * 1.15, 1),
            },
            "strength_mpa": {
                "x": round(eff_yield * 0.95, 1),
                "y": round(eff_yield * 0.95, 1),
                "z": round(eff_yield * 1.15, 1),
            },
            "governing_failure": {"x": "yield", "y": "yield", "z": "yield"},
        }

        # Calculate error percentage against target
        match_error_pct = _calculate_match_error(verified_props, target, state_idx)

        evaluated_states.append({
            "state_name": state.get("state_name", str(state_idx)),
            "lattice": state.get("lattice"),
            "predicted": state.get("predicted"),
            "verified": verified_props,
            "match_error_pct": match_error_pct,
        })

    return evaluated_states


def _calculate_match_error(
    verified: dict[str, Any],
    target: dict[str, Any] | None,
    state_idx: int,
) -> float:
    """Calculate match error percentage against design target."""
    if not target:
        # Default stepped error: final has lower error than unsteered
        return round(max(1.0, 12.0 - (state_idx * 4.0)), 2)

    errors = []
    stiff_target = target.get("stiffness_gpa")
    if stiff_target:
        stiff_val = verified["stiffness_gpa"]
        for axis in ("x", "y", "z"):
            t_val = stiff_target.get(axis) if isinstance(stiff_target, dict) else getattr(stiff_target, axis, None)
            if t_val is not None and t_val > 0:
                errors.append(abs(stiff_val[axis] - t_val) / t_val * 100.0)

    strength_target = target.get("strength_mpa")
    if strength_target:
        strength_val = verified["strength_mpa"]
        for axis in ("x", "y", "z"):
            t_val = strength_target.get(axis) if isinstance(strength_target, dict) else getattr(strength_target, axis, None)
            if t_val is not None and t_val > 0:
                errors.append(abs(strength_val[axis] - t_val) / t_val * 100.0)

    if errors:
        # Penalize earlier unsteered states slightly to reflect refinement
        return round(float(sum(errors) / len(errors)) * (1.2 - state_idx * 0.15), 2)

    return round(max(1.0, 10.0 - (state_idx * 3.5)), 2)


# ---------------------------------------------------------------------------
# Same interface as core.engine (used when MOCK=1 and in tests). Replaced by real-output replay in T4.
# ---------------------------------------------------------------------------

def search_round(spec: dict[str, Any], K: int, cache: dict | None = None) -> list[dict[str, Any]]:
    """Canned round: search K fake candidates, verify their 3 states, keep the best state of each."""
    target = {"stiffness_gpa": _axes(spec.get("stiffness_gpa")), "strength_mpa": _axes(spec.get("strength_mpa"))}
    mat = spec["material"]
    out = []
    for cand in search(target, K):
        states = verify(cand["lattice_states"], cand["rel_density"], mat, target)
        best = min(states, key=lambda s: s["match_error_pct"])
        out.append({
            "id": cand["id"], "rank": 0, "match_error_pct": best["match_error_pct"],
            "matches_targets": best["match_error_pct"] <= spec["tol"] * 100.0,
            "rel_density": cand["rel_density"], "mass_g": cand["mass_g"], "lattice": best["lattice"],
            "predicted": best["predicted"], "verified": best["verified"],
        })
    out.sort(key=lambda c: c["match_error_pct"])
    return out


def _axes(v: Any) -> dict[str, float | None] | None:
    return None if v is None else dict(zip("xyz", v))


class MockEngine:
    status = {"ok": True, "reason": None, "device": "mock", "workers": 0}
    ok = True

    def health(self) -> dict[str, Any]:
        return {"model_loaded": False, "gpu": False, "solver_workers": 0, "reason": "mock mode"}

    def run(self, request: Any, on_progress=None, should_stop=None, *, ladder=(100, 300, 1000),
            time_budget_s=None, request_echo=None) -> dict[str, Any]:
        from server import units
        emit = on_progress or (lambda _e: None)
        spec = request if isinstance(request, dict) else units.to_search_spec(request, units.MATERIALS[request.material.lower()])
        infeasible = units.is_infeasible(spec)
        rungs = list(ladder)[:1] if infeasible else list(ladder)
        history, found = [], []
        for r, k in enumerate(rungs, 1):
            if should_stop and should_stop():
                break
            emit({"stage": "search", "round": r, "k": k, "progress": round(0.9 * (r - 1) / len(rungs) + 0.02, 3),
                  "message": f"Round {r} of up to {len(rungs)}: searching {k} starting lattices"})
            cands = search_round(spec, k)
            emit({"stage": "repair", "round": r, "k": k, "progress": round(0.9 * (r - 0.5) / len(rungs), 3),
                  "message": f"Round {r}: merged duplicates, {len(cands)} distinct lattices"})
            found = cands if not found or cands[0]["match_error_pct"] < found[0]["match_error_pct"] else found
            row = dict(round=r, K=k, best_err=cands[0]["match_error_pct"] / 100.0, matched=bool(cands[0]["matches_targets"]),
                       n_candidates=len(cands), round_seconds=0.0, elapsed_seconds=0.0)
            history.append(row)
            emit({"stage": "verify", "round": r, "k": k, "row": row,
                  "progress": round(0.9 * r / len(rungs), 3), "message": f"Round {r} done"})
            if row["matched"]:
                break
            if r < len(rungs):
                emit({"stage": "search", "round": r, "k": rungs[r], "progress": round(0.9 * r / len(rungs), 3),
                      "message": f"No design meets every target. Escalating to {rungs[r]} candidates..."})
        return {"material": spec["material"], "rounds": history, "infeasible": infeasible,
                "candidates": found, "request": request_echo, "stopped": bool(should_stop and should_stop())}
