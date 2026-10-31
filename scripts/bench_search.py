"""Round-1 search time and match rate on 10 requests taken from lattices the predictor never trained on.

    python scripts/bench_search.py [--grid 9 5 3] [--starts 100 50] [--n 10]

Requests are what the demo sends: stiffness about, strength at least, weight AT MOST (the density is free, so the
solver checks up to n_grid densities per lattice). The search pool holds only the trained lattices, so the source lattice
itself is never in it. One round per configuration (ladder = [K]). Needs the GPU laptop and the labels files
(LABELS_DIR, default ../strength-labels). Prints one row per configuration.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
os.environ.pop("MOCK", None)
sys.path.insert(0, str(ROOT))

from core.engine import load_engine  # noqa: E402
from server import units  # noqa: E402
from server.schemas import DesignRequest  # noqa: E402


def requests(n: int, labels: Path):
    import pandas as pd
    from core.reach import ReachTable

    seen = np.unique(pd.read_csv(labels / "labels_100k_x3.csv", usecols=["id"])["id"].values)
    dl = pd.read_csv(labels / "labels_300k_x3.csv")
    dl = dl[(dl["ok"] == 1) & ~dl["id"].isin(seen)].sample(n=n, random_state=0)
    table = ReachTable.load()
    mat = units.MATERIALS["ti64"]
    out = []
    for _, row in dl.iterrows():
        i = int(np.argmin([abs(d - row["rho"]) for d in table.densities]))
        k = int(np.flatnonzero(table.ids[i] == row["id"])[0])
        v = table.values(mat, i)
        mass = table.densities[i] * 64 * mat["density_g_cm3"]
        out.append(DesignRequest(
            material="ti64", part={"size_mm": [40, 40, 40], "cell_mm": 10},
            target={"stiffness_gpa": dict(zip("xyz", map(float, v["stiff"][k]))),
                    "strength_mpa": dict(zip("xyz", map(float, v["eff"][k]))), "max_mass_g": round(mass, 3)},
            modes={"stiffness": "about", "strength": "at_least", "weight": "at_most"}))
    return out, seen


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--grid", type=int, nargs="+", default=[9, 5, 3])
    ap.add_argument("--starts", type=int, nargs="+", default=[100])
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--labels", type=Path, default=Path(os.environ.get("LABELS_DIR") or ROOT.parent / "strength-labels"))
    a = ap.parse_args(argv)
    reqs, seen = requests(a.n, a.labels)
    eng = load_engine()
    if not eng.ok:
        print("engine did not load:", eng.status["reason"])
        return 1
    ids = np.load(ROOT / "encoded_codes.npz")["ids"]
    pool = np.where(np.isin(ids, seen))[0]
    print(f"workers={eng.status['workers']}  priority={'normal' if os.environ.get('SOLVER_PRIORITY') == 'normal' else 'below normal'}")
    print(f"{'n_grid':>6} {'K':>5} {'matched':>8} {'median s':>9} {'mean s':>8} {'max s':>7} {'worst err %':>12}")
    eng.run(reqs[0], None, None, ladder=(20,), search_kwargs={"pool_idx": pool})        # warm up CUDA
    for k in a.starts:
        for g in a.grid:
            times, matched, errs = [], 0, []
            for r in reqs:
                t = time.time()
                res = eng.run(r, None, None, ladder=(k,), search_kwargs={"pool_idx": pool, "n_grid": g})
                times.append(time.time() - t)
                c = res["candidates"]
                matched += bool(c and c[0]["matches_targets"])
                errs.append(c[0]["match_error_pct"] if c else float("inf"))
            print(f"{g:>6} {k:>5} {matched:>5}/{len(reqs):<2} {np.median(times):>9.1f} {np.mean(times):>8.1f} "
                  f"{max(times):>7.1f} {max(errs):>12.1f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
