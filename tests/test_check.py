"""T16: the finite beam model. Validation: a growing block approaches the periodic solve of the same lattice."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import check  # noqa: E402

DEMO = Path(__file__).resolve().parent.parent / "demo" / "jobs"


def cand(n=0):
    return sorted(DEMO.glob("*/results.json"))[n].read_text(encoding="utf-8"), n


def lat(n):
    return json.loads(sorted(DEMO.glob("*/results.json"))[n].read_text(encoding="utf-8"))[0]


def test_periodic_c33_matches_the_solver_directly():
    c = lat(1)
    ls = check._solver()
    nodes, edges = np.asarray(c["lattice"]["nodes"]), np.asarray(c["lattice"]["edges"])
    adj = np.zeros((len(nodes), len(nodes)))
    adj[edges[:, 0], edges[:, 1]] = adj[edges[:, 1], edges[:, 0]] = 1
    direct = ls.solve_lattice(adj, nodes, rho=c["rel_density"])["C"][2, 2]
    assert check.periodic_c33(c["lattice"], check.r_solver_of(c["lattice"])) == pytest.approx(direct, rel=2e-3)


@pytest.mark.parametrize("n", [0, 1])
def test_block_stiffness_converges_towards_the_periodic_value(n):
    c = lat(n)["lattice"]
    r = check.r_solver_of(c)
    inf = check.periodic_c33(c, r)
    dev = [abs(check.block_stiffness(c, r, k, k, 3)["e_norm"] / inf - 1) for k in (1, 2, 4)]
    assert dev[0] > dev[1] > dev[2], dev                          # monotone approach as the footprint grows
    assert dev[2] < 0.65


def test_zone_check_reports_label_ratio_and_warning_for_small_blocks():
    c = lat(0)
    out = check.zone_check(c["lattice"], c["lattice"]["cell_size_mm"], (1, 1, 2), 114.0, c["verified"]["stiffness_gpa"]["z"])
    assert out["label"] == "beam_model_estimate" and out["stiffness_z_gpa"] > 0 and np.isfinite(out["ratio_to_infinite"])
    assert out["warning"] and "estimate" in out["note"]
    assert out["candidate_verified_z_gpa"] == c["verified"]["stiffness_gpa"]["z"]


def test_big_zone_uses_a_representative_block_within_the_element_budget():
    c = lat(1)["lattice"]
    out = check.zone_check(c, c["cell_size_mm"], (20, 20, 30), 114.0, None)
    assert out["representative"] and out["struts"] <= check.MAX_ELEMENTS and np.prod(out["block_cells"]) < 20 * 20 * 30
