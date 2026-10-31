"""Generate a test implant: a tapered, bent, hip-stem-like body as a closed binary STL (millimetres).

    python scripts/make_test_stem.py out.stl [--length 160] [--bend 22] [--tip 13 10] [--top 20 15] [--rings 60]

Not a real implant. The long axis is z (tip at z = 0), the cross-section is an ellipse that grows from the tip to
the top, and the centreline bends in x over the upper third (the "neck"). Rings are horizontal, so slicing
perpendicular to z cuts clean sections. Also offers make_bar() for hand-calculation tests.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import trimesh


def make_stem(length: float = 160.0, bend: float = 22.0, tip=(13.0, 10.0), top=(20.0, 15.0), rings: int = 60, sides: int = 48) -> trimesh.Trimesh:
    z = np.linspace(0.0, length, rings)
    t = z / length
    a = tip[0] + (top[0] - tip[0]) * t ** 1.3          # semi-axis along x
    b = tip[1] + (top[1] - tip[1]) * t ** 1.3          # semi-axis along y
    cx = bend * np.clip((t - 0.62) / 0.38, 0.0, 1.0) ** 2      # the bend: only the upper part leans in x
    th = np.linspace(0.0, 2 * np.pi, sides, endpoint=False)
    verts = np.stack([cx[:, None] + a[:, None] * np.cos(th), b[:, None] * np.sin(th) * np.ones((rings, 1)),
                      np.repeat(z[:, None], sides, axis=1)], axis=-1).reshape(-1, 3)
    faces = []
    for i in range(rings - 1):
        for j in range(sides):
            k = (j + 1) % sides
            p00, p01 = i * sides + j, i * sides + k
            p10, p11 = (i + 1) * sides + j, (i + 1) * sides + k
            faces += [[p00, p01, p11], [p00, p11, p10]]       # counter-clockwise seen from outside
    c0 = len(verts)
    c1 = c0 + 1
    verts = np.vstack([verts, [cx[0], 0.0, z[0]], [cx[-1], 0.0, z[-1]]])
    for j in range(sides):
        k = (j + 1) % sides
        faces.append([c0, k, j])                                          # bottom cap, normal -z
        faces.append([c1, (rings - 1) * sides + j, (rings - 1) * sides + k])   # top cap, normal +z
    m = trimesh.Trimesh(vertices=verts, faces=np.array(faces), process=False)
    m.fix_normals()
    return m


def make_bar(length: float = 80.0, width: float = 12.0, depth: float = 10.0) -> trimesh.Trimesh:
    """A straight rectangular bar along z from 0 to `length` (x = width, y = depth), centred on the z axis."""
    m = trimesh.creation.box(extents=(width, depth, length))
    m.apply_translation([0, 0, length / 2])
    return m


def write_stl(mesh: trimesh.Trimesh, path: str | Path) -> None:
    Path(path).write_bytes(mesh.export(file_type="stl"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path)
    ap.add_argument("--length", type=float, default=160.0)
    ap.add_argument("--bend", type=float, default=22.0)
    ap.add_argument("--tip", type=float, nargs=2, default=(13.0, 10.0))
    ap.add_argument("--top", type=float, nargs=2, default=(20.0, 15.0))
    ap.add_argument("--rings", type=int, default=60)
    a = ap.parse_args(argv)
    m = make_stem(a.length, a.bend, tuple(a.tip), tuple(a.top), a.rings)
    write_stl(m, a.out)
    print(f"wrote {a.out}: {len(m.faces)} triangles, watertight={m.is_watertight}, volume={m.volume:.0f} mm3, extents={m.extents.round(1).tolist()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
