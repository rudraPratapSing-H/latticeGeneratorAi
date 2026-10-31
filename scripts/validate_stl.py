"""Check that an STL is a valid BINARY STL made of closed, outward-oriented shells (numpy only, no mesh library).

    python scripts/validate_stl.py design.stl [--expect-size-mm 20 20 20]

Checks: header + triangle count match the file size (binary, not ASCII); every coordinate is finite; no degenerate
triangles; every directed edge has its reverse (each shell is closed; touching or overlapping shells from struts that
meet at a node are fine, slicers merge them); the stored normals agree with the winding; total signed volume is
positive (outward orientation); bounding box (and optionally size). Exit code 0 when everything passes.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import numpy as np


def load(path: Path) -> tuple[np.ndarray, np.ndarray]:
    raw = path.read_bytes()
    if raw[:5] == b"solid" and b"facet" in raw[:400]:
        raise SystemExit("ASCII STL: this tool expects binary STL")
    n = int(np.frombuffer(raw[80:84], dtype="<u4")[0])
    if len(raw) != 84 + 50 * n:
        raise SystemExit(f"size mismatch: header says {n} triangles = {84 + 50 * n} bytes, file has {len(raw)}")
    rec = np.frombuffer(raw, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]), offset=84, count=n)
    return rec["v"].astype(np.float64), rec["n"].astype(np.float64)


def validate(tri: np.ndarray, normals: np.ndarray) -> dict:
    res: dict = {"triangles": len(tri)}
    res["finite"] = bool(np.isfinite(tri).all() and np.isfinite(normals).all())
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    cr = np.cross(e1, e2)
    area = np.linalg.norm(cr, axis=1) / 2
    res["degenerate"] = int((area < 1e-12).sum())
    res["normals_agree"] = bool(((cr * normals).sum(axis=1) > 0).all())
    key = np.round(tri * 1e3).astype(np.int64)
    directed: Counter = Counter()
    for t in range(len(tri)):
        for v in range(3):
            directed[(tuple(key[t, v]), tuple(key[t, (v + 1) % 3]))] += 1
    res["unmatched_edges"] = sum(1 for (a, b), c in directed.items() if directed.get((b, a)) != c)
    res["volume_mm3"] = float(np.einsum("ij,ij->", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])) / 6.0)
    res["bbox_min"] = tri.reshape(-1, 3).min(axis=0).round(3).tolist()
    res["bbox_max"] = tri.reshape(-1, 3).max(axis=0).round(3).tolist()
    res["ok"] = (res["finite"] and res["degenerate"] == 0 and res["normals_agree"] and res["unmatched_edges"] == 0
                 and res["volume_mm3"] > 0)
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stl", type=Path)
    ap.add_argument("--expect-size-mm", type=float, nargs=3)
    ap.add_argument("--size-tol-mm", type=float, default=2.0, help="struts lying on a face poke out by one radius")
    a = ap.parse_args(argv)
    tri, nrm = load(a.stl)
    r = validate(tri, nrm)
    for k, v in r.items():
        print(f"{k:16} {v}")
    if a.expect_size_mm:
        ext = np.array(r["bbox_max"]) - np.array(r["bbox_min"])
        ok = bool(np.all(np.abs(ext - np.array(a.expect_size_mm)) < a.size_tol_mm))
        print(f"{'size_ok':16} {ok} (extent {ext.round(2).tolist()})")
        r["ok"] = r["ok"] and ok
    print("VALID" if r["ok"] else "INVALID")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
