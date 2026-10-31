"""Build core/tables/reach_table.npz from the solver labels (run once; the table is committed, the CSV is not).

    python scripts/build_reach_table.py C:\\AI-manthan\\data\\model\\strength-labels\\labels_300k_x3.csv

Per row: density index (0, 1, 2 = 0.05, 0.15, 0.25), normalised stiffness per axis E/E_s (1 / diag of the inverse
of the 3x3 normal-stiffness block, the same formula as search_design.c9_to_E), yield per axis (units of sigma_y)
and buckling per axis (units of E_s), exactly as the solver wrote them. Float32. Rows are stored in three blocks,
one per density, so a query at one density reads one contiguous slice.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DENSITIES = (0.05, 0.15, 0.25)
DEFAULT_OUT = ROOT / "core" / "tables" / "reach_table.npz"


def normal_block_to_E(d) -> np.ndarray:
    """Young's modulus per axis (units of E_s) from the 3x3 normal block of the stiffness matrix. NOT C1111:
    the block has off-diagonal terms, and E_x = 1 / S11 of its inverse."""
    n = len(d)
    N = np.zeros((n, 3, 3))
    for (i, j), col in {(0, 0): "C1111", (0, 1): "C1122", (0, 2): "C1133", (1, 1): "C2222", (1, 2): "C2233",
                        (2, 2): "C3333"}.items():
        N[:, i, j] = N[:, j, i] = d[col].values
    with np.errstate(all="ignore"):
        return 1.0 / np.diagonal(np.linalg.inv(N), axis1=1, axis2=2)


def build(csv_path: Path, out: Path) -> dict:
    import pandas as pd

    t0 = time.time()
    d = pd.read_csv(csv_path)
    d = d[d["ok"] == 1].reset_index(drop=True)
    E = normal_block_to_E(d)
    Y = d[["y_x", "y_y", "y_z"]].values
    B = d[["b_x", "b_y", "b_z"]].values
    good = np.isfinite(E).all(1) & (E > 0).all(1) & np.isfinite(Y).all(1) & (Y > 0).all(1) \
        & np.isfinite(B).all(1) & (B > 0).all(1)
    dens = np.full(len(d), -1, dtype=np.int8)
    for i, r in enumerate(DENSITIES):
        dens[np.isclose(d["rho"].values, r)] = i
    good &= dens >= 0
    arrays = {}
    for i in range(3):
        m = good & (dens == i)
        arrays[f"E{i}"] = E[m].astype(np.float32)
        arrays[f"Y{i}"] = Y[m].astype(np.float32)
        arrays[f"B{i}"] = B[m].astype(np.float32)
        arrays[f"id{i}"] = d["id"].values[m].astype(np.int32)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, densities=np.array(DENSITIES, dtype=np.float32), **arrays)
    info = {"rows": int(len(d)), "kept": int(good.sum()), "dropped": int((~good).sum()),
            "seconds": round(time.time() - t0, 1), "bytes": out.stat().st_size}
    return info


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("labels_csv", type=Path)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args(argv)
    if not a.labels_csv.is_file():
        print(f"labels file not found: {a.labels_csv}", file=sys.stderr)
        return 1
    info = build(a.labels_csv, a.out)
    print(f"wrote {a.out}: {info['kept']} rows kept, {info['dropped']} dropped, {info['bytes'] / 1e6:.1f} MB, "
          f"{info['seconds']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
