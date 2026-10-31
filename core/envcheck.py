"""Environment and model-file checks, shared by scripts/check_env.py and the engine (no torch import here)."""
from __future__ import annotations

import sys
from pathlib import Path

LFS_HEADER = b"version https://git-lfs.github.com/spec"

# (relative path, what it is, fix when broken)
MODEL_FILES = [
    ("results/best_model.pt", "VAE weights", "git lfs pull"),
    ("results/best_c_model.pt", "paper stiffness head", "git lfs pull"),
    ("q1.pt", "predictor", "git pull (q1.pt is a normal file)"),
    ("encoded_codes.npz", "stored lattice codes", "git lfs pull"),
    ("data/ptb_mask.csv", "node mask", "git pull"),
    ("strength-labels/lattice_strength.py", "beam solver", "git pull"),
]


def file_status(path: Path) -> str:
    """'ok', 'missing' or 'pointer' (a Git LFS text pointer where the real file should be)."""
    path = Path(path)
    if not path.is_file():
        return "missing"
    try:
        with open(path, "rb") as f:
            head = f.read(len(LFS_HEADER))
        if head == LFS_HEADER:
            return "pointer"
        if path.stat().st_size == 0:
            return "missing"
    except OSError:
        return "missing"
    return "ok"


def check_models(model_dir: Path, predictor: str = "q1.pt") -> list[dict]:
    rows = []
    for rel, what, fix in MODEL_FILES:
        rel = predictor if rel == "q1.pt" else rel
        st = file_status(Path(model_dir) / rel)
        rows.append({"file": rel, "what": what, "status": st, "fix": None if st == "ok" else fix})
    return rows


def first_problem(rows: list[dict]) -> str | None:
    for r in rows:
        if r["status"] != "ok":
            why = "is a Git LFS pointer, not the real file" if r["status"] == "pointer" else "is missing"
            return f"{r['file']} ({r['what']}) {why}. Fix: {r['fix']}"
    return None


def check_python() -> dict:
    ok = sys.version_info[:2] == (3, 11)
    return {"ok": ok, "version": ".".join(map(str, sys.version_info[:3])),
            "fix": None if ok else "Use Python 3.11 (the pinned PyTorch 2.1.2 has no wheels for newer versions)"}


def check_numpy() -> dict:
    try:
        import numpy
        ok = int(numpy.__version__.split(".")[0]) < 2
        return {"ok": ok, "version": numpy.__version__,
                "fix": None if ok else "pip install \"numpy<2\" (PyTorch 2.1.2 breaks with NumPy 2)"}
    except ImportError:
        return {"ok": False, "version": None, "fix": "pip install \"numpy<2\""}


def check_torch() -> dict:
    try:
        import torch
    except ImportError:
        return {"ok": False, "version": None, "cuda": False, "fix":
                "pip install torch==2.1.2 --index-url https://download.pytorch.org/whl/cu121"}
    cuda = bool(torch.cuda.is_available())
    return {"ok": True, "version": torch.__version__, "cuda": cuda,
            "device": torch.cuda.get_device_name(0) if cuda else None,
            "fix": None if cuda else "CPU only (works, many times slower). For CUDA: "
                   "pip install torch==2.1.2 --index-url https://download.pytorch.org/whl/cu121"}
