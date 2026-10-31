"""scripts/dev.ps1 starts the API and the web app, waits for readiness, reports a busy port, and stops both."""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "dev.ps1"
WEB = next((ROOT / n for n in ("web", "lattice-web") if (ROOT / n / "package.json").exists()), None)

pytestmark = pytest.mark.skipif(os.name != "nt" or not shutil.which("powershell"), reason="Windows PowerShell script")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start(tmp_path, *args):
    out = open(tmp_path / "dev_out.txt", "w+b")
    env = {k: v for k, v in os.environ.items() if k not in ("MOCK", "MOCK_STAGE_DELAY")}
    env["RUNS_DIR"] = str(tmp_path / "runs")
    proc = subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), *args],
                            cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT)
    return proc, out


def stop(proc):
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        pass


def get(url, timeout=3):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8")


def wait_for(fn, seconds):
    t = time.time()
    last = None
    while time.time() - t < seconds:
        try:
            v = fn()
            if v:
                return v
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(0.5)
    raise AssertionError(f"timed out after {seconds}s (last error: {last})")


def port_closed(port):
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
        return False
    except OSError:
        return True


@pytest.mark.skipif(WEB is None or not (WEB / "node_modules").exists(), reason="frontend not installed (npm ci)")
def test_mock_mode_starts_api_and_web_and_stops_both(tmp_path):
    api, web = free_port(), free_port()
    proc, out = start(tmp_path, "-Mock", "-Port", str(api), "-WebPort", str(web))
    try:
        health = wait_for(lambda: json.loads(get(f"http://127.0.0.1:{api}/api/health")[1]), 90)
        assert health["status"] == "ok" and health["model_loaded"] is False
        status, html = wait_for(lambda: get(f"http://127.0.0.1:{web}/"), 90)
        assert status == 200 and '<div id="root">' in html
        wait_for(lambda: b"Ready." in Path(out.name).read_bytes(), 30)
        assert b"API ready" in Path(out.name).read_bytes()
    finally:
        stop(proc)
    wait_for(lambda: port_closed(api) and port_closed(web), 15)          # both children were stopped with it


def test_busy_port_is_reported_and_nothing_starts(tmp_path):
    port = free_port()
    with socket.socket() as s:
        s.bind(("127.0.0.1", port))
        s.listen(1)
        proc, out = start(tmp_path, "-Mock", "-NoWeb", "-Port", str(port))
        try:
            code = proc.wait(timeout=60)
        finally:
            stop(proc)
    text = Path(out.name).read_text(errors="replace")
    assert code != 0 and "already in use" in text


@pytest.mark.gpu
def test_real_mode_waits_for_the_models(tmp_path):
    api = free_port()
    proc, out = start(tmp_path, "-NoWeb", "-Port", str(api))
    try:
        wait_for(lambda: b"API ready" in Path(out.name).read_bytes(), 240)
        health = json.loads(get(f"http://127.0.0.1:{api}/api/health")[1])
        assert health["model_loaded"] is True                               # the script only says ready after this
        assert b"model_loaded: True" in Path(out.name).read_bytes()
    finally:
        stop(proc)
    wait_for(lambda: port_closed(api), 20)
