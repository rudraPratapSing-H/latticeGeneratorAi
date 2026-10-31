"""T3: the dataset picker (core/reach.py) and the table builder."""
import time

import numpy as np
import pytest

import search_design as sd
from core.reach import ReachTable, rel_errors
from server import units

MAT = units.MATERIALS["ti64"]
ABOUT = {"stiffness": "about", "strength": "about"}


@pytest.fixture(scope="module")
def table():
    return ReachTable.load()


def _row(table, i, r, material=MAT):
    v = table.values(material, i)
    return [float(x) for x in v["stiff"][r]], [float(x) for x in v["eff"][r]]


# 1  (run on a 30,000-rows-per-density slice of the table so 1,000 queries take seconds, not minutes)
def test_own_values_of_1000_random_rows_are_covered_at_distance_zero(table):
    n = 30000
    sub = ReachTable({"densities": np.array(table.densities, dtype=np.float32),
                      **{f"{k}{i}": getattr(table, {"E": "E", "Y": "Y", "B": "B", "id": "ids"}[k])[i][:n]
                         for k in ("E", "Y", "B", "id") for i in range(3)}})
    rng = np.random.default_rng(0)
    for _ in range(1000):
        i = int(rng.integers(3))
        r = int(rng.integers(n))
        st, sg = _row(sub, i, r)
        res = sub.check(MAT, stiffness=st, strength=sg, modes=ABOUT, rho=sub.densities[i])
        assert res["distance_pct"] == 0.0 and res["level"] == "covered"


# 2 (the plan says x1.5 -> about 50% and outside. That only holds at the edge of the data: a stored lattice is
# always 50% away, but in the interior another lattice is usually closer. Test what actually holds.)
def test_scaled_targets_are_never_farther_than_the_scale_and_far_outside_is_flagged(table):
    rng = np.random.default_rng(1)
    for _ in range(30):
        i = int(rng.integers(3))
        r = int(rng.integers(len(table.E[i])))
        st, sg = _row(table, i, r)
        res = table.check(MAT, stiffness=[1.5 * x for x in st], strength=[1.5 * x for x in sg], modes=ABOUT,
                          rho=table.densities[i])
        assert res["distance_pct"] <= 50.01                      # the source lattice itself is 50% away
    v = table.values(MAT, 1)                                     # the stiffest lattices x1.5 break the density bound
    for r in np.argsort(v["stiff"].sum(1))[-5:]:
        st, sg = _row(table, 1, int(r))
        res = table.check(MAT, stiffness=[1.5 * x for x in st], strength=[1.5 * x for x in sg], modes=ABOUT, rho=0.15)
        assert res["level"] == "infeasible"
    st, sg = _row(table, 0, 12345)                               # x10 on a typical row: nothing stored is near
    res = table.check(MAT, stiffness=[10 * x for x in st], strength=[10 * x for x in sg], modes=ABOUT, rho=0.05)
    assert res["level"] in ("outside", "infeasible") and res["distance_pct"] > 25


# 3
def test_stiffness_sum_above_density_bound_is_infeasible(table):
    for rho in table.densities:
        third = 1.2 * rho * MAT["E_gpa"] / 3
        res = table.check(MAT, stiffness=[third] * 3, rho=rho)
        assert res["level"] == "infeasible", res
        assert res["bounds"]["stiffness_sum_max_gpa"] == pytest.approx(rho * MAT["E_gpa"], rel=1e-3)
    rho = table.densities[1]                                     # exactly on the bound (plain cubic) is allowed
    on_bound = table.check(MAT, stiffness=[rho * MAT["E_gpa"] / 3] * 3, rho=rho)
    assert on_bound["level"] != "infeasible"


# 4
def test_strength_above_data_maximum_is_infeasible_at_every_density(table):
    assert table.limits(MAT)["densities"][2]["strength_max_mpa"] == pytest.approx(76.1, abs=0.1)
    for rho in (0.25, 0.15, 0.05):
        res = table.check(MAT, strength=[77.0, None, None], rho=rho)
        assert res["level"] == "infeasible", (rho, res)
    assert table.check(MAT, strength=[77.0, None, None])["level"] == "infeasible"      # any density
    assert table.check(MAT, strength=[70.0, None, None], rho=0.25)["level"] != "infeasible"


# 5
def test_softer_material_with_lower_yield_lowers_the_strength_limit(table):
    soft = {"id": "soft", "name": "soft", "E_gpa": 70.0, "yield_mpa": 300.0, "density_g_cm3": 2.7}
    ti, sf = table.limits(MAT), table.limits(soft)
    assert sf["densities"][2]["strength_max_mpa"] < ti["densities"][2]["strength_max_mpa"]
    assert sf["densities"][2]["stiffness_gpa"]["max"] < ti["densities"][2]["stiffness_gpa"]["max"]
    assert table.check(soft, strength=[50.0, None, None], rho=0.25)["level"] == "infeasible"
    assert table.check(MAT, strength=[50.0, None, None], rho=0.25)["level"] != "infeasible"


# 6
def test_query_over_300k_rows_is_fast_and_table_is_small(table):
    st, sg = _row(table, 1, 777)
    table.check(MAT, stiffness=st, strength=sg, rho=0.15)          # warm the material cache
    t = time.perf_counter()
    table.check(MAT, stiffness=st, strength=sg, rho=0.15)
    assert time.perf_counter() - t < 0.1
    assert table.nbytes < 300e6


# --- other behaviour the plan asks for
def test_density_choice_takes_lowest_covered_density(table):
    st, sg = _row(table, 0, 99)
    res = table.check(MAT, stiffness=st, strength=sg, modes=ABOUT)
    assert res["density"] == 0.05 and res["level"] == "covered"


def test_weight_limit_excludes_heavier_densities(table):
    st, sg = _row(table, 2, 99)
    res = table.check(MAT, stiffness=st, strength=sg, modes=ABOUT, rho_max=0.2116)
    assert res["density"] in (0.05, 0.15)
    low = table.check(MAT, stiffness=st, rho_max=0.03)
    assert low["density"] == 0.05 and low["warnings"]


def test_snap_returns_the_nearest_stored_lattice(table):
    st, sg = _row(table, 1, 4242)
    snap = table.snap(MAT, stiffness=[x * 1.02 for x in st], strength=[x * 0.98 for x in sg], modes=ABOUT, rho=0.15)
    assert snap["moved_pct"] <= 2.1 and snap["density"] == 0.15


@pytest.mark.parametrize("mode", ["about", "at_least", "at_most"])
def test_vectorised_errors_equal_search_design_solver_errors(mode):
    """The picker applies the same rule as the solver check (search_design.solver_errors)."""
    tg = sd.Target(dict(E_gpa=114.0, yield_mpa=880.0, density_g_cc=4.43), stiffness_gpa=[1.0, 2.0, 3.0],
                   strength_mpa=[5.0, 6.0, 7.0], modes={"stiffness": mode, "strength": mode}, tol=0.1)
    rng = np.random.default_rng(3)
    for _ in range(20):
        E = rng.uniform(0.2, 5, 3) / 114.0
        y = rng.uniform(1, 90, 3) / 880.0
        errs, _ = sd.solver_errors(tg, dict(E=E, y=y, b=np.full(3, 1e9)))     # huge buckling: yield governs
        mine = [rel_errors(np.array([E[a] * 114.0]), t, mode)[0] for a, t in enumerate([1.0, 2.0, 3.0])] + \
               [rel_errors(np.array([y[a] * 880.0]), t, mode)[0] for a, t in enumerate([5.0, 6.0, 7.0])]
        assert np.allclose(errs, mine, atol=1e-9)


def test_stiffness_is_inverse_normal_block_not_c1111():
    """Bug watchlist 2: E_x = 1/S11 of the inverse, not C1111; same value as search_design.c9_to_E."""
    import pandas as pd
    import torch
    from scripts.build_reach_table import normal_block_to_E
    row = dict(C1111=0.05, C1122=0.01, C1133=0.008, C2222=0.04, C2233=0.006, C3333=0.03)
    E = normal_block_to_E(pd.DataFrame([row]))[0]
    assert abs(E[0] - row["C1111"]) > 1e-3
    C9 = torch.tensor([[0.05, 0.01, 0.008, 0.04, 0.006, 0.03, 0.001, 0.001, 0.001]], dtype=torch.float64)
    assert np.allclose(E, sd.c9_to_E(C9)[0].numpy(), rtol=1e-6)


def test_table_matches_published_data_facts(table):
    lim = table.limits(MAT)["densities"]
    assert [round(d["stiffness_gpa"]["max"], 2) for d in lim] == [2.51, 7.76, 13.15]
    assert [round(d["strength_mpa"]["max"], 1) for d in lim] == [16.0, 45.3, 76.1]


@pytest.mark.gpu
def test_gpu_targets_from_unseen_lattices_are_covered_and_search_matches_9_of_10(table):
    """Plan test 7: 10 targets from lattices outside the 100k the predictor trained on. The pool holds only the
    trained lattices (the source lattice itself is not in it); the picker must call them covered, the search must
    match at least 9."""
    import os
    from pathlib import Path

    import pandas as pd
    from core.engine import load_engine
    from server.schemas import DesignRequest

    root = Path(os.environ.get("LABELS_DIR") or Path(__file__).resolve().parent.parent.parent / "strength-labels")
    f300, f100 = root / "labels_300k_x3.csv", root / "labels_100k_x3.csv"
    if not (f300.is_file() and f100.is_file()):
        pytest.skip("labels_300k_x3.csv / labels_100k_x3.csv not found (set LABELS_DIR)")
    seen = np.unique(pd.read_csv(f100, usecols=["id"])["id"].values)
    dl = pd.read_csv(f300)
    dl = dl[(dl["ok"] == 1) & ~dl["id"].isin(seen)].sample(n=10, random_state=0)

    eng = load_engine()
    assert eng.ok, eng.status["reason"]
    codes_ids = np.load(Path(__file__).resolve().parent.parent / "encoded_codes.npz")["ids"]
    pool_idx = np.where(np.isin(codes_ids, seen))[0]
    trained = ReachTable({"densities": np.array(table.densities, dtype=np.float32),
                          **{f"{k}{i}": getattr(table, {"E": "E", "Y": "Y", "B": "B", "id": "ids"}[k])[i][np.isin(table.ids[i], seen)]
                             for k in ("E", "Y", "B", "id") for i in range(3)}})
    covered = matched = 0
    for _, row in dl.iterrows():
        i = int(np.argmin([abs(d - row["rho"]) for d in table.densities]))
        v = table.values(MAT, i)
        k = int(np.flatnonzero(table.ids[i] == row["id"])[0])
        st, sg = [float(x) for x in v["stiff"][k]], [float(x) for x in v["eff"][k]]
        chk = trained.check(MAT, stiffness=st, strength=sg, rho=table.densities[i])
        covered += chk["level"] == "covered"
        req = DesignRequest(material="ti64", part={"size_mm": [40, 40, 40], "cell_mm": 10},
                            target={"stiffness_gpa": dict(zip("xyz", st)), "strength_mpa": dict(zip("xyz", sg)),
                                    "rel_density": table.densities[i]}, modes={"weight": "about"})
        res = eng.run(req, None, None, search_kwargs={"pool_idx": pool_idx})
        matched += bool(res["candidates"] and res["candidates"][0]["matches_targets"])
    assert covered >= 9, f"picker: {covered}/10 covered"
    assert matched >= 9, f"search: {matched}/10 matched"
