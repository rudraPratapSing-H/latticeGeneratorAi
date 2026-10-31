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
