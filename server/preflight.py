"""Everything checked before a search is queued: material, plausibility, weight limit, picker level, cell fit.

Cheap (a few tens of ms) but not free, so the API runs it in a thread. Raises picker.BadTarget for requests that
cannot be run; otherwise returns the picker result and plain-language warnings. It never changes the user's numbers.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any

import core
from core import reach as reach_mod
from server import units
from server.finalize import sanitize
from server.picker import BadTarget, material_or_raise, plausibility, reach_for_request
from server.schemas import DesignRequest


@dataclass
class Preflight:
    material: dict[str, Any]
    reach: dict[str, Any] | None
    warnings: list[str] = field(default_factory=list)
    cache_key: str = ""


def canonical_request(request: DesignRequest) -> str:
    """Sorted keys, floats rounded to 6 digits: the same request always gives the same string."""
    def norm(o: Any) -> Any:
        if isinstance(o, float):
            return round(o, 6)
        if isinstance(o, dict):
            return {k: norm(v) for k, v in sorted(o.items())}
        if isinstance(o, list):
            return [norm(v) for v in o]
        return o
    return json.dumps(norm(request.model_dump(mode="json")), sort_keys=True, separators=(",", ":"))


def cache_key(request: DesignRequest) -> str:
    return hashlib.sha256((canonical_request(request) + "|" + core.model_hash()).encode("utf-8")).hexdigest()[:32]


def cell_fit_warning(request: DesignRequest) -> str | None:
    cell = request.part.cell_mm
    bad = [(a, s) for a, s in zip("xyz", request.part.size_mm) if abs(s / cell - round(s / cell)) > 1e-6]
    if not bad:
        return None
    a, s = bad[0]
    lo, hi = math.floor(s / cell), math.ceil(s / cell)
    return (f"The {a} size ({s:g} mm) is not a whole number of {cell:g} mm cells. {lo} cells ({lo * cell:g} mm) or "
            f"{hi} cells ({hi * cell:g} mm) fit; the designs themselves are not affected.")


def weight_checks(request: DesignRequest, material: dict[str, Any]) -> list[str]:
    """Mass limit that implies a density outside 0.05..0.25."""
    rho = units.weight_limit_density(request, material)
    if rho is None:
        return []
    vol = units.calculate_volume_cm3(request.part.size_mm)
    if rho < units.RHO_MIN * 0.98:
        lightest = units.RHO_MIN * vol * material["density_g_cm3"]
        raise BadTarget(
            f"The weight limit is below the lightest lattice in the data: relative density 0.05 already weighs "
            f"{lightest:.1f} g for this part. Raise the limit to at least {lightest:.1f} g.",
            field="target.max_mass_g")
    if rho > units.RHO_MAX * 1.02:
        return [f"The weight limit allows a relative density of {rho:.2f}; designs use at most 0.25, the densest the "
                f"model was trained on."]
    return []


def run(request: DesignRequest) -> Preflight:
    material = material_or_raise(request.material)
    plausibility(request, material)
    warnings = weight_checks(request, material)
    w = cell_fit_warning(request)
    if w:
        warnings.append(w)

    res: dict[str, Any] | None = None
    try:
        res = reach_for_request(request, material)
    except reach_mod.ReachUnavailable as e:
        warnings.append(f"The dataset check is unavailable ({e}); the search still runs.")
    if res is not None:
        warnings += list(res.get("warnings", []))
        if res["level"] == "infeasible" and not request.force:
            n = res["nearest"]
            raise BadTarget(
                f"{res['message']} Nearest achievable target at relative density {res['density']:g}: stiffness "
                f"{n['stiffness_gpa']} GPa, strength {n['strength_mpa']} MPa. Send force: true to search anyway.",
                field="target", extra={"reach": sanitize(res)})
        if res["level"] == "infeasible":
            warnings.append("No lattice can reach this target; the closest designs found are shown (force was set).")
        elif res["level"] in ("extended", "outside"):
            warnings.append(res["message"])
    return Preflight(material=material, reach=res, warnings=warnings, cache_key=cache_key(request))
