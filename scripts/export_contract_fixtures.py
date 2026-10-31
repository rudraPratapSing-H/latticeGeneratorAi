"""Write what the REAL backend sends (its serializers, validators and SSE framing) for the frontend to test against.

    python scripts/export_contract_fixtures.py [--out lattice-web/src/test/fixtures/backend]

Runs the FastAPI app in mock mode (same code paths and schemas as real mode; only the engine differs, and its
candidates are stored real runs). Writes one JSON file per response plus openapi.json and an SSE transcript.
The frontend's mock fixtures should be copied from these files, never typed by hand.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["MOCK"] = "1"
os.environ["RUNS_DIR"] = tempfile.mkdtemp(prefix="lattice_contract_")
os.environ["MOCK_STAGE_DELAY"] = "0.35"
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import server.app as app_mod  # noqa: E402
import server.jobs as jobs_mod  # noqa: E402
from server.store import create_job, fail_stale_jobs  # noqa: E402

GOOD = {"material": "ti64", "part": {"size_mm": [40, 40, 40], "cell_mm": 10},
        "target": {"stiffness_gpa": {"x": 0.465, "y": 0.496, "z": 0.402},
                   "strength_mpa": {"x": 2.22, "y": 2.65, "z": 2.19}, "rel_density": 0.05},
        "modes": {"stiffness": "about", "strength": "at_least", "weight": "about"}, "tolerance_pct": 10, "n_results": 5}
INFEASIBLE = {**GOOD, "target": {"stiffness_gpa": {"x": 20, "y": 20, "z": 20}, "max_mass_g": 60},
              "modes": {"stiffness": "about", "strength": "at_least", "weight": "at_most"}}
MISS = {**GOOD, "target": {"stiffness_gpa": {"x": 1.45, "y": 3.32, "z": 3.35},
                           "strength_mpa": {"x": 11.6, "y": 23.8, "z": 19.8}, "rel_density": 0.25}}


def wait(c: TestClient, jid: str, states=("done", "failed", "cancelled")) -> dict:
    for _ in range(400):
        j = c.get(f"/api/jobs/{jid}").json()
        if j["status"] in states:
            return j
        time.sleep(0.05)
    raise SystemExit(f"job {jid} did not reach {states}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "lattice-web" / "src" / "test" / "fixtures" / "backend")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    c = TestClient(app_mod.app)

    def save(name: str, data) -> None:
        (a.out / f"{name}.json").write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")

    save("openapi", c.get("/openapi.json").json())
    save("health", c.get("/api/health").json())
    save("materials", c.get("/api/materials").json())
    save("limits", c.get("/api/limits?material=ti64").json())
    save("reach_covered", c.post("/api/reach", json=GOOD).json())
    save("reach_infeasible", c.post("/api/reach", json=INFEASIBLE).json())
    r = c.post("/api/designs", json=GOOD)
    save("create_design", r.json())
    first = r.json()["job_id"]

    # a second, different request queues behind the first
    queued_body = {**GOOD, "tolerance_pct": 10.5}
    q = c.post("/api/designs", json=queued_body).json()["job_id"]
    save("job_queued", c.get(f"/api/jobs/{q}").json())
    time.sleep(0.5)
    save("job_running", wait(c, first, states=("running",)))
    save("job_done", wait(c, first))
    # cancelled
    cancel_body = {**GOOD, "tolerance_pct": 10.6}
    cid = c.post("/api/designs", json=cancel_body).json()["job_id"]
    wait(c, q)
    wait(c, cid, states=("running",))
    save("cancel_response", c.post(f"/api/jobs/{cid}/cancel").json())
    save("job_cancelled", wait(c, cid))
    # failed (restart) and a job that missed its target
    create_job("j_contract_failed", status="running", progress=0.3)
    fail_stale_jobs()
    save("job_failed", c.get("/api/jobs/j_contract_failed").json())
    mid = c.post("/api/designs", json=MISS).json()["job_id"]
    save("job_no_match", wait(c, mid))
    done = wait(c, first)
    save("design", c.get(f"/api/designs/{done['candidates'][0]['id']}").json())

    # error bodies
    save("error_422_infeasible", c.post("/api/designs", json=INFEASIBLE).json())
    save("error_422_schema", c.post("/api/designs", json={**GOOD, "tolerance_pct": 900}).json())
    save("error_422_unit_hint", c.post("/api/designs", json={**GOOD, "target": {"stiffness_gpa": {"x": 8000}}}).json())
    save("error_422_unknown_material", c.post("/api/designs", json={**GOOD, "material": "zzz"}).json())
    save("error_404", c.get("/api/jobs/j_nope").json())
    jobs_mod.MAX_QUEUE = 0
    r429 = c.post("/api/designs", json={**GOOD, "tolerance_pct": 10.7})
    jobs_mod.MAX_QUEUE = 10
    save("error_429", r429.json())
    (a.out / "status_codes.json").write_text(json.dumps({"error_429": r429.status_code, "create_design": r.status_code}),
                                             encoding="utf-8")

    # SSE transcript of a finished job, with pings
    app_mod.SSE_PING_S = 0.2
    sid = c.post("/api/designs", json={**GOOD, "tolerance_pct": 10.8}).json()["job_id"]
    with c.stream("GET", f"/api/jobs/{sid}/events") as resp:
        text = "".join(resp.iter_text())
    with open(a.out / "sse_transcript.txt", "w", encoding="utf-8", newline="") as f:   # keep the server framing as is
        f.write(text)
    # what the frontend's mock mode replays: copies of real backend output, never hand-written numbers
    real = a.out.parent.parent.parent / "mocks" / "fixtures" / "real"
    real.mkdir(parents=True, exist_ok=True)
    for name in ("materials", "limits", "reach_covered", "reach_infeasible"):
        (real / f"{name}.json").write_text((a.out / f"{name}.json").read_text(encoding="utf-8"), encoding="utf-8")
    sets = []
    for d in sorted((ROOT / "demo" / "jobs").glob("j_demo_d*")):
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        sets.append({"label": d.name, "request": json.loads((d / "request.json").read_text(encoding="utf-8")),
                     "rounds": meta["rounds"], "candidates": json.loads((d / "results.json").read_text(encoding="utf-8"))})
    miss = json.loads((a.out / "job_no_match.json").read_text(encoding="utf-8"))
    sets.append({"label": "no_match", "request": miss["request"], "rounds": miss["rounds"], "candidates": miss["candidates"]})
    (real / "replay.json").write_text(json.dumps(sets, indent=1, allow_nan=False), encoding="utf-8")
    print(f"wrote {len(list(a.out.iterdir()))} files to {a.out} and the mock replay set to {real}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
