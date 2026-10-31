"""Regression tests for the bugs found in the backend review."""
import time

import pytest
from fastapi.testclient import TestClient

from server.app import app
from server.store import create_job, fail_stale_jobs, get_job, init_db

BASE = {
    "material": "ti64",
    "part": {"size_mm": [40, 40, 40], "cell_mm": 10},
    "target": {"stiffness_gpa": {"x": 8, "y": 8, "z": 12}, "max_mass_g": 150},
}


@pytest.fixture
def client():
    init_db()
    return TestClient(app)


def _with(**over):
    out = {**BASE}
    for k, v in over.items():
        out[k] = v
    return out


@pytest.mark.parametrize("payload", [
    _with(part={"size_mm": [0, 40, 40], "cell_mm": 10}),
    _with(part={"size_mm": [-40, 40, 40], "cell_mm": 10}),
    _with(part={"size_mm": [5, 5, 5], "cell_mm": 10}),
    _with(tolerance_pct=-5),
    _with(tolerance_pct=900),
    _with(n_results=100000),
    _with(target={"stiffness_gpa": {"x": -8, "y": 8, "z": 12}}),
    _with(target={"stiffness_gpa": {"x": 0, "y": 8, "z": 12}}),
    _with(target={"max_mass_g": 100}),                      # no stiffness or strength at all
    _with(target={"stiffness_gpa": {}, "max_mass_g": 100}),
    _with(target={"stiffness_gpa": {"x": 8}, "max_mass_g": -1}),
])
def test_bad_requests_are_rejected_up_front(client, payload):
    assert client.post("/api/designs", json=payload).status_code == 422


def test_nan_is_rejected(client):
    r = client.post("/api/designs", content='{"material":"ti64","part":{"size_mm":[40,40,40],"cell_mm":10},"target":{"stiffness_gpa":{"x":NaN}}}',
                    headers={"content-type": "application/json"})
    assert r.status_code == 422


def test_unknown_job_is_404_for_status_and_events(client):
    assert client.get("/api/jobs/j_nope").status_code == 404
    assert client.get("/api/jobs/j_nope/events").status_code == 404


def test_unknown_design_is_404(client):
    assert client.get("/api/designs/does_not_exist").status_code == 404


def _run(client, payload):
    jid = client.post("/api/designs", json=payload).json()["job_id"]
    for _ in range(200):
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] in ("done", "failed"):
            return jid, j
        time.sleep(0.1)
    raise AssertionError("job did not finish")


def test_candidate_ids_are_unique_per_job_and_resolvable(client):
    jid1, j1 = _run(client, BASE)
    jid2, j2 = _run(client, {**BASE, "tolerance_pct": 11})        # a different request: an identical one is cached
    ids1 = [c["id"] for c in j1["candidates"]]
    ids2 = [c["id"] for c in j2["candidates"]]
    assert ids1 and len(set(ids1)) == len(ids1)
    assert not set(ids1) & set(ids2)
    assert all(i.startswith(jid1) for i in ids1)
    got = client.get(f"/api/designs/{ids1[0]}")
    assert got.status_code == 200 and got.json()["id"] == ids1[0]


def test_request_is_saved_and_returned(client):
    _, j = _run(client, BASE)
    assert j["request"]["target"]["max_mass_g"] == 150
    assert j["request"]["part"]["cell_mm"] == 10


def test_events_stream_works_for_two_listeners(client):
    jid, _ = _run(client, BASE)
    for _ in range(2):
        with client.stream("GET", f"/api/jobs/{jid}/events") as s:
            text = " ".join(s.iter_lines())
        assert "event: close" in text and '"status": "done"' in text


def test_restart_marks_unfinished_jobs_failed(client):
    create_job("j_stale_running", status="running", stage="search", progress=0.3, message="x")
    create_job("j_stale_done", status="done", stage="rank", progress=1.0, message="ok")
    assert fail_stale_jobs() >= 1
    assert get_job("j_stale_running")["status"] == "failed"
    assert get_job("j_stale_done")["status"] == "done"


def test_works_from_any_working_directory(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    jid, j = _run(client, BASE)
    assert j["status"] == "done"
    assert not (tmp_path / "runs").exists()
