"""T11: five stored demo targets that load without the GPU."""
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import core
from core.mock import MockEngine
from server import demo
from server.app import app
from server.schemas import Candidate, DesignRequest

DEMO = Path(__file__).resolve().parent.parent / "demo"
INDEX = json.loads((DEMO / "index.json").read_text(encoding="utf-8"))


@pytest.fixture
def client():
    demo._installed = False
    return TestClient(app)


def test_five_demo_jobs_are_stored_with_real_matching_results():
    assert len(INDEX) == 5
    for d in INDEX:
        folder = DEMO / "jobs" / d["job_id"]
        results = json.loads((folder / "results.json").read_text(encoding="utf-8"))
        req = DesignRequest(**json.loads((folder / "request.json").read_text(encoding="utf-8")))
        assert req.target.max_mass_g
        cands = [Candidate(**c) for c in results]
        assert cands and cands[0].matches_targets and cands[0].match_error_pct < 10
        assert all(c.id.startswith(d["job_id"]) and c.mass_g > 0 and c.verified for c in cands)
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        assert meta["rounds"][0]["matched"] and meta["reach"]["level"] in ("covered", "extended")
        json.dumps(results, allow_nan=False)


@pytest.mark.parametrize("d", INDEX, ids=lambda d: d["job_id"])
def test_posting_a_demo_target_returns_the_stored_job_without_a_gpu(client, d):
    body = json.loads((DEMO / "jobs" / d["job_id"] / "request.json").read_text(encoding="utf-8"))
    r = client.post("/api/designs", json=body)
    assert r.status_code == 202 and r.json() == {"job_id": d["job_id"], "status": "done"}
    j = client.get(f"/api/jobs/{d['job_id']}").json()
    assert j["status"] == "done" and j["candidates"][0]["matches_targets"] and j["rounds"]
    assert j["request"]["target"] == body["target"]
    one = client.get(f"/api/designs/{j['candidates'][0]['id']}")
    assert one.status_code == 200 and one.json()["verified"]["stiffness_gpa"]


class _Down:
    ok = False
    status = {"ok": False, "reason": "GPU out of memory"}

    def health(self):
        return {"model_loaded": False, "gpu": False, "solver_workers": 0, "reason": "GPU out of memory"}


class _Up(MockEngine):
    pass


def test_demo_served_when_real_engine_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(core, "MOCK", False)
    monkeypatch.setattr(core, "_engine", _Down())
    monkeypatch.setattr(core, "_hash", "whatever")
    d = INDEX[0]
    body = json.loads((DEMO / "jobs" / d["job_id"] / "request.json").read_text(encoding="utf-8"))
    assert client.post("/api/designs", json=body).json()["job_id"] == d["job_id"]


def test_demo_not_served_over_a_working_engine_with_different_models(client, monkeypatch):
    """A stored result made with other model files must not be shown as if the current models produced it."""
    monkeypatch.setattr(core, "MOCK", False)
    up = _Up()
    monkeypatch.setattr(core, "_engine", up)
    monkeypatch.setattr(core, "_real_hash", "other-models")
    monkeypatch.setattr(core, "_hash", "other-models")
    d = INDEX[1]
    body = json.loads((DEMO / "jobs" / d["job_id"] / "request.json").read_text(encoding="utf-8"))
    r = client.post("/api/designs", json=body)
    assert r.status_code == 202 and r.json()["job_id"] != d["job_id"]


def test_dev_script_is_valid_powershell():
    import subprocess
    script = Path(__file__).resolve().parent.parent / "scripts" / "dev.ps1"
    cmd = f"$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('{script}',[ref]$null,[ref]$e); if($e){{$e; exit 1}}"
    out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr


def test_health_reports_why_the_models_are_not_loaded(client, monkeypatch):
    monkeypatch.setattr(core, "_engine", _Down())
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["model_loaded"] is False and h["reason"] == "GPU out of memory"
