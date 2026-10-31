"""Check the environment before starting the backend:  python scripts/check_env.py [--model-dir DIR]

Exit code 0 when everything needed for real mode is fine, 1 otherwise (CPU-only torch is a warning, not an error).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import envcheck  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model-dir", default=str(ROOT))
    a = ap.parse_args(argv)
    bad = 0

    py = envcheck.check_python()
    print(f"[{'OK' if py['ok'] else 'FAIL'}] Python {py['version']}" + (f"  -> {py['fix']}" if py["fix"] else ""))
    bad += not py["ok"]
    npy = envcheck.check_numpy()
    print(f"[{'OK' if npy['ok'] else 'FAIL'}] NumPy {npy['version']}" + (f"  -> {npy['fix']}" if npy["fix"] else ""))
    bad += not npy["ok"]
    tc = envcheck.check_torch()
    if not tc["ok"]:
        print(f"[FAIL] PyTorch not installed  -> {tc['fix']}")
        bad += 1
    elif tc["cuda"]:
        print(f"[OK] PyTorch {tc['version']} with CUDA ({tc['device']})")
    else:
        print(f"[WARN] PyTorch {tc['version']} without CUDA  -> {tc['fix']}")
    for r in envcheck.check_models(Path(a.model_dir)):
        print(f"[{r['status'].upper():7}] {r['file']} ({r['what']})" + (f"  -> {r['fix']}" if r["fix"] else ""))
        bad += r["status"] != "ok"
    print("\nAll good." if not bad else f"\n{bad} problem(s) found.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
