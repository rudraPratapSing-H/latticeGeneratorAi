"""Run one full implant case against the real backend (real solver, no mock) and record the response of every step.

    python scripts/run_implant_case.py [--out mock/implant] [--weight 45] [--activity sedentary] [--no-save]

Drives the same HTTP API the frontend uses, in-process (FastAPI TestClient with the app lifespan, so the GPU pool is the
real one). Prints wall-clock seconds per stage. Responses are saved as JSON fixtures for the frontend contract tests.
Runs on the GPU when there is one, otherwise on the CPU (slower; the search then takes minutes per zone).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from scripts.make_test_stem import make_stem  # noqa: E402
from scripts.validate_implant_stl import validate  # noqa: E402
from server.app import app  # noqa: E402


def poll(client: TestClient, job_id: str, timeout: float = 1800.0) -> tuple[dict, float]:
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "failed", "cancelled"):
            return j, time.time() - t0
        time.sleep(0.5)
    raise TimeoutError(job_id)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "mock" / "implant"))
    ap.add_argument("--weight", type=float, default=45.0)
    ap.add_argument("--activity", default="sedentary")
    ap.add_argument("--no-save", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    timings: dict[str, float] = {}
    saved: dict[str, object] = {}

    def save(name: str, data) -> None:
        saved[name] = data
        if not a.no_save:
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{name}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    with TestClient(app) as c:
        desc = f"Right femoral hip stem for a {a.weight:g} kg {a.activity} patient. Keep the neck solid."
        t = time.time()
        stl = make_stem().export(file_type="stl")
        r = c.post("/api/implants", files={"stl_file": ("stem.stl", stl, "model/stl")}, data={"material": "ti64", "description": desc})
        timings["upload_and_parse"] = time.time() - t
        assert r.status_code == 201, r.text
        up = r.json()
        save("create", up)
        iid = up["implant_id"]

        t = time.time()
        r = c.post(f"/api/implants/{iid}/confirm", json={"units": "mm", "axis": "auto", "flip": False, "fields": up["fields"]})
        timings["confirm_and_zone_table"] = time.time() - t
        assert r.status_code == 200, r.text
        zt = r.json()
        save("zones", zt)
        print(f"zones: {[(z['name'], z['kind']) for z in zt['zones']]} cell {zt['cell_mm']} mm")

        t = time.time()
        jobs = c.post(f"/api/implants/{iid}/search")
        assert jobs.status_code == 200, jobs.text
        jobs = jobs.json()
        save("search", jobs)
        choices = {}
        for zid, jid in jobs.items():
            j, secs = poll(c, jid)
            timings[f"search_{zid}"] = secs
            assert j["status"] == "done", j
            cands = c.get(f"/api/implants/{iid}/zones/{zid}/candidates").json()
            save(f"candidates_{zid}", cands)
            if not cands["candidates"]:
                print(f"zone {zid}: no candidates ({j.get('message')})")
                return 2
            choices[zid] = cands["candidates"][0]["id"]
        timings["search_total_wall"] = time.time() - t

        if not choices:
            print("this load gives no lattice zone; nothing to assemble")
            return 3
        save("candidates_solid", c.get(f"/api/implants/{iid}/zones/{next(z['id'] for z in zt['zones'] if z['kind'] == 'solid')}/candidates").json()) \
            if any(z["kind"] == "solid" for z in zt["zones"]) else None

        t = time.time()
        r = c.post(f"/api/implants/{iid}/assemble", json={"choices": choices})
        assert r.status_code == 202, r.text
        aid = r.json()["job_id"]
        seen_stages: dict[str, float] = {}
        t0 = time.time()
        while True:
            j = c.get(f"/api/jobs/{aid}").json()
            seen_stages.setdefault(j.get("stage") or "queued", time.time() - t0)
            if j["status"] in ("done", "failed", "cancelled"):
                break
            time.sleep(0.2)
        timings["assemble_job_total"] = time.time() - t
        assert j["status"] == "done", j
        save("assemble_job", j)
        stage_start = dict(sorted(seen_stages.items(), key=lambda kv: kv[1]))
        print("stage first seen (s after submit):", {k: round(v, 1) for k, v in stage_start.items()})

        res = c.get(f"/api/implants/{iid}/result").json()
        save("result", res)
        t = time.time()
        stl_resp = c.get(f"/api/implants/{iid}/export.stl")
        timings["download_stl"] = time.time() - t
        path = out / "implant.stl" if not a.no_save else ROOT / "runs" / "implants" / iid / "export_check.stl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(stl_resp.content)
        src = next((ROOT / "runs" / "implants" / iid / "assemblies").glob("*/implant.shells.json"))
        path.with_name(path.stem + ".shells.json").write_bytes(src.read_bytes())
        rep = validate(path, expected_shells=len(res["parts"]))
        save("report", {"markdown": c.get(f"/api/implants/{iid}/report").text})
        print("STL:", {k: rep[k] for k in ("ok", "triangles", "shells", "problems")}, f"{len(stl_resp.content) / 1e6:.1f} MB")
        print("summary:", res["summary"])
        for z in res["zones"]:
            print(" ", z["name"], z["kind"], z.get("candidate_id"), (z.get("check") or {}).get("ratio_to_infinite"))
        if not rep["ok"]:
            return 1
    print("timings (s):", json.dumps({k: round(v, 2) for k, v in timings.items()}, indent=1))
    if not a.no_save:
        (out / "timings.json").write_text(json.dumps({"seconds": timings, "weight": a.weight, "activity": a.activity}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
