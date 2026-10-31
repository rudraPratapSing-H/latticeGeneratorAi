"""Assemble the implant from zones: whole-cell lattice per lattice zone, solid parts, thin solid interface plates.

No boolean operations: the result is a list of closed shells (struts as prisms, clipped-and-capped solid parts, extruded
plates) that overlap by a small margin where they meet; slicers merge overlaps. Every number here is geometry (counts,
lengths, volumes of the shells); none of it is solver-verified. See core/check.py for the labelled stiffness estimate.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import trimesh

from core import meshing, tiling, zoning
from core.profiles import implant as profile

Progress = Callable[[str, float, str], None]


class AssemblyFailed(RuntimeError):
    """The lattice of a zone fell apart (main connected part under 90% of its struts)."""


@dataclass
class Part:
    name: str
    kind: str                      # lattice | solid | interface
    zone_ids: list[str]
    mesh: trimesh.Trimesh
    info: dict[str, Any] = field(default_factory=dict)


@dataclass
class Assembly:
    parts: list[Part]
    zones: list[dict[str, Any]]
    warnings: list[str]
    notes: list[str]
    interface_mm: float
    sides: int
    length_mm: float
    cell_mm: float

    @property
    def triangles(self) -> int:
        return int(sum(len(p.mesh.faces) for p in self.parts))


def segments_for(frame: trimesh.Trimesh, zones: list[dict[str, Any]], cell_mm: float, lattices: dict[str, dict[str, Any]],
                 warnings: list[str]) -> tuple[list[dict[str, Any]], dict[str, tiling.Grid]]:
    """Cover [0, L] with lattice segments (whole cells) and solid segments (solid zones, slivers, zones where no cell fits)."""
    L = float(frame.bounds[1][2])
    segs: list[dict[str, Any]] = []
    grids: dict[str, tiling.Grid] = {}

    def add(z0: float, z1: float, kind: str, zid: str | None) -> None:
        if z1 - z0 > 1e-6:
            segs.append({"z0": z0, "z1": z1, "kind": kind, "zone": zid})

    for zn in zones:
        a, b = zn["range_mm"]
        if zn["kind"] == "undecided":
            raise ValueError(f"{zn['name']} is undecided: choose solid or lattice before assembling.")
        if zn["kind"] == "solid" or zn["id"] not in lattices:
            add(a, b, "solid", zn["id"])
            continue
        c0 = math.ceil(a / cell_mm - 1e-6) * cell_mm
        c1 = math.floor(b / cell_mm + 1e-6) * cell_mm
        grid = tiling.cells_for_range(frame, c0, c1, cell_mm) if c1 > c0 else None
        if grid is None or not grid.cells:
            warnings.append(f"No whole {cell_mm:g} mm cell fits inside {zn['name']}, so it is solid.")
            add(a, b, "solid", zn["id"])
            continue
        add(a, c0, "solid", zn["id"])
        add(c0, c1, "lattice", zn["id"])
        add(c1, b, "solid", zn["id"])
        grids[zn["id"]] = grid
        if (c0 - a) > 1e-6 or (b - c1) > 1e-6:
            warnings.append(f"{zn['name']}: {(c0 - a) + (b - c1):.1f} mm at the zone ends is shorter than one cell and is filled solid.")
    # merge neighbouring solid segments into one run
    merged: list[dict[str, Any]] = []
    for s in sorted(segs, key=lambda s: s["z0"]):
        if merged and merged[-1]["kind"] == "solid" == s["kind"] and abs(merged[-1]["z1"] - s["z0"]) < 1e-6:
            merged[-1]["z1"] = s["z1"]
            merged[-1].setdefault("zones", [merged[-1]["zone"]]).append(s["zone"])
        else:
            s.setdefault("zones", [s["zone"]])
            merged.append(s)
    if merged:
        merged[0]["z0"] = 0.0
        merged[-1]["z1"] = L
    return merged, grids


def assemble(frame: trimesh.Trimesh, zones: list[dict[str, Any]], cell_mm: float, lattices: dict[str, dict[str, Any]],
             interface_mm: float | None = None, sides: int = 8, progress: Progress | None = None,
             should_stop: Callable[[], bool] | None = None, max_triangles: int = 3_000_000) -> Assembly:
    """`lattices[zone_id]` is the chosen candidate's lattice dict (octant27) for every lattice zone."""
    emit = progress or (lambda *_: None)
    stop = should_stop or (lambda: False)
    t = interface_mm if interface_mm is not None else profile.GEOMETRY["interface_mm"]["value"]
    L = float(frame.bounds[1][2])
    warnings: list[str] = []
    notes: list[str] = []
    zone_by_id = {z["id"]: z for z in zones}

    emit("tile", 0.02, "Finding the whole cells that fit inside the implant")
    segs, grids = segments_for(frame, zones, cell_mm, lattices, warnings)
    parts: list[Part] = []
    zone_stats: dict[str, dict[str, Any]] = {z["id"]: {"zone_id": z["id"], "name": z["name"], "kind": "solid", "cells": 0, "struts": 0}
                                           for z in zones}

    lattice_segs = [s for s in segs if s["kind"] == "lattice"]
    for n, s in enumerate(lattice_segs):
        if stop():
            raise InterruptedError("cancelled")
        zid = s["zone"]
        zn = zone_by_id[zid]
        emit("tile", 0.05 + 0.5 * n / max(1, len(lattice_segs)), f"Tiling {zn['name']}")
        lat = lattices[zid]
        a, b, r = tiling.tile(lat, grids[zid], cell_mm)
        a, b, rep = tiling.remove_fragments(a, b)
        if rep["main_share"] < 0.9:
            raise AssemblyFailed(f"The lattice of {zn['name']} fell apart: its main connected part holds only "
                                 f"{100 * rep['main_share']:.0f}% of the struts (needs 90%). Choose another candidate or cell size.")
        if rep["removed"]:
            notes.append(f"{zn['name']}: removed {rep['removed']} loose strut(s) that were not part of the main lattice.")
        length = float(np.linalg.norm(b - a, axis=1).sum())
        diameter = 2 * r
        st = zone_stats[zid]
        gz = sorted({k for _, _, k in grids[zid].cells})
        st.update({"kind": "lattice", "cells": len(grids[zid].cells), "grid_cells": [grids[zid].nx, grids[zid].ny, len(gz)], "struts": int(len(a)), "strut_radius_mm": r,
                   "strut_length_mm": length, "strut_volume_mm3": math.pi * r * r * length,
                   "rel_density": lat.get("rel_density"), "components": rep["components"], "removed_fragments": rep["removed"],
                   "main_share": rep["main_share"], "min_diameter_mm": diameter, "printable": diameter >= profile.GEOMETRY["min_strut_mm"]})
        if diameter < profile.GEOMETRY["min_strut_mm"]:
            need = profile.GEOMETRY["min_strut_mm"] * cell_mm / diameter
            warnings.append(f"{zn['name']}: struts are {diameter:.2f} mm thick, below the {profile.GEOMETRY['min_strut_mm']:g} mm many printers "
                            f"can make. A cell size of at least {need:.1f} mm would print.")
        v, f = meshing.prisms(a, b, r, sides)
        parts.append(Part(f"lattice {zn['name']}", "lattice", [zid], trimesh.Trimesh(v, f, process=False),
                          {"struts": int(len(a)), "cells": len(grids[zid].cells), "radius_mm": r}))
        if sum(len(p.mesh.faces) for p in parts) > max_triangles:
            raise AssemblyFailed(f"The assembled implant would exceed {max_triangles:,} triangles. Use a larger cell size.")

    emit("assemble", 0.6, "Building the solid parts")
    for s in [s for s in segs if s["kind"] == "solid"]:
        if stop():
            raise InterruptedError("cancelled")
        names = ", ".join(dict.fromkeys(zone_by_id[z]["name"] for z in s["zones"] if z in zone_by_id))
        m = meshing.clip_and_cap(frame, s["z0"], s["z1"])
        parts.append(Part(f"solid {names}", "solid", [z for z in s["zones"] if z], m, {"z": [s["z0"], s["z1"]]}))
        for z in s["zones"]:
            if z in zone_stats and zone_stats[z]["kind"] != "lattice":
                zone_stats[z].update({"kind": "solid", "run_volume_mm3": float(abs(m.volume))})

    emit("assemble", 0.8, "Adding the interface plates between zones")
    for left, right in zip(segs[:-1], segs[1:]):
        if left["kind"] == "solid" and right["kind"] == "solid":
            continue
        zb = left["z1"]
        poly = zoning.section_polygon(frame, min(max(zb, 1e-3), L - 1e-3))
        if poly is None or poly.is_empty:
            continue
        z0, z1 = max(0.0, zb - t / 2), min(L, zb + t / 2)
        plate = meshing.extrude_polygon(poly, z0, z1)
        parts.append(Part(f"interface at {zb:.0f} mm", "interface", [z for z in (left["zone"], right["zone"]) if z], plate,
                          {"z": [z0, z1], "thickness_mm": z1 - z0}))
    emit("assemble", 0.95, "Done assembling")
    return Assembly(parts, list(zone_stats.values()), warnings, notes, float(t), sides, L, float(cell_mm))
