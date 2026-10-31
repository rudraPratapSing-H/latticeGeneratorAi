"""The multi-core solver gives the same numbers as the single-core one."""
import json
from pathlib import Path

import numpy as np
import pytest

SAMPLE = Path(__file__).resolve().parent.parent / "sample_3.json"


def test_pick_workers_is_at_least_one(monkeypatch):
    from core import solver_pool
    monkeypatch.delenv("WORKERS", raising=False)
    n, why = solver_pool.pick_workers()
    assert n >= 1 and isinstance(why, str)
    monkeypatch.setenv("WORKERS", "3")
    assert solver_pool.pick_workers()[0] == 3


@pytest.mark.skipif(not SAMPLE.exists(), reason="needs sample_3.json from a real run")
def test_pool_matches_serial():
    pytest.importorskip("search_design")
    from core import solver_pool
    d = json.loads(SAMPLE.read_text())
    c = d[0] if isinstance(d, list) else d["candidates"][0]
    pos = np.array(c["lattice"]["nodes"])
    adj = np.zeros((len(pos), len(pos)), int)
    for a, b in c["lattice"]["edges"]:
        adj[a, b] = adj[b, a] = 1
    tasks = [(adj, pos, r) for r in (0.05, 0.1, 0.15, 0.2, 0.25)] * 4
    serial = [solver_pool.solve_task(t) for t in tasks]
    pool = solver_pool.make_pool(2)
    try:
        par = list(pool.map(solver_pool.solve_task, tasks, chunksize=2))
    finally:
        pool.shutdown()
    assert all(np.allclose(a["E"], b["E"]) and np.allclose(a["y"], b["y"]) for a, b in zip(serial, par))
