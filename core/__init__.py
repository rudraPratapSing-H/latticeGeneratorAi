"""Backend-facing interface to the search and solver.

    core.MOCK                  True when MOCK=1: canned engine, no torch, no GPU
    core.start_engine()        load the engine once (idempotent, never raises); call from a worker thread
    core.get_engine()          the engine (a not-loaded one before start_engine); engine.run(...) does a search
    core.health()              {model_loaded, gpu, solver_workers, reason}

Importing this package never imports torch or the models (invariant 10).
"""
from __future__ import annotations

import os
import threading
from typing import Any

MOCK = os.environ.get("MOCK", "") == "1"

_engine: Any = None
_lock = threading.Lock()


def get_engine() -> Any:
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                if MOCK:
                    from core.mock import MockEngine
                    _engine = MockEngine()
                else:
                    from core.engine import Engine
                    _engine = Engine()          # status.ok is False until start_engine() has run
    return _engine


def start_engine() -> Any:
    """Load the real engine (blocking; run it in a thread). Safe to call twice."""
    global _engine
    with _lock:
        if MOCK:
            from core.mock import MockEngine
            _engine = _engine or MockEngine()
            return _engine
        if _engine is not None and _engine.ok:
            return _engine
    from core.engine import load_engine
    eng = load_engine()
    with _lock:
        _engine = eng
    return eng


def health() -> dict[str, Any]:
    return get_engine().health()


_hash: str | None = None
_real_hash: str | None = None


def _fingerprint(mock: bool) -> str:
    """Content hash of the model files (real) or the stored mock runs (mock); about 0.3 s for the real files."""
    import hashlib
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    if mock:
        files = sorted((root / "mock").glob("sample_*.json"))
    else:
        from core import envcheck
        files = [root / rel for rel, _, _ in envcheck.MODEL_FILES] + [root / "search_design.py"]
    h = hashlib.sha256(b"mock" if mock else b"real")
    for f in files:
        h.update(f.name.encode())
        if f.is_file():
            with open(f, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
    return h.hexdigest()[:16]


def model_hash() -> str:
    """Fingerprint of what produces results in this process. A cached or stored result is only valid for the files
    it was made with; a content hash survives a fresh git clone."""
    global _hash
    if _hash is None:
        _hash = _fingerprint(MOCK)
    return _hash


def real_model_hash() -> str:
    """The hash of the real model files, even in mock mode (stamps and checks stored demo results)."""
    global _real_hash
    if _real_hash is None:
        _real_hash = _hash if (not MOCK and _hash) else _fingerprint(False)
    return _real_hash
