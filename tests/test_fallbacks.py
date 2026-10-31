"""Phase A leftovers: CUDA out-of-memory retry and CPU fallback, nearest-stored-lattice fallback, clean exit."""
import copy
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

import core
import search_design as sd
from core import reach
from core.engine import Engine, is_out_of_memory
from core.mock import MockEngine
from server import units
from server.app import app
from server.finalize import finalize_candidates
from server.schemas import Candidate

ROOT = Path(__file__).resolve().parent.parent
MAT = units.MATERIALS["ti64"]


def spec(**over):
    base = {"material": MAT, "stiffness_gpa": [1.0, 1.0, 1.0], "strength_mpa": [5.0, 5.0, 5.0],
            "yield_strength_mpa": None, "rho": None, "rho_max": 0.15,
            "modes": {"stiffness": "about", "strength": "at_least", "weight": "at_most"}, "tol": 0.10,
            "cell_mm": 10.0, "part_mm": [40, 40, 40]}
    return {**base, **over}


class FakeModule:
    def __init__(self):
        self.moved_to = []

    def to(self, device):
        self.moved_to.append(device)
        return self


class FakeTensor(FakeModule):
    pass


def fake_engine(code_ids=None):
    e = Engine()
    e._s = dict(vae=FakeModule(), cmod=FakeModule(),
                pred=dict(net=FakeModule(), x_mean=FakeTensor(), x_std=FakeTensor(), y_mean=FakeTensor(), y_std=FakeTensor()),
                mask=None, codes=np.zeros((5, 48)), code_ids=code_ids, device="cuda:0", pool=None, workers=1)
    e.status = {"ok": True, "reason": None, "device": "cuda:0", "workers": 1}
    return e


OOM = RuntimeError("CUDA out of memory. Tried to allocate 20.00 MiB")


def patch_search(monkeypatch, errors):
    calls = []

    def fake(*a, ladder=None, **kw):
        calls.append({"ladder": list(ladder), "device": a[6]})
        if errors and len(calls) <= len(errors):
            raise errors[len(calls) - 1]
        return [], [{"round": 1, "K": ladder[0], "best_err": 0.5, "matched": False, "n_candidates": 0,
                     "round_seconds": 0.1, "elapsed_seconds": 0.1}]

    monkeypatch.setattr(sd, "search_adaptive", fake)
    return calls


def test_is_out_of_memory():
    assert is_out_of_memory(OOM) and not is_out_of_memory(RuntimeError("something else"))


def test_oom_once_retries_with_half_the_starts_on_the_gpu(monkeypatch):
    calls = patch_search(monkeypatch, [OOM])
    e = fake_engine()
    res = e.run(spec())
    assert [c["ladder"] for c in calls] == [[100, 300, 1000], [50, 150, 500]]
    assert calls[1]["device"] == "cuda:0" and e.status["device"] == "cuda:0"
    assert res["rounds"] and not res["stopped"]


def test_oom_twice_falls_back_to_the_cpu(monkeypatch):
    calls = patch_search(monkeypatch, [OOM, OOM])
    e = fake_engine()
    res = e.run(spec())
    assert [c["ladder"] for c in calls] == [[100, 300, 1000], [50, 150, 500], [50, 150, 500]]
    assert calls[2]["device"] == "cpu"
    assert e.status["device"] == "cpu" and e.health()["gpu"] is False
    assert e._s["vae"].moved_to == ["cpu"] and e._s["pred"]["net"].moved_to == ["cpu"]
    assert e._s["pred"]["x_mean"].moved_to == ["cpu"]
    assert res["rounds"]


def test_oom_on_the_cpu_too_is_raised(monkeypatch):
    patch_search(monkeypatch, [OOM, OOM, OOM])
    with pytest.raises(RuntimeError, match="out of memory"):
        fake_engine().run(spec())


def test_other_errors_are_not_retried(monkeypatch):
    calls = patch_search(monkeypatch, [RuntimeError("boom")])
    with pytest.raises(RuntimeError, match="boom"):
        fake_engine().run(spec())
    assert len(calls) == 1


# ---- nearest stored lattices
def test_no_candidates_runs_the_stored_lattice_fallback_with_the_picker_ids(monkeypatch):
    patch_search(monkeypatch, [])
    table = reach.get_table()
    request = spec(stiffness_gpa=[20.0, 20.0, 20.0], strength_mpa=None, rho_max=0.25)      # far outside the data
    ids, density = table.nearest_ids(MAT, n=20, stiffness=request["stiffness_gpa"], strength=None,
                                     modes=request["modes"], tol=0.1, rho_max=0.25)
    assert len(ids) == 20 and density == 0.25
    code_ids = np.concatenate([ids[:7], np.arange(10_000_000, 10_000_050)])       # 7 of the nearest are in the codes file
    seen = {}

    def fake_run_search(vae, cmod, pred, mask, codes, tg, device, **kw):
        seen.update(kw)
        return []

    monkeypatch.setattr(sd, "run_search", fake_run_search)
    e = fake_engine(code_ids=code_ids)
    res = e.run(request)
    assert res["candidates"] == [] and res["fallback"] is None                       # nothing decodable: still honest
    assert seen["use_gradient"] is False                                              # no steering: stored lattices as they are
    assert seen["K"] == 7 and list(seen["pool_idx"]) == list(range(7))


def test_fallback_candidates_are_labelled_nearest_stored_and_never_called_a_match():
    cand = MockEngine().run(spec())["candidates"][0]
    cand = copy.deepcopy(cand)
    cand["origin"] = "stored"
    cand["matches_targets"] = False
    out = finalize_candidates([cand], "j_x", None, MAT, [40, 40, 40], 10.0)[0]
    assert out["source"] == "nearest_stored"
    assert out["warnings"][0].startswith("Nearest stored lattice") and "Not a match" in out["warnings"][0]
    Candidate(**out)
    gen = finalize_candidates([{**copy.deepcopy(cand), "origin": "steered"}], "j_y", None, MAT, [40, 40, 40], 10.0)[0]
    assert gen["source"] == "generated" and not any("stored" in w for w in gen["warnings"])


class _FallbackEngine(MockEngine):
    def run(self, request, *a, **kw):
        res = super().run(request, *a, **kw)
        for c in res["candidates"]:
            c["origin"] = "stored"
            c["matches_targets"] = False
        res["fallback"] = "nearest_stored"
        return res


def test_job_reports_the_fallback(monkeypatch):
    monkeypatch.setenv("MOCK_STAGE_DELAY", "0")
    monkeypatch.setattr(core, "_engine", _FallbackEngine())
    c = TestClient(app)
    body = {"material": "ti64", "part": {"size_mm": [40, 40, 40], "cell_mm": 10},
            "target": {"stiffness_gpa": {"x": 0.465, "y": 0.496, "z": 0.402}, "rel_density": 0.05},
            "modes": {"weight": "about"}, "tolerance_pct": 10.0777}
    jid = c.post("/api/designs", json=body).json()["job_id"]
    for _ in range(200):
        j = c.get(f"/api/jobs/{jid}").json()
        if j["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert j["status"] == "done" and "nearest stored lattices" in j["message"]
    assert j["candidates"] and all(x["source"] == "nearest_stored" and x["matches_targets"] is False for x in j["candidates"])


# ---- real models (GPU laptop): pytest -q -m gpu tests/test_fallbacks.py
@pytest.mark.gpu
def test_gpu_far_outside_target_with_empty_search_returns_verified_stored_lattices(monkeypatch):
    from core.engine import load_engine
    eng = load_engine()
    assert eng.ok, eng.status["reason"]
    monkeypatch.setattr(sd, "search_adaptive", lambda *a, **kw: ([], []))             # the search finds nothing at all
    res = eng.run(spec(stiffness_gpa=[20.0, 20.0, 20.0], strength_mpa=None, rho_max=0.25))
    assert res["fallback"] == "nearest_stored" and res["candidates"]
    for c in res["candidates"]:
        assert c["origin"] == "stored" and c["verified"]["stiffness_gpa"]["x"] > 0
        assert c["matches_targets"] is False                                           # 20 GPa per axis is beyond any lattice
    finals = finalize_candidates(res["candidates"], "j_gpu", None, MAT, [40, 40, 40], 10.0)
    for c in finals:
        Candidate(**c)
        assert c["source"] == "nearest_stored" and "Not a match" in c["warnings"][0]
    best = max(c["verified"]["stiffness_gpa"]["x"] for c in res["candidates"])
    assert best > 5.0                                                                 # the stiffest stored lattices at 0.25


@pytest.mark.gpu
def test_gpu_interpreter_exit_is_clean_with_a_live_solver_pool():
    code = ("import sys; sys.path.insert(0, r'%s')\n"
            "if __name__ == '__main__':\n"
            "    from core.engine import load_engine\n"
            "    e = load_engine(); print('loaded', e.ok)\n" % ROOT)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT, timeout=240)
    assert "loaded True" in out.stdout, out.stdout + out.stderr
    assert out.returncode == 0
    assert "AttributeError" not in out.stderr and "Exception ignored" not in out.stderr, out.stderr
