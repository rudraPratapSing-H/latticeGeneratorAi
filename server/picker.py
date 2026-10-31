"""Glue between a request and core.reach: the same check serves /api/reach and the pipeline's first step."""
from __future__ import annotations

from typing import Any

from core import reach
from server import units


class BadTarget(Exception):
    """A request that fails a plausibility rule. Becomes 422 {"error": {"code": "bad_target", ...}}."""

    def __init__(self, message: str, code: str = "bad_target", field: str | None = None,
                 extra: dict | None = None) -> None:
        super().__init__(message)
        self.message, self.code, self.field, self.extra = message, code, field, extra or {}


def material_or_raise(material_id: str) -> dict[str, Any]:
    m = units.MATERIALS.get(material_id.lower())
    if m is None:
        raise BadTarget(f"unknown material '{material_id}'. Available: {', '.join(units.MATERIALS)}",
                        code="unknown_material", field="material")
    return m


def plausibility(request: Any, material: dict[str, Any]) -> None:
    """Values above the material itself are unit mistakes: stiffness above E_s, strength above yield."""
    t = request.target
    for name, axis, cap, unit in (("stiffness_gpa", t.stiffness_gpa, material["E_gpa"], "GPa"),
                                  ("strength_mpa", t.strength_mpa, material["yield_mpa"], "MPa"),
                                  ("yield_strength_mpa", t.yield_strength_mpa, material["yield_mpa"], "MPa")):
        for a in "xyz":
            v = getattr(axis, a) if axis is not None else None
            if v is not None and v > cap:
                hint = " Stiffness is in GPa; did you enter MPa?" if name == "stiffness_gpa" else ""
                raise BadTarget(f"{name}.{a} = {v:g} {unit} is above the material itself ({cap:g} {unit}).{hint}",
                                field=f"target.{name}.{a}")


def reach_for_request(request: Any, material: dict[str, Any]) -> dict[str, Any]:
    """Run the dataset picker for a DesignRequest-like object (anything with material/part/target/modes/tolerance)."""
    spec = units.to_search_spec(request, material)
    yield_only = spec["yield_strength_mpa"] is not None
    res = reach.get_table().check(
        material, stiffness=spec["stiffness_gpa"], strength=spec["yield_strength_mpa"] if yield_only else spec["strength_mpa"],
        yield_only=yield_only, modes=spec["modes"], tol=spec["tol"], rho=spec["rho"], rho_max=spec["rho_max"])
    return res
