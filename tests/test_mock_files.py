"""T4: every file in mock/ validates against the Pydantic models; mock mode serves the whole API."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.mock import with_predicted_governing
from server import units
from server.app import app
from server.finalize import finalize_candidates
from server.schemas import Candidate, JobResponse, Material

MOCK = Path(__file__).resolve().parent.parent / "mock"


def test_mock_folder_has_the_expected_files():
    names = {p.name for p in MOCK.glob("*.json")}
    assert {"materials.json", "job_done.json"} <= names
    assert {f"sample_{n}.json" for n in range(3, 10)} <= names


def test_materials_json_validates_and_matches_units():
    mats = [Material(**m) for m in json.loads((MOCK / "materials.json").read_text(encoding="utf-8"))]
    assert [m.model_dump() for m in mats] == list(units.MATERIALS.values())


def test_job_done_validates_and_is_real_output():
    raw = json.loads((MOCK / "job_done.json").read_text(encoding="utf-8"))
    job = JobResponse(**raw)
    assert job.status.value == "done" and len(job.candidates) == 5
    assert job.rounds and job.reach["level"] in ("covered", "extended", "outside", "infeasible")
    assert job.candidates[0].matches_targets and job.candidates[0].mass_g > 0
    sample = json.loads((MOCK / "sample_3.json").read_text(encoding="utf-8"))
    assert raw["candidates"][0]["verified"]["stiffness_gpa"] == sample["candidates"][0]["verified"]["stiffness_gpa"]
    json.dumps(raw, allow_nan=False)


@pytest.mark.parametrize("path", sorted(MOCK.glob("sample_*.json")), ids=lambda p: p.name)
def test_each_sample_candidate_validates_as_a_candidate(path):
    d = json.loads(path.read_text(encoding="utf-8"))
    assert set(d) >= {"material", "rounds", "infeasible", "candidates"}
    mat = units.MATERIALS["ti64"]
    cands = [with_predicted_governing(c) for c in d["candidates"]]
    for c in finalize_candidates(cands, "j_x", None, mat, [40, 40, 40], 10):
        Candidate(**c)


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_mock_mode_serves_health_materials_limits_reach(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["model_loaded"] is False
    assert client.get("/api/materials").json() == json.loads((MOCK / "materials.json").read_text(encoding="utf-8"))
    assert client.get("/api/limits").status_code == 200
    r = client.post("/api/reach", json={"material": "ti64", "target": {"stiffness_gpa": {"x": 0.4, "y": 0.4, "z": 0.4}}})
    assert r.status_code == 200 and r.json()["level"] in ("covered", "extended")


def test_mock_job_walks_four_stages_and_returns_real_candidates(client):
    body = {"material": "ti64", "part": {"size_mm": [40, 40, 40], "cell_mm": 10},
            "target": {"stiffness_gpa": {"x": 0.465, "y": 0.496, "z": 0.402},
                       "strength_mpa": {"x": 2.22, "y": 2.65, "z": 2.19}, "rel_density": 0.05},
            "modes": {"weight": "about"}}
    jid = client.post("/api/designs", json=body).json()["job_id"]
    import time
    for _ in range(100):
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert j["status"] == "done", j["message"]
    assert len(j["candidates"]) == 5 and j["candidates"][0]["matches_targets"]
    assert j["rounds"][0]["matched"]
    json.dumps(j, allow_nan=False)
