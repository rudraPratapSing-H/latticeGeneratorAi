"""From a framed implant mesh to the zone table: requirements, picker check, snapped targets, lattice or solid.

Pure functions (no FastAPI). Every automatic number records its source; nothing is changed silently: the table shows the
requested value next to the snapped one.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from core import reach as reach_mod
from core import zoning
from core.profiles import implant as profile

Z = 2  # index of the long axis in [x, y, z] triples


def sourced(value: float | None, source: str, note: str | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"value": None if value is None else float(value), "source": source}
    if note:
        d["note"] = note
    return d


def axis_triple(z_value: float | None, source: str, note: str | None = None) -> dict[str, Any]:
    """Targets run along the implant's long axis only: x and y are 'don't care' (the search may shape them freely)."""
    return {"x": sourced(None, "automatic"), "y": sourced(None, "automatic"), "z": sourced(z_value, source, note)}


def zone_from_range(slices: list[zoning.Slice], stress: list[dict[str, float]], a: float, b: float) -> dict[str, Any]:
    """Zone properties for the range [a, b] mm (used when the user moves a boundary)."""
    idx = [i for i, s in enumerate(slices) if a <= s.z <= b] or [min(range(len(slices)), key=lambda i: abs(slices[i].z - (a + b) / 2))]
    return {
        "range_mm": [float(a), float(b)],
        "thickness_mm": float(min(slices[i].thickness for i in idx)),
        "area_mm2": float(np.mean([slices[i].area for i in idx])),
        "stress_mpa": float(max(stress[i]["design_mpa"] for i in idx)),
        "axial_mpa": float(max(stress[i]["axial_mpa"] for i in idx)),
        "slices": len(idx),
    }


def choose_cell(zones: list[dict[str, Any]], cells_across: int | None = None) -> tuple[float | None, list[str]]:
    """The largest printable cell that fits across the thinnest LATTICE zone. Zones too thin for any printable cell are
    turned solid (in place) and named in the notes. Returns (cell_mm or None when nothing can be lattice, notes)."""
    notes: list[str] = []
    while True:
        lat = [z for z in zones if z.get("kind") != "solid"]
        if not lat:
            return None, notes
        lo, hi = zoning.cell_range(min(z["thickness_mm"] for z in lat), cells_across)
        if hi >= lo:
            half = math.floor(hi * 2) / 2.0               # round down to half a millimetre
            return (half if half >= lo else hi), notes
        thin = min(lat, key=lambda z: z["thickness_mm"])
        thin["kind"] = "solid"
        thin["reason"] = (f"Too thin for a printable lattice: the zone is {thin['thickness_mm']:.1f} mm thick, so fewer than "
                          f"{cells_across or profile.GEOMETRY['cells_across_thinnest']['value']} cells of at least {lo:.1f} mm fit across it.")
        notes.append(f"{thin['name']} became solid: {thin['reason']}")


def evaluate_zone(table: reach_mod.ReachTable, material: dict[str, Any], zone: dict[str, Any], tol: float = 0.10) -> None:
    """Fill zone['reach'], zone['kind'], zone['reason'] and the search target from the dataset picker (in place)."""
    req = zone["requirement"]
    k = req["stiffness_gpa"]["z"]["value"]
    s = req["strength_mpa"]["z"]["value"]
    stiff = [None, None, k] if k else None
    stren = [None, None, s] if s else None
    if stiff is None and stren is None:
        zone["kind"], zone["reason"] = "undecided", "No stiffness or strength target for this zone."
        zone["reach"] = None
        return
    res = table.check(material, stiffness=stiff, strength=stren, modes={"stiffness": "about", "strength": "at_least"}, tol=tol)
    nearest = res["nearest"]
    zone["reach"] = {
        "level": res["level"], "distance_pct": res["distance_pct"], "density": res["density"],
        "message": res["message"], "bounds": res["bounds"],
        "snapped": {"stiffness_gpa": dict(zip("xyz", nearest["stiffness_gpa"])),
                    "strength_mpa": dict(zip("xyz", nearest["strength_mpa"])), "lattice_id": nearest["lattice_id"]},
    }
    if zone.get("forced_kind") == "solid":
        zone["kind"] = "solid"
        zone["reason"] = zone.get("forced_reason") or "Set to solid by you."
        return
    if res["level"] == "infeasible":
        smax = res["bounds"]["strength_max_mpa"]
        if s and s > smax:
            zone["kind"] = "solid"
            zone["reason"] = (f"The strength this zone needs ({s:.0f} MPa, with the safety factor) is above the most any lattice in the "
                              f"dataset reaches for this material ({smax:.1f} MPa), so it is solid.")
        else:
            zone["kind"] = "undecided"
            zone["reason"] = ("The stiffness this zone is meant to match is above what a lattice of this material can give "
                              f"at the densities in the dataset. Choose: solid, or the closest lattice (softer than target). {res['message']}")
        return
    if k and k > table.limits(material)["stiffness_max_gpa"]:
        zone["kind"] = "undecided"
        zone["reason"] = "Solid, or closest lattice (softer than target): the bone-matching stiffness is above the dataset maximum."
        return
    zone["kind"] = "lattice"
    zone["reason"] = {
        "covered": "A stored lattice is within tolerance of this zone's targets.",
        "extended": "No stored lattice is within tolerance; the search will try to design one.",
        "outside": "Far from every stored lattice; a match is unlikely. Consider solid.",
    }[res["level"]]
    # the search target is the snapped one (the nearest stored lattice), never lower than the need for strength
    if stren is not None and nearest["strength_mpa"][Z] < s * 0.995 and res["level"] != "covered":
        zone["reason"] += " The nearest stored lattice is weaker than needed."


def build_zone_table(slices: list[zoning.Slice], stress: list[dict[str, float]], length_mm: float, fields: dict[str, Any],
                     material: dict[str, Any], cell_mm: float | None = None, edits: dict[str, Any] | None = None,
                     table: reach_mod.ReachTable | None = None) -> dict[str, Any]:
    """The whole zone table. `edits` carries what the user changed: moved boundaries, forced kinds, typed targets, cell size."""
    table = table or reach_mod.get_table()
    edits = edits or {}
    notes: list[str] = []
    warnings: list[str] = []

    edited = edits.get("zones")
    if edited:
        edited = sorted(edited, key=lambda e: e["range_mm"][0])
        zones = []
        for e in edited:
            zn = zone_from_range(slices, stress, *e["range_mm"])
            zn["id"] = e.get("id") or f"z{len(zones) + 1}"
            zn["edit"] = e
            zones.append(zn)
        zoning.name_zones(zones, length_mm)
    else:
        zones = zoning.make_zones(slices, stress, length_mm)
        zoning.name_zones(zones, length_mm)

    rules = " ".join(str(r).lower() for r in fields.get("special_rules") or [])
    for zn in zones:
        zn["kind"] = None
        bone = profile.region_for(zn["position"])
        zn["bone_region"] = bone["name"]
        ed = zn.get("edit") or {}
        k = ed.get("stiffness_z")
        s = ed.get("strength_z")
        zn["requirement"] = {
            "stiffness_gpa": axis_triple(k if k is not None else bone["stiffness"]["value"], "requested" if k is not None else "automatic",
                                         None if k is not None else f"bone stiffness placeholder for the {bone['name']} (source: TODO)"),
            "strength_mpa": axis_triple(s if s is not None else zn["stress_mpa"], "requested" if s is not None else "automatic",
                                        None if s is not None else "peak stress of the governing load case x safety factor"),
            "density": sourced(None, "automatic", "lowest dataset density at which the zone is covered"),
        }
        if ed.get("kind") in ("solid", "lattice"):
            zn["forced_kind"] = ed["kind"]
        if "neck" in zn["name"] and ("neck solid" in rules or "solid neck" in rules or "keep the neck" in rules or "keep neck" in rules):
            zn["forced_kind"] = "solid"
            zn["forced_reason"] = "The description asks to keep the neck solid."
    # dataset picker per zone, then the cell size from the lattice zones, then snap boundaries to the grid
    for zn in zones:
        evaluate_zone(table, material, zn)
    cell, cnotes = choose_cell(zones) if cell_mm is None else (float(cell_mm), [])
    if edits.get("cell_mm"):
        cell = float(edits["cell_mm"])
    notes += cnotes
    lo, hi = zoning.cell_range(min([z["thickness_mm"] for z in zones if z["kind"] != "solid"] or [0.0]))
    if cell is None:
        cell = 5.0
        warnings.append("Every zone is solid, so no lattice cell size is needed; 5 mm is shown for the grid.")
    if not edits.get("zones"):
        notes += zoning.snap_to_grid(zones, cell)
    for zn in zones:                       # properties follow the final range (merged or moved zones)
        merged = zone_from_range(slices, stress, *zn["range_mm"])
        zn.update({k: merged[k] for k in ("thickness_mm", "area_mm2", "stress_mpa", "axial_mpa", "slices")})
        if zn["requirement"]["strength_mpa"]["z"]["source"] != "requested":       # typed targets stay; automatic ones follow the final range
            zn["requirement"]["strength_mpa"]["z"]["value"] = zn["stress_mpa"]
        zn["cells"] = max(0, int(math.floor((zn["range_mm"][1] - zn["range_mm"][0]) / cell + 1e-6)))
        evaluate_zone(table, material, zn)
    zones = [{k: v for k, v in z.items() if k not in ("edit", "forced_kind", "forced_reason")} for z in zones]
    seen: dict[str, int] = {}
    for zn in zones:                       # two zones in the same bone region get a number, so every name is unique
        seen[zn["name"]] = seen.get(zn["name"], 0) + 1
    count: dict[str, int] = {}
    for zn in zones:
        if seen[zn["name"]] > 1:
            count[zn["name"]] = count.get(zn["name"], 0) + 1
            zn["name"] = f"{zn['name']} {count[zn['name']]}"

    # neighbouring stiffness ratio
    ratio = profile.GEOMETRY["stiffness_ratio_warn"]["value"]
    for a, b in zip(zones[:-1], zones[1:]):
        ka, kb = a["requirement"]["stiffness_gpa"]["z"]["value"], b["requirement"]["stiffness_gpa"]["z"]["value"]
        if ka and kb and max(ka, kb) / min(ka, kb) > ratio:
            warnings.append(f"{a['name']} and {b['name']} differ in stiffness by more than {ratio:g}x; a solid interface plate is used between them.")
    if all(z["kind"] == "solid" for z in zones):
        smax = table.limits(material)["strength_max_mpa"]
        warnings.append(f"Every zone is solid. The load case needs up to {max(z['stress_mpa'] for z in zones):.0f} MPa; the strongest lattice "
                        f"in the dataset gives {smax:.0f} MPa. Try a lower activity or body weight, or a solid core with a lattice shell (not built).")
    return {"zones": zones, "cell_mm": cell, "cell_range_mm": [lo, hi], "notes": notes, "warnings": warnings}
