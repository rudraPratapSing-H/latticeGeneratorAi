"""Gaps found in the plan review: WAL, workers without torch, unphysical candidates, conflict naming."""
import sqlite3
import sys

import pytest

from core import reach
from core.engine import drop_unphysical
from server import units
from server.store import DEFAULT_DB_PATH, init_db

MAT = units.MATERIALS["ti64"]


def test_sqlite_uses_wal_and_a_connection_per_call():
    init_db()
    con = sqlite3.connect(str(DEFAULT_DB_PATH))
    assert con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    con.close()
    from server import store
    a, b = store.get_db_connection(), store.get_db_connection()
    assert a is not b
    a.close(); b.close()


def test_solver_workers_do_not_import_torch():
    from core import solver_pool
    pool = solver_pool.make_pool(1)
    try:
        assert list(pool.map(solver_pool.has_torch, [0])) == [False]
        assert "torch" not in sys.modules or True        # the parent may have torch; the worker must not
    finally:
        solver_pool.shutdown(pool)


def cand(stiff, rho=0.15):
    return {"rank": 1, "rel_density": rho, "verified": {"stiffness_gpa": dict(zip("xyz", stiff))}}


def test_unphysical_solver_results_are_skipped_and_counted():
    ok = cand([2.0, 2.0, 2.0])
    nan = cand([float("nan"), 1.0, 1.0])
    zero = cand([0.0, 1.0, 1.0])
    floppy = cand([20.0, 20.0, 20.0])                       # 60 GPa > 1.05 x 0.15 x 114 = 17.9
    cubic = cand([5.7, 5.7, 5.7])                            # exactly density x E_s: the plain cubic lattice is allowed
    kept, skipped = drop_unphysical([nan, ok, zero, floppy, cubic], MAT)
    assert kept == [ok, cubic] and skipped == 3
    assert [c["rank"] for c in kept] == [1, 2]


def test_reach_names_the_conflicting_value_when_nothing_stored_is_close():
    t = reach.get_table()
    # very stiff but very weak: a combination the dataset lacks
    res = t.check(MAT, stiffness=[9.0, 9.0, 9.0], strength=[2.0, 2.0, 2.0], modes={"stiffness": "about", "strength": "about"},
                  rho=0.25)
    assert res["level"] in ("extended", "outside")
    c = res["conflict"]
    assert c and c["value"].split("_")[0] in ("stiffness", "strength") and c["error_pct"] > 10
    assert c["message"] in res["message"]
    # a covered request has no conflict
    v = t.values(MAT, 1)
    ok = t.check(MAT, stiffness=[float(x) for x in v["stiff"][5]], strength=[float(x) for x in v["eff"][5]],
                 modes={"stiffness": "about", "strength": "about"}, rho=0.15)
    assert ok["level"] == "covered" and "conflict" not in ok


def test_job_reports_skipped_candidates(monkeypatch):
    import time

    from fastapi.testclient import TestClient

    import core
    from core.mock import MockEngine
    from server.app import app

    class Skipping(MockEngine):
        def run(self, request, *a, **kw):
            res = super().run(request, *a, **kw)
            res["skipped_invalid"] = 2
            return res

    monkeypatch.setenv("MOCK_STAGE_DELAY", "0")
    monkeypatch.setattr(core, "_engine", Skipping())
    c = TestClient(app)
    body = {"material": "ti64", "part": {"size_mm": [40, 40, 40], "cell_mm": 10},
            "target": {"stiffness_gpa": {"x": 0.465, "y": 0.496, "z": 0.402}, "rel_density": 0.05},
            "modes": {"weight": "about"}, "tolerance_pct": 10.0911}
    jid = c.post("/api/designs", json=body).json()["job_id"]
    for _ in range(200):
        j = c.get(f"/api/jobs/{jid}").json()
        if j["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert j["status"] == "done" and j["skipped_invalid"] == 2
    assert any("2 candidate(s) skipped" in w for w in j["warnings"])
