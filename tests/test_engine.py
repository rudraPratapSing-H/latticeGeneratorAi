"""core.engine: startup never raises; the ladder, stop and budget rules (fake search); a real GPU check."""
import pytest

import search_design as sd
from core import engine as eng_mod
from core.engine import Engine, EngineUnavailable, load_engine


def test_load_engine_with_missing_files_does_not_raise(tmp_path):
    e = load_engine(tmp_path)
    assert not e.ok
    assert "missing" in e.status["reason"] and "results/best_model.pt" in e.status["reason"]
    assert e.health()["model_loaded"] is False and e.health()["gpu"] is False


def test_load_engine_reports_lfs_pointer(tmp_path):
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "best_model.pt").write_text("version https://git-lfs.github.com/spec/v1\nsize 9\n")
    e = load_engine(tmp_path)
    assert not e.ok and "Git LFS pointer" in e.status["reason"] and "git lfs pull" in e.status["reason"]


def test_run_on_unloaded_engine_raises_with_reason(tmp_path):
    e = load_engine(tmp_path)
    with pytest.raises(EngineUnavailable):
        e.run({})


def test_importing_core_does_not_import_torch():
    import subprocess, sys
    code = "import sys, core, core.engine; assert 'torch' not in sys.modules and 'search_design' not in sys.modules"
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0


# ---- ladder behaviour of the real search_adaptive with a fake run_search (no torch) ----
def _fake(monkeypatch, errs, calls, seconds=0.0):
    def fake_run_search(*a, K=100, **kw):
        calls.append(K)
        e = errs[len(calls) - 1]
        return [{"max_err": e, "match": e <= 0.1}]
    monkeypatch.setattr(sd, "run_search", fake_run_search)


def _adaptive(**kw):
    return sd.search_adaptive(None, None, None, None, None, None, "cpu", **kw)


def test_ladder_stops_on_match(monkeypatch):
    calls = []
    _fake(monkeypatch, [0.5, 0.05, 0.01], calls)
    cands, hist = _adaptive(time_budget=60)
    assert calls == [100, 300] and hist[-1]["matched"]


def test_ladder_stops_when_round_gains_less_than_half_a_point(monkeypatch):
    calls = []
    _fake(monkeypatch, [0.5, 0.3, 0.298, 0.0], calls)
    _adaptive(time_budget=60)
    assert calls == [100, 300, 1000]  # round 2 gained 20 points, round 3 is allowed; then ladder ends
    calls.clear()
    _fake(monkeypatch, [0.5, 0.499, 0.0], calls)
    _adaptive(time_budget=60)
    assert calls == [100, 300]       # round 2 gained 0.1 points -> stop before K=1000


def test_should_stop_checked_between_rounds(monkeypatch):
    calls = []
    _fake(monkeypatch, [0.5, 0.4, 0.3], calls)
    stop = {"now": False}
    def on_round(row, c):
        stop["now"] = True
    cands, hist = _adaptive(should_stop=lambda: stop["now"], on_round=on_round)
    assert calls == [100] and len(hist) == 1
    calls.clear()
    cands, hist = _adaptive(should_stop=lambda: True)
    assert calls == [] and cands == [] and hist == []


def test_time_budget_prevents_overrunning_round(monkeypatch):
    import time
    calls = []
    def slow(*a, K=100, **kw):
        calls.append(K); time.sleep(0.2)
        return [{"max_err": 0.5 - 0.1 * len(calls), "match": False}]
    monkeypatch.setattr(sd, "run_search", slow)
    # 0.2 s for K=100 -> K=300 projected ~0.6 s, over a 0.3 s budget
    _adaptive(time_budget=0.3)
    assert calls == [100]


@pytest.mark.gpu
def test_gpu_sample3_request_matches_in_round_one():
    """The request behind sample_3.json (titanium, density 0.05): matches in round 1 with error under 10%."""
    from server.schemas import DesignRequest
    e = load_engine()
    assert e.ok, e.status["reason"]
    req = DesignRequest(material="ti64", part={"size_mm": [40, 40, 40], "cell_mm": 10},
                        target={"stiffness_gpa": {"x": 0.465, "y": 0.496, "z": 0.402},
                                "strength_mpa": {"x": 2.22, "y": 2.65, "z": 2.19}, "rel_density": 0.05},
                        modes={"weight": "about"})
    events = []
    res = e.run(req, events.append, None)
    assert res["request"]["material"] == "ti64"
    assert res["rounds"][0]["matched"] and res["rounds"][0]["round"] == 1
    assert res["candidates"][0]["match_error_pct"] < 10 and res["candidates"][0]["mass_g"] > 0
    assert any(ev["stage"] == "verify" for ev in events)


@pytest.mark.gpu
def test_gpu_cancel_before_first_round_returns_empty():
    from server.schemas import DesignRequest
    e = load_engine()
    req = DesignRequest(material="ti64", part={"size_mm": [40, 40, 40], "cell_mm": 10},
                        target={"stiffness_gpa": {"x": 1, "y": 1, "z": 1}})
    res = e.run(req, None, lambda: True)
    assert res["stopped"] and res["candidates"] == []
