"""Run the beam solver on several CPU cores.

The search spends most of its time in the solver (about 25 ms per lattice and density, one core). The solves are
independent, so they are spread over a pool of worker processes. Workers only import numpy and the solver, not torch.

Worker count: WORKERS env var if set, else every core that is less than 50% busy right now (psutil), else all cores.
"""
from __future__ import annotations

import atexit
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUSY_LIMIT = 50.0     # a core counts as free when it is less than this % busy


def pick_workers() -> tuple[int, str]:
    """Return (number of workers, one-line explanation)."""
    total = os.cpu_count() or 1
    env = os.environ.get("WORKERS")
    if env and env.isdigit() and int(env) > 0:
        return min(int(env), 61), f"WORKERS={env} from the environment"
    try:
        import psutil
        load = psutil.cpu_percent(interval=1.0, percpu=True)
        free = sum(1 for p in load if p < BUSY_LIMIT)
        n = max(1, free - 1)                           # leave one core for the API and the GPU feeding thread
        return min(n, 61), f"{total} logical cores, {free} free (under {BUSY_LIMIT:.0f}% busy)"
    except Exception:                                   # psutil missing: use everything
        return min(total, 61), f"{total} logical cores (psutil not installed, cannot measure load)"


def _init_worker() -> None:
    if os.environ.get("SOLVER_PRIORITY") != "normal":     # "normal" is a benchmark switch: the old behaviour
        try:                                              # workers yield to the API server, so /api/health stays fast
            import psutil
            psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 10)
        except Exception:
            pass
    sys.path.insert(0, str(ROOT))
    import search_design  # noqa: F401  - also puts the solver folder on sys.path; imports numpy only


def has_torch(_: int) -> bool:
    """Worker-side check used by a test: workers must import only numpy and the solver, never PyTorch."""
    return "torch" in sys.modules


def ping(_: int) -> int:
    return os.getpid()


def solve_task(args):
    """(adj, pos, rho) -> solver result dict, or None when the solver fails on this lattice."""
    import search_design as sd
    try:
        return sd.solve(*args)
    except Exception:
        return None


def shutdown(pool: ProcessPoolExecutor | None) -> None:
    """Stop the workers now. Safe to call twice. Without this, a pool still alive at interpreter exit makes the
    executor's weakref callback raise AttributeError ('NoneType' has no attribute 'util') while modules are torn down."""
    if pool is not None:
        try:
            pool.shutdown(wait=True, cancel_futures=True)
        except Exception:
            pass


def make_pool(n: int) -> ProcessPoolExecutor:
    # one BLAS thread per worker, otherwise n workers x n threads fight over the same cores
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[var] = "1"
    pool = ProcessPoolExecutor(max_workers=n, initializer=_init_worker)
    list(pool.map(ping, range(n * 2)))                  # start the workers now, not on the first request
    atexit.register(shutdown, pool)                     # runs before modules are torn down
    return pool
