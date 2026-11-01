#!/usr/bin/env python3
"""
generate_strength_labels.py

Adds strength labels (and recomputed stiffness) to lattices from the truss dataset,
at any relative density, using the periodic beam solver in lattice_strength.py.

Examples (run from this folder; needs numpy + scipy; pandas only for --verify):
  python generate_strength_labels.py --verify                 # check solver vs stiffness-vec.csv
  python generate_strength_labels.py --n 20000 --rho 0.05 0.10 0.15 0.20 --out labels.csv
  python generate_strength_labels.py --n 0 --rho 0.15          # ALL lattices at density 0.15
  # 100,000 lattices x 3 densities, in 10 resumable pieces (same --n and --seed every time):
  python generate_strength_labels.py --n 100000 --rho 0.05 0.15 0.25 --parts 10 --part 0 --out labels_part0.csv

Output columns
  id, rho, C1111 C1122 C1133 C2222 C2233 C3333 C2323 C3131 C1212   (stiffness / E_s)
  y_x y_y y_z   first-yield strength / sigma_y   (uniaxial stress along that axis)
  b_x b_y b_z   strut-buckling strength / E_s    (uniaxial compression along that axis)
  n_struts, ok
Strength for a real material (E_s, sigma_y):  min(sigma_y * y, E_s * b)
"""
import argparse, os, sys, time
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"          # one math thread per worker: many workers x many threads stalls the run
import numpy as np
import scipy.sparse as sp
from multiprocessing import Pool, cpu_count, freeze_support

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lattice_strength as ls

COLS = ["id", "rho", "C1111", "C1122", "C1133", "C2222", "C2233", "C3333", "C2323", "C3131", "C1212",
        "y_x", "y_y", "y_z", "b_x", "b_y", "b_z", "n_struts", "ok"]


def work(task):
    ids, adj, pos, rhos = task
    rows = []
    for n, i in enumerate(ids):
        for rho in rhos:
            try:
                r = ls.solve_lattice(adj[n], pos[n], rho=rho)
                rows.append([i, rho, *r["stiff9"], *r["y"], *r["b"], r["n_struts"], 1])
            except Exception:
                rows.append([i, rho] + [np.nan] * 15 + [0, 0])
    return np.array(rows, dtype=float)


def tasks(A, P, ids, rhos, chunk):
    for s in range(0, len(ids), chunk):
        sub = ids[s:s + chunk]
        rows = (sub[:, None] * 27 + np.arange(27)).ravel()
        yield (sub, A[rows].toarray().reshape(-1, 27, 27), P[rows].toarray().reshape(-1, 27, 3), rhos)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=os.path.join(HERE, "..", "data"))
    ap.add_argument("--out", default=os.path.join(HERE, "strength_labels.csv"))
    ap.add_argument("--n", type=int, default=2000, help="number of random lattices (0 = all)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--rho", type=float, nargs="+", default=[0.15], help="relative densities")
    ap.add_argument("--workers", type=int, default=max(1, min(cpu_count() - 1, 8)))
    ap.add_argument("--chunk", type=int, default=200)
    ap.add_argument("--parts", type=int, default=1, help="split the chosen lattices into this many parts")
    ap.add_argument("--part", type=int, default=0, help="which part to label now (0-based); lets you run in pieces and resume")
    ap.add_argument("--exclude", nargs="+", default=[],
                    help="label CSV(s) whose lattice ids must NOT be drawn again (use with a new --seed to add fresh lattices)")
    ap.add_argument("--verify", action="store_true",
                    help="compare solver stiffness at rho=0.15 with stiffness-vec.csv on 200 random lattices")
    a = ap.parse_args()

    t0 = time.time()
    A = sp.load_npz(os.path.join(a.data_dir, "adjacency-matrix.npz")).tocsr()
    P = sp.load_npz(os.path.join(a.data_dir, "node-position.npz")).tocsr()
    N = A.shape[0] // 27
    print(f"loaded {N} lattices in {time.time() - t0:.1f}s")
    rng = np.random.default_rng(a.seed)

    if a.verify:
        import pandas as pd
        S = pd.read_csv(os.path.join(a.data_dir, "stiffness-vec.csv"), header=None).values
        ids = np.sort(rng.choice(N, 200, replace=False))
        out = np.vstack([work(t) for t in tasks(A, P, ids, [0.15], 100)])
        err = np.abs(out[:, 2:11] - S[ids]).max(1) / np.abs(S[ids]).max(1)
        print(f"stiffness vs dataset on {len(ids)} lattices: median rel. error {np.median(err):.1e}, "
              f"max {err.max():.1e}  (expect ~1e-6)")
        return

    if a.exclude:
        used = np.unique(np.concatenate([np.loadtxt(f, delimiter=",", skiprows=1, usecols=0, dtype=np.int64)
                                         for f in a.exclude]))
        pool = np.setdiff1d(np.arange(N), used)
        print(f"excluding {len(used)} already-labelled lattices; {len(pool)} left to draw from")
        ids = pool if a.n == 0 else np.sort(rng.choice(pool, min(a.n, len(pool)), replace=False))
    else:
        ids = np.arange(N) if a.n == 0 else np.sort(rng.choice(N, min(a.n, N), replace=False))
    if a.parts > 1:
        ids = np.array_split(ids, a.parts)[a.part]
    print(f"labelling {len(ids)} lattices x {len(a.rho)} densities with {a.workers} workers"
          + (f" (part {a.part + 1} of {a.parts})" if a.parts > 1 else ""))
    chunks, t1 = [], time.time()
    total = len(ids) * len(a.rho)

    def report(res):
        chunks.append(res)
        done = sum(len(c) for c in chunks)
        print(f"  {done}/{total} rows, {time.time() - t1:.0f}s", flush=True)

    if a.workers <= 1:
        for t in tasks(A, P, ids, a.rho, a.chunk):
            report(work(t))
    else:
        with Pool(a.workers) as pool:
            for res in pool.imap_unordered(work, tasks(A, P, ids, a.rho, a.chunk)):
                report(res)
    out = np.vstack(chunks)
    out = out[np.lexsort((out[:, 1], out[:, 0]))]
    fmt = ["%d"] + ["%.4f"] + ["%.8e"] * 15 + ["%d", "%d"]
    np.savetxt(a.out, out, delimiter=",", header=",".join(COLS), comments="", fmt=fmt)
    print(f"wrote {a.out}  ({len(out)} rows, {int(out[:, -1].sum())} ok) in {time.time() - t1:.0f}s")


if __name__ == "__main__":
    freeze_support()
    main()

