"""STL and a plain markdown report for an assembled implant.

The STL is the list of closed shells written as one binary file (struts, solid parts and interface plates overlap where they
meet; slicers merge overlaps). Nothing here is a clinical or safety statement.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

import numpy as np

from core.assemble import Assembly

WARN_TRIANGLES = 1_000_000


def combined_vertices_faces(a: Assembly) -> tuple[np.ndarray, np.ndarray]:
    verts, faces, base = [], [], 0
    for p in a.parts:
        verts.append(np.asarray(p.mesh.vertices, dtype=np.float64))
        faces.append(np.asarray(p.mesh.faces, dtype=np.int64) + base)
        base += len(p.mesh.vertices)
    return np.vstack(verts), np.vstack(faces)


def write_stl(a: Assembly, path: Path) -> dict[str, Any]:
    """Binary STL (little-endian, float32, outward normals), written to a temp name and renamed. Returns size info."""
    v, f = combined_vertices_faces(a)
    tri = v[f].astype(np.float32)
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(n, axis=1)
    n = np.where(ln[:, None] > 0, n / np.maximum(ln, 1e-30)[:, None], 0).astype(np.float32)
    rec = np.zeros(len(f), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    rec["n"], rec["v"] = n, tri
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "wb") as fh:
        fh.write(b"Lattice Designer - design demo, not a medical device".ljust(80, b" "))
        fh.write(struct.pack("<I", len(f)))
        fh.write(rec.tobytes())
    tmp.replace(path)
    runs: list[list[int]] = []                      # [count, triangles per shell]: lattice parts hold one prism per strut
    for p in a.parts:
        if p.kind == "lattice":
            runs.append([len(p.mesh.faces) // (4 * a.sides), 4 * a.sides])
        else:
            runs.append([1, int(len(p.mesh.faces))])
    path.with_name(path.stem + ".shells.json").write_text(json.dumps({"runs": runs}), encoding="utf-8")
    out = {"triangles": int(len(f)), "bytes": int(path.stat().st_size), "warnings": []}
    if len(f) > WARN_TRIANGLES:
        out["warnings"].append(f"The STL has {len(f):,} triangles; many slicers and viewers are slow above {WARN_TRIANGLES:,}. "
                               "A larger cell size makes a lighter file.")
    return out


def report_markdown(result: dict[str, Any]) -> str:
    L = [f"# Lattice Designer - implant design report", "", f"> {result['disclaimer']}", ""]
    s = result["summary"]
    L += ["## Summary", "",
          f"- Length {s['length_mm']:.1f} mm, cell size {s['cell_mm']:g} mm, interface plates {s['interface_mm']:g} mm",
          f"- Mass about {s['mass_g']:.1f} g (geometry only: shell volumes times the material density; overlaps counted twice, so an upper bound)",
          f"- {s['lattice_share_pct']:.0f}% of the volume is lattice, {100 - s['lattice_share_pct']:.0f}% solid or plate",
          f"- {s['triangles']:,} triangles", ""]
    L += ["## Zones", "", "| zone | range (mm) | kind | stress (MPa) | candidate | solver-verified (infinite lattice) | finite-block estimate |",
          "|---|---|---|---|---|---|---|"]
    for z in result["zones"]:
        v = z.get("verified") or {}
        chk = z.get("check") or {}
        L.append(f"| {z['name']} | {z['range_mm'][0]:.0f}-{z['range_mm'][1]:.0f} | {z['kind']} | {z['stress_mpa']:.0f} | "
                 f"{z.get('candidate_id') or '-'} | "
                 + (f"stiffness z {v['stiffness_gpa']['z']:.2f} GPa, strength z {v['strength_mpa']['z']:.1f} MPa" if v else "-")
                 + " | " + (f"{chk['stiffness_z_gpa']:.2f} GPa ({chk['label']})" if chk else "-") + " |")
    L += ["", "## How to read the numbers", ""]
    for k, d in result["verification"].items():
        L.append(f"- **{k}**: {d}")
    if result["warnings"]:
        L += ["", "## Warnings", ""] + [f"- {w}" for w in result["warnings"]]
    L += ["", "## Load assumptions (placeholders)", ""]
    for a in result["load"]["assumptions"]:
        L.append(f"- {a['name']}: {a['value']} {a['unit']} ({a['source']}{', TODO' if a.get('todo') else ''})")
    return "\n".join(L) + "\n"
