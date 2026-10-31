"""Re-solve returned designs with the beam solver, independently of the server, and compare with the API numbers.

  python scripts/verify_design.py <job_id>        every design of a job
  python scripts/verify_design.py <design_id>     one design (ids look like j_xxxxxxxx_d_xxxxxxxx)
Reads runs/<job>/results.json. Needs only numpy and the repo's solver.
"""
import glob
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import search_design as sd  # noqa: E402  (finds lattice_strength.py)

E_S, SIG_Y = 114.0, 880.0   # Ti-6Al-4V


def load(arg):
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, "runs", "*", "results.json"))):
        job = os.path.basename(os.path.dirname(f))
        for c in json.load(open(f, encoding="utf-8")):
            if arg == job or arg == c["id"]:
                out.append((job, c))
    return out


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    found = load(sys.argv[1])
    if not found:
        sys.exit("nothing found for " + sys.argv[1])
    worst = 0.0
    for job, c in found:
        pos = np.array(c["lattice"]["nodes"], float)
        adj = np.zeros((len(pos), len(pos)), int)
        for a, b in c["lattice"]["edges"]:
            adj[a, b] = adj[b, a] = 1
        r = sd.solve(adj, pos, c["rel_density"])
        E = r["E"] * E_S
        S = np.minimum(r["y"] * SIG_Y, r["b"] * E_S * 1000)
        api_E = np.array(list(c["verified"]["stiffness_gpa"].values()))
        api_S = np.array(list(c["verified"]["strength_mpa"].values()))
        dev = max(np.abs(E / api_E - 1).max(), np.abs(S / api_S - 1).max())
        worst = max(worst, dev)
        print(f"{c['id']}  rank {c['rank']}  origin {c.get('origin', '?')}  rho {c['rel_density']}  "
              f"{len(c['lattice']['edges'])} struts")
        print(f"   solver now : E {np.round(E, 3)} GPa   S {np.round(S, 2)} MPa")
        print(f"   API reported: E {np.round(api_E, 3)} GPa   S {np.round(api_S, 2)} MPa   max difference {100 * dev:.4f}%")
    print(f"\nlargest difference over {len(found)} design(s): {100 * worst:.4f}%")


main()
