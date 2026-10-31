"""The only module that imports torch and search_design. Wraps the adaptive search behind a small interface.

    engine = load_engine(model_dir, device)      # never raises; engine.status says whether it is usable
    result = engine.run(request, on_progress, should_stop)
        -> {"material", "rounds", "infeasible", "candidates", "request"}   (same structure as search_design --out)

Candidates are already solver-verified (start, early snapshot and steered end point of every start) and ranked.
Nothing here changes a number produced by search_design.py or lattice_strength.py.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from core import envcheck

ROOT = Path(__file__).resolve().parent.parent
K_LADDER = (100, 300, 1000)
DEFAULT_TIME_BUDGET_S = 120.0

ProgressFn = Callable[[dict[str, Any]], None]


class EngineUnavailable(RuntimeError):
    """Raised by run() when the engine did not load; the message says why and how to fix it."""


def _failure(y, b, E_gpa: float, yield_mpa: float) -> dict[str, str]:
    return {k: ("yield" if yv * yield_mpa <= bv * E_gpa * 1000 else "buckling") for k, yv, bv in zip("xyz", y, b)}


def _stage_of(line: str) -> tuple[str, float] | None:
    """Map a run_search log line to (stage, fraction of the round done)."""
    t = line.strip()
    if t.startswith("start:"):
        return "search", 0.10
    if t.startswith("steer:"):
        return "search", 0.40
    if t.startswith("decode:"):
        return "repair", 0.55
    if t.startswith("solver:"):
        return "verify", 0.90
    if t.startswith("verify:"):
        return "verify", 0.98
    return None


class Engine:
    def __init__(self) -> None:
        self.status: dict[str, Any] = {"ok": False, "reason": "not loaded", "device": None, "workers": 0}
        self._s: dict[str, Any] = {}
        self._lock = threading.Lock()

    @property
    def ok(self) -> bool:
        return bool(self.status.get("ok"))

    def health(self) -> dict[str, Any]:
        dev = str(self.status.get("device") or "")
        return {"model_loaded": self.ok, "gpu": self.ok and dev.startswith("cuda"),
                "solver_workers": int(self.status.get("workers") or 0), "reason": self.status.get("reason")}

    def run(self, request: Any, on_progress: ProgressFn | None = None,
            should_stop: Callable[[], bool] | None = None, *, ladder=K_LADDER,
            time_budget_s: float | None = None, request_echo: dict | None = None,
            search_kwargs: dict | None = None) -> dict[str, Any]:
        """Run the adaptive search for `request` (a server.schemas.DesignRequest, or a spec dict from
        server.units.to_search_spec). K = 100, 300, 1000; stops on a match, when a round gains under half a
        point, at the time budget, or when `should_stop()` returns True (checked between rounds)."""
        if not self.ok:
            raise EngineUnavailable(self.status.get("reason") or "engine not loaded")
        from server import units

        import search_design as sd
        from core.solver_pool import solve_task

        if isinstance(request, dict) and "material" in request and "tol" in request:
            spec, echo = request, request_echo
        else:
            material = units.MATERIALS[request.material.lower()]
            spec = units.to_search_spec(request, material)
            echo = request_echo if request_echo is not None else request.model_dump(mode="json")
        mat = spec["material"]
        budget = DEFAULT_TIME_BUDGET_S if time_budget_s is None else time_budget_s
        if time_budget_s is None and os.environ.get("TIME_BUDGET_S"):
            budget = float(os.environ["TIME_BUDGET_S"])
        infeasible = units.is_infeasible(spec)
        sdm = dict(E_gpa=mat["E_gpa"], yield_mpa=mat["yield_mpa"], density_g_cc=mat["density_g_cm3"])
        tg = sd.Target(sdm, stiffness_gpa=spec.get("stiffness_gpa"), strength_mpa=spec.get("strength_mpa"),
                       yield_mpa=spec.get("yield_strength_mpa"), rho=spec.get("rho"), rho_max=spec.get("rho_max"),
                       modes=spec["modes"], tol=spec["tol"])
        s = self._s
        rungs = list(ladder)[:1] if infeasible else list(ladder)
        state = {"round": 0, "n": len(rungs), "rungs": rungs}
        emit = on_progress or (lambda _e: None)

        def log(line: str) -> None:
            if line.strip().startswith("[round"):
                state["round"] += 1
                return
            m = _stage_of(line)
            if m and state["round"]:
                stage, frac = m
                r, n = state["round"], state["n"]
                emit({"stage": stage, "round": r, "k": state["rungs"][r - 1],
                      "progress": round(min(0.95, ((r - 1) + frac) / n * 0.95), 3),
                      "message": f"Round {r} of up to {n}: {line.strip()}"})

        def on_round(row: dict, _cands: list) -> None:
            emit({"stage": "verify", "round": row["round"], "k": row["K"], "row": row,
                  "progress": round(min(0.95, row["round"] / state["n"] * 0.95), 3),
                  "message": f"Round {row['round']} of up to {state['n']} done: best error "
                             f"{100 * row['best_err']:.1f}%{' (match)' if row['matched'] else ''}"})
            if not row["matched"] and row["round"] < state["n"]:
                emit({"stage": "search", "round": row["round"], "k": state["rungs"][row["round"]],
                      "progress": round(min(0.95, row["round"] / state["n"] * 0.95), 3),
                      "message": f"No design meets every target. Escalating to {state['rungs'][row['round']]} candidates..."})

        t0 = time.time()
        with self._lock:                                   # one search at a time on the GPU
            try:
                cands, history = self._adaptive(sd, tg, rungs, budget, infeasible, on_round, log, should_stop,
                                                solve_task, search_kwargs)
            except RuntimeError as e:                      # CUDA out of memory: retry once with half the starts
                if "out of memory" not in str(e).lower():
                    raise
                import torch
                torch.cuda.empty_cache()
                state.update(round=0, rungs=[max(10, k // 2) for k in rungs])
                cands, history = self._adaptive(sd, tg, state["rungs"], budget, infeasible, on_round, log,
                                                should_stop, solve_task, search_kwargs)
        out = []
        for rank, c in enumerate(cands, 1):
            j = sd.to_candidate_json(c, tg, rank, spec["cell_mm"], spec.get("part_mm"))
            j["predicted"]["governing_failure"] = _failure(c["pred"]["y"], c["pred"]["b"], mat["E_gpa"], mat["yield_mpa"])
            j["origin"] = c["origin"]
            out.append(j)
        return {"material": sdm, "rounds": history, "infeasible": infeasible, "candidates": out, "request": echo,
                "elapsed_seconds": round(time.time() - t0, 2),
                "stopped": bool(should_stop and should_stop())}

    def _adaptive(self, sd, tg, rungs, budget, infeasible, on_round, log, should_stop, task_fn, extra=None):
        s = self._s
        return sd.search_adaptive(
            s["vae"], s["cmod"], s["pred"], s["mask"], s["codes"], tg, s["device"], ladder=rungs,
            time_budget=budget, infeasible=infeasible, on_round=on_round, log=log, should_stop=should_stop,
            steps=100, lr=0.002, executor=s.get("pool"), task_fn=task_fn, n_workers=s.get("workers", 1),
            **(extra or {}))


def load_engine(model_dir: str | Path | None = None, device: str | None = None) -> Engine:
    """Load VAE, stiffness head, predictor, stored codes and the node mask once. Never raises."""
    eng = Engine()
    model_dir = Path(model_dir or os.environ.get("MODEL_DIR") or ROOT)
    predictor = os.environ.get("PREDICTOR", "q1.pt")
    problem = envcheck.first_problem(envcheck.check_models(model_dir, predictor))
    if problem:
        eng.status = {"ok": False, "reason": problem, "device": None, "workers": 0}
        return eng
    try:
        sys.path.insert(0, str(ROOT))
        import numpy as np
        import torch
        import search_design as sd

        if int(np.__version__.split(".")[0]) >= 2:
            raise RuntimeError('NumPy 2 is installed; fix: pip install "numpy<2"')
        device = device or os.environ.get("DEVICE") or ("cuda:0" if torch.cuda.is_available() else "cpu")
        vae, cmod, mask = sd.load_models(str(model_dir / "results"), str(model_dir / "data"), device)
        pred = sd.load_predictor(str(model_dir / predictor), device)
        codes = np.load(str(model_dir / "encoded_codes.npz"))["mu"]
        from core import solver_pool
        n, why = solver_pool.pick_workers()
        pool = solver_pool.make_pool(n) if n > 1 else None
        print(f"[pool] {why} -> {n} solver worker(s)", flush=True)
        eng._s = dict(vae=vae, cmod=cmod, pred=pred, mask=mask, codes=codes, device=device, pool=pool, workers=n)
        eng.status = {"ok": True, "reason": None, "device": device, "workers": n}
    except BaseException as e:  # noqa: BLE001 - startup must not crash; health reports the reason
        eng.status = {"ok": False, "reason": f"{type(e).__name__}: {e}", "device": None, "workers": 0}
    return eng
