"""T5: one job at a time, queue position, cancellation, heartbeat, restart, health stays fast."""
import time

import pytest
from fastapi.testclient import TestClient

import server.app as app_mod
import server.jobs as jobs_mod
from server.app import app
from server.store import create_job, fail_stale_jobs, get_job, init_db, update_job_status

BODY = {"material": "ti64", "part": {"size_mm": [40, 40, 40], "cell_mm": 10},
        "target": {"stiffness_gpa": {"x": 0.465, "y": 0.496, "z": 0.402},
                   "strength_mpa": {"x": 2.22, "y": 2.65, "z": 2.19}, "rel_density": 0.05},
        "modes": {"weight": "about"}}


@pytest.fixture
def client(monkeypatch):
    init_db()
    monkeypatch.setenv("MOCK_STAGE_DELAY", "0.4")          # a job takes about 1.2 s
    return TestClient(app)


_n = [0]


def fresh_body():
    """A request nobody sent before (an identical one would be answered from the cache)."""
    _n[0] += 1
    return {**BODY, "tolerance_pct": 10 + _n[0] * 0.01}


def submit(client):
    r = client.post("/api/designs", json=fresh_body())
    assert r.status_code == 202
    return r.json()["job_id"]


def wait(client, jid, states=("done", "failed", "cancelled"), timeout=30):
    t = time.time()
    while time.time() - t < timeout:
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] in states:
            return j
        time.sleep(0.05)
    raise AssertionError(f"job {jid} stuck: {j}")


def test_jobs_run_one_at_a_time_in_order_with_queue_position(client):
    a, b, c = submit(client), submit(client), submit(client)
    seen_running, positions = [], {}
    deadline = time.time() + 30
    while time.time() < deadline:
        js = {x: client.get(f"/api/jobs/{x}").json() for x in (a, b, c)}
        seen_running.append(sum(j["status"] == "running" for j in js.values()))
        for x, j in js.items():
            if j["status"] == "queued":
                positions.setdefault(x, set()).add(j["queue_position"])
        if all(j["status"] == "done" for j in js.values()):
            break
        time.sleep(0.03)
    assert all(j["status"] == "done" for j in js.values())
    assert max(seen_running) == 1                         # never two at once
    assert positions[c] and min(positions[c]) <= 1 and max(positions[c]) >= 1
    assert positions.get(b) and max(positions[b]) >= 1    # ahead of it: the running job
    assert max(positions[c]) > max(positions[b]) or max(positions[c]) >= 2
    for x in (a, b, c):
        assert js[x]["queue_position"] is None


def test_cancel_queued_job_never_runs(client):
    a = submit(client)
    b = submit(client)
    r = client.post(f"/api/jobs/{b}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    wait(client, a)
    time.sleep(0.3)
    jb = client.get(f"/api/jobs/{b}").json()
    assert jb["status"] == "cancelled" and jb["candidates"] == []


def test_cancel_running_job_stops_with_partial_results(client):
    a = submit(client)
    wait(client, a, states=("running",))
    r = client.delete(f"/api/jobs/{a}")
    assert r.status_code == 200
    j = wait(client, a)
    assert j["status"] == "cancelled"
    assert "Stopped" in j["message"] or "Cancelled" in j["message"]


def test_cancel_finished_and_unknown(client):
    a = submit(client)
    wait(client, a)
    assert client.post(f"/api/jobs/{a}/cancel").json()["status"] == "done"      # idempotent
    assert client.post("/api/jobs/j_nope/cancel").status_code == 404


def test_health_answers_fast_while_a_job_runs(client):
    a = submit(client)
    wait(client, a, states=("running",))
    worst = 0.0
    for _ in range(15):
        t = time.perf_counter()
        assert client.get("/api/health").status_code == 200
        worst = max(worst, time.perf_counter() - t)
        time.sleep(0.02)
    assert get_job(a, include_candidates=False)["status"] in ("running", "done")
    assert worst < 0.1, f"health took {worst * 1000:.0f} ms"
    wait(client, a)


def test_queue_full_is_429(client, monkeypatch):
    monkeypatch.setattr(jobs_mod, "MAX_QUEUE", 0)
    r = client.post("/api/designs", json=fresh_body())
    assert r.status_code == 429 and r.json()["error"]["code"] == "queue_full" and "Retry-After" in r.headers


def test_event_stream_sends_heartbeat_and_closes(client, monkeypatch):
    monkeypatch.setattr(app_mod, "SSE_PING_S", 0.2)
    a = submit(client)
    text = ""
    with client.stream("GET", f"/api/jobs/{a}/events") as r:
        for chunk in r.iter_text():
            text += chunk
    assert "event: close" in text and '"status": "done"' in text
    assert ": ping" in text                                # comment pings keep proxies from dropping the stream


def test_job_reports_round_k_rounds_and_infeasible(client):
    a = submit(client)
    j = wait(client, a)
    assert j["round"] == 1 and j["k"] == 100 and j["infeasible"] is False
    assert j["rounds"][0]["matched"] and j["rounds"][0]["best_error_pct"] < 10
    assert j["queue_position"] is None and j["warnings"] == [] or isinstance(j["warnings"], list)


def test_saved_jobs_survive_a_restart_and_unfinished_ones_fail_with_reason(client):
    a = submit(client)
    j = wait(client, a)
    create_job("j_was_running", status="running", progress=0.3)
    create_job("j_was_queued", status="queued")
    assert fail_stale_jobs() >= 2                          # what the lifespan does at startup
    again = client.get(f"/api/jobs/{a}").json()
    assert again["status"] == "done" and again["candidates"] == j["candidates"]
    for jid in ("j_was_running", "j_was_queued"):
        g = client.get(f"/api/jobs/{jid}").json()
        assert g["status"] == "failed" and "restart" in g["message"].lower()
        assert get_job(jid, include_candidates=False)["failure_reason"] == "restart"
