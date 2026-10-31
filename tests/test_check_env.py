import subprocess
import sys
from pathlib import Path

from core import envcheck

ROOT = Path(__file__).resolve().parent.parent


def test_file_status_ok_missing_pointer(tmp_path):
    ok = tmp_path / "ok.pt"
    ok.write_bytes(b"\x80\x02real weights" * 10)
    ptr = tmp_path / "ptr.pt"
    ptr.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 123\n")
    assert envcheck.file_status(ok) == "ok"
    assert envcheck.file_status(ptr) == "pointer"
    assert envcheck.file_status(tmp_path / "nope.pt") == "missing"


def test_check_models_reports_pointer(tmp_path):
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "best_model.pt").write_text("version https://git-lfs.github.com/spec/v1\nsize 1\n")
    rows = {r["file"]: r for r in envcheck.check_models(tmp_path)}
    assert rows["results/best_model.pt"]["status"] == "pointer"
    assert rows["results/best_c_model.pt"]["status"] == "missing"
    assert "Git LFS pointer" in envcheck.first_problem(list(rows.values()))


def test_cli_runs_and_fails_on_empty_model_dir(tmp_path):
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_env.py"), "--model-dir", str(tmp_path)],
                         capture_output=True, text=True)
    assert out.returncode == 1 and "[MISSING]" in out.stdout
