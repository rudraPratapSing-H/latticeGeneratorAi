"""Check an exported implant STL: it opens in trimesh, every shell is closed and outward-oriented, numbers are finite.

    python scripts/validate_implant_stl.py path/to/implant.stl [--shells N]

The exporter writes `implant.shells.json` next to the STL: runs of [count, triangles_per_shell]. With it, every shell is
checked on its own (closed, each edge used once in each direction, positive volume), so overlapping shells that touch each
other do not hide defects. Without it the whole file is checked as one mesh. Exit code 0 when all checks pass, 1 otherwise.
The checks are about the mesh only; they say nothing about whether the design is good.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import trimesh

REC = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])


def shell_sizes_from_runs(runs: list[list[int]]) -> np.ndarray:
    return np.concatenate([np.full(int(c), int(t), dtype=np.int64) for c, t in runs]) if runs else np.zeros(0, dtype=np.int64)


def check_shells(tri: np.ndarray, sizes: np.ndarray) -> list[str]:
    """tri: (n, 3, 3) float32 triangles; sizes: triangles per shell, in file order. Returns the problems found."""
    problems: list[str] = []
    n = len(tri)
    shell = np.repeat(np.arange(len(sizes)), sizes)
    bits = np.ascontiguousarray(tri).view(np.int32).reshape(n, 3, 3).astype(np.int64)
    keys = np.concatenate([np.repeat(shell, 3)[:, None], bits.reshape(-1, 3)], axis=1)
    _, vid = np.unique(keys, axis=0, return_inverse=True)
    vid = np.asarray(vid).ravel().reshape(n, 3)
    a, b = vid, np.roll(vid, -1, axis=1)
    directed = np.stack([a.ravel(), b.ravel()], 1)
    fwd, cnt = np.unique(directed, axis=0, return_counts=True)
    if (cnt > 1).any():
        problems.append("an edge is used twice in the same direction (non-manifold or flipped triangles)")
    rev = np.stack([fwd[:, 1], fwd[:, 0]], 1)
    all_keys = fwd[:, 0] * (int(vid.max()) + 1) + fwd[:, 1]
    rev_keys = rev[:, 0] * (int(vid.max()) + 1) + rev[:, 1]
    if not np.isin(rev_keys, all_keys).all():
        problems.append("some edge has no opposite edge: a shell is open or inconsistently wound")
    v = tri.astype(np.float64)
    vol6 = np.einsum("ij,ij->i", v[:, 0], np.cross(v[:, 1], v[:, 2]))
    vol = np.bincount(shell, weights=vol6, minlength=len(sizes)) / 6.0
    bad = int((vol <= 0).sum())
    if bad:
        problems.append(f"{bad} shell(s) have zero or negative volume (inside-out)")
    return problems


def validate(path: str | Path, expected_shells: int | None = None) -> dict:
    path = Path(path)
    problems: list[str] = []
    raw = path.read_bytes()
    n = int(np.frombuffer(raw[80:84], dtype="<u4")[0]) if len(raw) >= 84 else 0
    if len(raw) != 84 + 50 * n:
        return {"ok": False, "problems": [f"file size {len(raw)} does not match {n} binary STL triangles"]}
    rec = np.frombuffer(raw[84:], dtype=REC)
    finite = bool(np.isfinite(rec["v"]).all() and np.isfinite(rec["n"]).all())
    if not finite:
        problems.append("the file contains NaN or infinite values")
        return {"ok": False, "problems": problems, "finite": False}

    loaded = trimesh.load(str(path), file_type="stl")                      # the plain loader must open it
    if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) != n:
        problems.append("trimesh did not load the file as one mesh with every triangle")

    sidecar = path.with_name(path.stem + ".shells.json")
    if sidecar.exists():
        sizes = shell_sizes_from_runs(json.loads(sidecar.read_text(encoding="utf-8"))["runs"])
        if int(sizes.sum()) != n:
            problems.append("implant.shells.json does not match the triangle count")
            sizes = np.array([n])
    else:
        sizes = np.array([n])
    tri = np.ascontiguousarray(rec["v"])
    problems += check_shells(tri, sizes)

    v = tri.astype(np.float64)
    area2 = np.linalg.norm(np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0]), axis=1)
    degenerate = int((area2 < 1e-12).sum())
    if degenerate:
        problems.append(f"{degenerate} degenerate triangle(s)")
    calc = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    agree = float(((calc * rec["n"]).sum(axis=1) >= 0).mean()) if n else 1.0
    if agree < 0.999:
        problems.append(f"stored normals disagree with the winding on {100 * (1 - agree):.2f}% of the triangles")
    if expected_shells is not None and len(sizes) < expected_shells:
        problems.append(f"expected at least {expected_shells} shells, found {len(sizes)}")
    return {"ok": not problems, "problems": problems, "triangles": n, "shells": int(len(sizes)), "finite": finite,
            "watertight": not any("open" in p or "twice" in p for p in problems), "winding_consistent": not any("wound" in p for p in problems),
            "bounds_mm": [tri.reshape(-1, 3).min(axis=0).tolist(), tri.reshape(-1, 3).max(axis=0).tolist()]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stl")
    ap.add_argument("--shells", type=int, default=None, help="minimum number of closed shells expected")
    a = ap.parse_args()
    out = validate(a.stl, a.shells)
    print(json.dumps(out, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
