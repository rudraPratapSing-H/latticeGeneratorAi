"""Server-side finishing of engine output: ids, mass, printability notes, and one sanitize() for every response.

The engine's numbers are never changed here. Mass is added from the part volume (the engine does not know it for
stored or mock results), warnings are derived from numbers already in the candidate.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from server import units

MIN_STRUT_MM = 0.4          # common 0.4 mm nozzle reference


def sanitize(obj: Any) -> Any:
    """Plain Python types only, and no NaN / Infinity (they become null): json.dumps(..., allow_nan=False) is safe."""
    if isinstance(obj, dict):
        return {str(k): sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [sanitize(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return sanitize(obj.tolist())
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if hasattr(obj, "value") and not isinstance(obj, (str, int, float, bool)):     # Enum
        return sanitize(obj.value)
    return obj


def mass_g(rel_density: float, size_mm: list[float], material: dict[str, Any]) -> float:
    """rel_density x part volume x material density (an estimate: a finite block is a little heavier)."""
    return round(rel_density * units.calculate_volume_cm3(size_mm) * material["density_g_cm3"], 3)


def min_cell_mm(strut_radius_mm: float, cell_mm: float) -> float:
    """Smallest cell size at which the strut diameter reaches MIN_STRUT_MM (radius scales with the cell)."""
    return MIN_STRUT_MM / (2.0 * strut_radius_mm / cell_mm)


def printability_warning(lattice: dict[str, Any]) -> str | None:
    r, cell = lattice["strut_radius_mm"], lattice["cell_size_mm"]
    d = 2.0 * r
    if d >= MIN_STRUT_MM:
        return None
    return (f"Struts are {d:.2f} mm thick, below the {MIN_STRUT_MM:g} mm many printers can make. "
            f"Use a cell size of at least {min_cell_mm(r, cell):.1f} mm (now {cell:g} mm).")


def shortfall_warning(c: dict[str, Any], request: dict[str, Any] | None) -> str | None:
    """For a candidate that is not a match: say it is the closest, not a match, with its worst error."""
    if c.get("matches_targets") is not False:
        return None
    return f"Closest design, not a match: worst target is off by {c['match_error_pct']:g}%."


def finalize_candidates(cands: list[dict[str, Any]], job_id: str, request: Any, material: dict[str, Any],
                        part_mm: list[float], cell_mm: float) -> list[dict[str, Any]]:
    """Add mass_g and warnings, prefix ids with the job id (unique across jobs), apply the part's cell size."""
    out = []
    for c in cands:
        c = dict(c)
        c["id"] = c["id"] if c["id"].startswith(f"{job_id}_") else f"{job_id}_{c['id']}"
        lat = dict(c["lattice"])
        # the radius scales with the cell: stored radius is for the cell size the engine was given
        if lat.get("cell_size_mm") and abs(lat["cell_size_mm"] - cell_mm) > 1e-9:
            lat["strut_radius_mm"] = lat["strut_radius_mm"] * cell_mm / lat["cell_size_mm"]
            lat["cell_size_mm"] = cell_mm
        c["lattice"] = lat
        c["mass_g"] = mass_g(c["rel_density"], part_mm, material)
        c["mass_estimate"] = True
        stored = c.pop("origin", None) == "stored"
        c["source"] = "nearest_stored" if stored else "generated"
        w = [x for x in (printability_warning(lat), shortfall_warning(c, None)) if x]
        if stored:
            w.insert(0, "Nearest stored lattice from the dataset (the search found no valid design for this target): "
                        "solver-verified, but not made for your request." +
                        ("" if c.get("matches_targets") else " Not a match."))
        c["warnings"] = w
        out.append(c)
    return out


def predicted_governing(pred: dict[str, Any]) -> dict[str, str]:
    """Governing failure from stored predicted yield and buckling (effective strength is their minimum)."""
    return {a: ("yield" if pred["yield_strength_mpa"][a] <= pred["buckling_strength_mpa"][a] else "buckling")
            for a in "xyz"}


def rounds_info(rounds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Engine rows (best_err is a fraction, K) -> API rows (best_error_pct, k)."""
    out = []
    for r in rounds:
        err = r.get("best_err")
        out.append({"round": int(r["round"]), "k": int(r.get("K", r.get("k", 0))),
                    "best_error_pct": None if err is None or not math.isfinite(err) else round(100.0 * err, 2),
                    "matched": bool(r.get("matched")), "n_candidates": int(r.get("n_candidates", 0)),
                    "round_seconds": round(float(r.get("round_seconds", 0.0)), 2),
                    "elapsed_seconds": round(float(r.get("elapsed_seconds", 0.0)), 2)})
    return out
