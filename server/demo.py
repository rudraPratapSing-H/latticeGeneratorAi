"""Pre-run demo targets: finished jobs stored in demo/ that load without the GPU.

demo/index.json lists them; demo/jobs/<job_id>/ holds request.json, results.json and meta.json exactly as the real
pipeline wrote them (scripts/build_demo.py makes them on the GPU machine). They are copied into runs/ so
GET /api/jobs/{id} and /api/designs/{id} work for them like for any job.

A request equal to a demo request is answered with the stored job when the models are the same as when it was made,
or when the real engine is not available (mock mode, missing files, GPU trouble): the numbers are real solver output.
"""
from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path
from typing import Any

import core
from server import preflight
from server.schemas import DesignRequest
from server.store import DEFAULT_DB_PATH, DEFAULT_RUNS_DIR, create_job, get_job

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"
_lock = threading.Lock()
_installed = False


def load_index() -> list[dict[str, Any]]:
    f = DEMO_DIR / "index.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    except (OSError, json.JSONDecodeError):
        return []


def install() -> int:
    """Copy the demo jobs into runs/ and register them as finished (idempotent). Returns how many are installed."""
    global _installed
    with _lock:
        n = 0
        for d in load_index():
            src = DEMO_DIR / "jobs" / d["job_id"]
            if not (src / "results.json").exists():
                continue
            dst = Path(DEFAULT_RUNS_DIR) / d["job_id"]
            dst.mkdir(parents=True, exist_ok=True)
            for name in ("request.json", "results.json"):
                if (src / name).exists():
                    shutil.copyfile(src / name, dst / name)
            if get_job(d["job_id"], DEFAULT_DB_PATH, include_candidates=False) is None:
                meta = json.loads((src / "meta.json").read_text(encoding="utf-8"))
                create_job(d["job_id"], status="done", stage="rank", progress=1.0,
                           message=meta.pop("final_message", "Stored demo result."), meta=meta)
            n += 1
        _installed = True
        return n


def ensure_installed() -> None:
    if not _installed:
        install()


def find(request: DesignRequest) -> dict[str, Any] | None:
    """The stored demo job for this exact request, if it may be served (same models, or the engine is unavailable)."""
    ensure_installed()
    canon = preflight.canonical_request(request)
    engine_ok = False if core.MOCK else bool(core.get_engine().ok)
    for d in load_index():
        if d.get("canonical") != canon:
            continue
        same_models = d.get("model_hash") == core.real_model_hash()
        if same_models or not engine_ok:
            job = get_job(d["job_id"], DEFAULT_DB_PATH, include_candidates=False)
            if job is not None and job["status"] == "done":
                return {"job_id": d["job_id"], "status": "done"}
    return None
