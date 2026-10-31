"""Real server, real models, over HTTP:  pytest -q -m gpu tests/test_gpu_api.py   (needs the GPU laptop)."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

BODY = {"material": "ti64", "part": {"size_mm": [40, 40, 40], "cell_mm": 10},
        "target": {"stiffness_gpa": {"x": 0.465, "y": 0.496, "z": 0.402},
                   "strength_mpa": {"x": 2.22, "y": 2.65, "z": 2.19}, "rel_density": 0.05},
        "modes": {"weight": "about"}}


def _get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


@pytest.fixture(scope="module")
def server():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {k: v for k, v in os.environ.items() if k not in ("MOCK", "MOCK_STAGE_DELAY")}
    env["RUNS_DIR"] = tempfile.mkdtemp(prefix="lattice_gpu_runs_")
    logf = open(Path(env["RUNS_DIR"]) / "server.log", "w+b")                  # a file, so a full pipe can never stall it
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "server.app:app", "--port", str(port)], cwd=ROOT, env=env,
                            stdout=logf, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(240):
            try:
                if _get(f"{base}/api/health").get("model_loaded"):
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            proc.terminate()
            raise AssertionError("models did not load: " + Path(logf.name).read_text(errors="replace")[-2000:])
        yield base
    finally:
        print(Path(logf.name).read_text(errors="replace")[-3000:])
        if os.name == "nt":                                   # also stop the solver worker processes it started
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        else:
            proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.mark.gpu
def test_real_job_over_http(server):
    health = _get(f"{server}/api/health")
    assert health["model_loaded"] and health["solver_workers"] >= 1
    status, created = _post(f"{server}/api/designs", BODY)
    assert status == 202
    jid = created["job_id"]
    worst, polls = 0.0, 0
    while True:
        t = time.perf_counter()
        _get(f"{server}/api/health")                         # the event loop must stay free while the GPU works
        worst = max(worst, time.perf_counter() - t)
        job = _get(f"{server}/api/jobs/{jid}")
        polls += 1
        if job["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.4)
    assert job["status"] == "done", job["message"]
    assert worst < 0.1, f"health took {worst * 1000:.0f} ms during a search"
    assert job["rounds"] and job["rounds"][0]["matched"] and job["reach"]["level"] in ("covered", "extended")
    best = job["candidates"][0]
    assert best["matches_targets"] and best["match_error_pct"] < 10
    assert best["mass_g"] == pytest.approx(best["rel_density"] * 64 * 4.43, abs=1e-2) and best["mass_g"] > 0
    assert best["lattice"]["strut_radius_mm"] > 0 and len(best["lattice"]["nodes"]) == 27
    assert set(best["predicted"]["governing_failure"]) == {"x", "y", "z"}
    # identical request: the stored job comes back, no new search
    status2, again = _post(f"{server}/api/designs", BODY)
    assert again["job_id"] == jid and again["status"] == "done"
    # one design by id
    assert _get(f"{server}/api/designs/{best['id']}")["id"] == best["id"]
