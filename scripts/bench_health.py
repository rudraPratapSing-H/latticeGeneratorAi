"""Measure /api/health latency while a real search runs (plan: under 100 ms).

    python scripts/bench_health.py [--samples 40] [--ladder 300]

Starts its own server on a free port with K_LADDER=<ladder> (default one K=300 round), submits a job, calls /api/health
every 0.4 s while the job runs, prints min / median / p95 / max in ms. Needs the GPU laptop. Stop other busy programs first.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BODY = {"material": "ti64", "part": {"size_mm": [40, 40, 40], "cell_mm": 10},
        "target": {"stiffness_gpa": {"x": 1.2, "y": 1.4, "z": 1.1}, "strength_mpa": {"x": 8, "y": 9, "z": 7.5},
                   "max_mass_g": 43.4},
        "modes": {"stiffness": "about", "strength": "at_least", "weight": "at_most"}, "tolerance_pct": 10.123}


def get(url: str):
    t = time.perf_counter()
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data, (time.perf_counter() - t) * 1000.0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--samples", type=int, default=40)
    ap.add_argument("--ladder", default="300")
    a = ap.parse_args(argv)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {k: v for k, v in os.environ.items() if k not in ("MOCK", "MOCK_STAGE_DELAY")}
    env.update(RUNS_DIR=tempfile.mkdtemp(prefix="lattice_bench_"), K_LADDER=a.ladder)
    log = open(Path(env["RUNS_DIR"]) / "server.log", "w+b")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "server.app:app", "--port", str(port)], cwd=ROOT, env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(300):
            try:
                if get(f"{base}/api/health")[0].get("model_loaded"):
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            print("models did not load"); return 1
        idle = [get(f"{base}/api/health")[1] for _ in range(10)]
        req = urllib.request.Request(f"{base}/api/designs", data=json.dumps(BODY).encode(),
                                     headers={"Content-Type": "application/json"})
        jid = json.loads(urllib.request.urlopen(req, timeout=30).read())["job_id"]
        busy, t0 = [], time.time()
        while True:
            job, _ = get(f"{base}/api/jobs/{jid}")
            if job["status"] == "running" and job.get("stage") in ("search", "repair", "verify"):
                busy.append(get(f"{base}/api/health")[1])
            if job["status"] in ("done", "failed", "cancelled"):
                break
            time.sleep(0.4)
        secs = time.time() - t0
        rounds = job.get("rounds") or []
        pct = lambda xs, p: sorted(xs)[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]  # noqa: E731
        print(f"job {job['status']} in {secs:.0f}s, rounds {[(r['k'], r['matched']) for r in rounds]}")
        for name, xs in (("idle", idle), ("during search", busy)):
            if xs:
                print(f"{name:14} n={len(xs):3d} min {min(xs):6.1f}  median {statistics.median(xs):6.1f}  "
                      f"p95 {pct(xs, 0.95):6.1f}  max {max(xs):6.1f} ms")
        return 0 if busy and len(busy) >= min(20, a.samples) else 2
    finally:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        else:
            proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
