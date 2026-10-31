"""The Bruno collection stays true: every request returns the status its own test expects (mock mode)."""
import json
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.app import app

BRUNO = Path(__file__).resolve().parent.parent / "bruno"
FILES = sorted(p for p in BRUNO.rglob("*.bru") if p.name != "folder.bru" and p.parent.name != "environments")


def parse(path: Path):
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^(get|post|put|delete) \{\s*url: (\S+)", text, re.M)
    method, url = m.group(1), m.group(2)
    b = re.search(r"^body:json \{\n(.*?)\n\}\n", text, re.M | re.S)
    payload = json.loads(b.group(1)) if b else None
    st = re.search(r"res\.status\)\.to\.equal\((\d+)\)", text)
    return method, url, payload, int(st.group(1)) if st else None


@pytest.fixture(scope="module")
def ctx():
    client = TestClient(app)
    body = json.loads((Path(__file__).resolve().parent.parent / "demo" / "jobs" / "j_demo_d2" / "request.json").read_text("utf-8"))
    jid = client.post("/api/designs", json=body).json()["job_id"]
    for _ in range(100):
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] == "done":
            break
        time.sleep(0.05)
    return client, {"jobId": jid, "designId": j["candidates"][0]["id"]}


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(BRUNO)))
def test_request_returns_the_status_its_test_expects(ctx, path):
    client, var = ctx
    method, url, payload, expected = parse(path)
    if method == "get" and "events" in url:
        pytest.skip("SSE stream, covered in test_runner")
    url = url.replace("{{baseUrl}}", "")
    for k, v in var.items():
        url = url.replace("{{" + k + "}}", v)
    if "/cancel" in url and "j_nope" not in url:
        pass                                   # cancelling the finished demo job is idempotent
    r = client.request(method.upper(), url, json=payload)
    if expected is not None:
        assert r.status_code == expected, f"{path.name}: {r.status_code} {r.text[:300]}"
    else:
        assert r.status_code < 500
    if r.status_code >= 400 and path.parent.name == "errors":
        assert "error" in r.json() and r.json()["error"]["code"]
