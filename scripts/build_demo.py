"""Run the dataset-based demo targets (bruno/dataset_requests.json) on the REAL engine and store the finished jobs in
demo/ (committed), so the demo works without the GPU.   Needs the GPU laptop:

    python scripts/build_demo.py [--count 5] [--labels D1,D2,...]

Each job goes through the same code as the API (preflight, engine, ranking, finalize). Only targets the solver
confirmed (every target met) are kept, in file order, until --count are stored.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.pop("MOCK", None)
RUNS = tempfile.mkdtemp(prefix="lattice_demo_build_")
os.environ["RUNS_DIR"] = RUNS            # before server.store is imported: never touch the real runs/
sys.path.insert(0, str(ROOT))

import core  # noqa: E402
from server import jobs, preflight  # noqa: E402
from server.finalize import sanitize  # noqa: E402
from server.schemas import DesignRequest  # noqa: E402
from server.store import DEFAULT_DB_PATH, create_job, get_job, init_db, save_request  # noqa: E402

DEMO = ROOT / "demo"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--requests", type=Path, default=ROOT / "bruno" / "dataset_requests.json")
    a = ap.parse_args(argv)
    assert not core.MOCK, "build the demo with the real engine (unset MOCK)"
    init_db()
    print("loading engine ...", flush=True)
    eng = core.start_engine()
    if not eng.ok:
        print("engine did not load:", eng.status["reason"], file=sys.stderr)
        return 1
    mhash = core.real_model_hash()
    entries, kept = [], 0
    (DEMO / "jobs").mkdir(parents=True, exist_ok=True)
    for i, item in enumerate(json.loads(a.requests.read_text(encoding="utf-8")), 1):
        if kept >= a.count:
            break
        job_id = f"j_demo_d{i}"
        req = DesignRequest(**item["body"])
        pre = preflight.run(req)
        save_request(job_id, req.model_dump(mode="json"))
        reach_meta = {k: pre.reach[k] for k in ("level", "distance_pct", "density", "nearest", "bounds", "message")}
        create_job(job_id, status="queued", message="queued",
                   meta=sanitize({"cache_key": pre.cache_key, "warnings": pre.warnings + ["Stored demo result (real run)."],
                                  "reach": reach_meta}))
        t0 = time.time()
        jobs.run_job_sync(job_id, req)
        job = get_job(job_id)
        best = job["candidates"][0] if job["candidates"] else None
        ok = job["status"] == "done" and best is not None and best.get("matches_targets")
        print(f"D{i} {item['label']:<40} {job['status']:<9} "
              f"{'MATCH ' + str(best['match_error_pct']) + '%' if ok else 'no match'}  {time.time() - t0:.0f}s", flush=True)
        if not ok:
            continue
        dst = DEMO / "jobs" / job_id
        if dst.exists():
            shutil.rmtree(dst)
        dst.mkdir(parents=True)
        for name in ("request.json", "results.json"):
            shutil.copyfile(Path(RUNS) / job_id / name, dst / name)
        con = sqlite3.connect(str(DEFAULT_DB_PATH))
        meta = json.loads(con.execute("SELECT meta FROM jobs WHERE job_id = ?", (job_id,)).fetchone()[0])
        con.close()
        meta["final_message"] = job["message"]
        (dst / "meta.json").write_text(json.dumps(sanitize(meta), indent=2, allow_nan=False), encoding="utf-8")
        entries.append({"job_id": job_id, "label": item["label"], "source_lattice_id": item.get("source_lattice_id"),
                        "canonical": preflight.canonical_request(req), "model_hash": mhash,
                        "best_error_pct": best["match_error_pct"], "rel_density": best["rel_density"]})
        kept += 1
    (DEMO / "index.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")
    print(f"stored {kept} demo job(s) in {DEMO}")
    shutil.rmtree(RUNS, ignore_errors=True)
    return 0 if kept else 1


if __name__ == "__main__":
    sys.exit(main())
