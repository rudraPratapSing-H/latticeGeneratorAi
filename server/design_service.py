"""Queue one design job (shared by POST /api/designs and the implant zone searches)."""
from __future__ import annotations

import uuid
from typing import Any

from server import demo, preflight
from server.finalize import sanitize
from server.jobs import runner
from server.schemas import DesignRequest
from server.store import create_job, find_by_cache_key, save_request, update_job_status


def submit_design(payload: DesignRequest, extra_meta: dict[str, Any] | None = None) -> dict[str, str]:
    """Check against the dataset (BadTarget -> 422), reuse an identical earlier job, otherwise queue. Raises jobs.QueueFull."""
    pre = preflight.run(payload)
    same = find_by_cache_key(pre.cache_key) or demo.find(payload)
    if same is not None:
        return same
    job_id = f"j_{uuid.uuid4().hex[:8]}"
    save_request(job_id, payload.model_dump(mode="json"))
    reach_meta = None
    if pre.reach is not None:
        reach_meta = {k: pre.reach[k] for k in ("level", "distance_pct", "density", "nearest", "bounds", "message")}
    create_job(job_id=job_id, status="queued", stage=None, progress=0.0, message="Job queued for processing",
               meta=sanitize({"cache_key": pre.cache_key, "warnings": pre.warnings, "reach": reach_meta, "kind": "design",
                              **(extra_meta or {})}))
    try:
        runner.submit(job_id, payload)
    except Exception as e:  # QueueFull: the job row must not stay "queued" forever
        update_job_status(job_id, status="failed", message=str(e))
        raise
    return {"job_id": job_id, "status": "queued"}
