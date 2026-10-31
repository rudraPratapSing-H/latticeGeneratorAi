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
def _ladder_from_env() -> tuple[int, ...]:
    """K_LADDER="300" or "100,300,1000" overrides the starting-point ladder (benchmarks); default 100, 300, 1000."""
    raw = os.environ.get("K_LADDER", "")
    try:
        vals = tuple(int(x) for x in raw.replace(" ", "").split(",") if x)
    except ValueError:
        vals = ()
    return vals if vals and all(v > 0 for v in vals) else (100, 300, 1000)


K_LADDER = _ladder_from_env()
DEFAULT_TIME_BUDGET_S = 120.0

ProgressFn = Callable[[dict[str, Any]], None]


class EngineUnavailable(RuntimeError):
    """Raised by run() when the engine did not load; the message says why and how to fix it."""


def is_out_of_memory(e: BaseException) -> bool:
    return "out of memory" in str(e).lower()


def drop_unphysical(cands: list[dict[str, Any]], material: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    """Skip candidates whose solver result is not finite and positive, or whose three stiffnesses add up to more than
    1.05 x density x E_s (a floppy-lattice artefact no beam lattice can reach). Returns (kept, how many were skipped)."""
    kept = []
    for c in cands:
        st = list(c["verified"]["stiffness_gpa"].values())
        ok = all(isinstance(v, (int, float)) and v == v and abs(v) != float("inf") and v > 0 for v in st)
        if ok and sum(st) > 1.05 * c["rel_density"] * material["E_gpa"]:
            ok = False
        if ok:
            kept.append(c)
    for rank, c in enumerate(kept, 1):
        c["rank"] = rank
    return kept, len(cands) - len(kept)


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
        fallback = None
        with self._lock:                                   # one search at a time on the GPU
            cands, history = self._run_with_memory_fallback(
                sd, tg, state, budget, infeasible, on_round, log, should_stop, solve_task, search_kwargs)
            if not cands and not (should_stop and should_stop()):
                # the search produced no valid lattice at all: show the nearest STORED lattices, solver-verified
                emit({"stage": "search", "round": state["round"], "k": None, "progress": 0.9,
                      "message": "The search found no valid design; checking the nearest stored lattices..."})
                cands = self._nearest_stored(sd, tg, spec, solve_task, search_kwargs)
                fallback = "nearest_stored" if cands else None
        out = []
        for rank, c in enumerate(cands, 1):
            j = sd.to_candidate_json(c, tg, rank, spec["cell_mm"], spec.get("part_mm"))
            j["predicted"]["governing_failure"] = _failure(c["pred"]["y"], c["pred"]["b"], mat["E_gpa"], mat["yield_mpa"])
            j["origin"] = "stored" if fallback else c["origin"]
            out.append(j)
        out, skipped = drop_unphysical(out, mat)
        return {"material": sdm, "rounds": history, "infeasible": infeasible, "candidates": out, "request": echo,
                "fallback": fallback, "skipped_invalid": skipped, "elapsed_seconds": round(time.time() - t0, 2),
                "stopped": bool(should_stop and should_stop())}

    # ------------------------------------------------------------------ memory fallback and stored-lattice fallback
    def _run_with_memory_fallback(self, sd, tg, state, budget, infeasible, on_round, log, should_stop, task_fn, extra):
        """Full ladder; on CUDA out-of-memory retry with half the starts; if that fails too, move the models to the
        CPU (slower) and retry once more. Any other error is raised."""
        first = list(state["rungs"])
        halved = [max(10, k // 2) for k in first]
        plan = [("gpu", first), ("gpu", halved), ("cpu", halved)]
        for attempt, (where, rungs) in enumerate(plan):
            if where == "cpu" and str(self._s["device"]).startswith("cuda"):
                self._to_cpu()
            state.update(round=0, rungs=rungs, n=len(rungs))
            try:
                return self._adaptive(sd, tg, rungs, budget, infeasible, on_round, log, should_stop, task_fn, extra)
            except RuntimeError as e:
                if not is_out_of_memory(e) or attempt == len(plan) - 1:
                    raise
                self._release_gpu_memory()
        raise AssertionError("unreachable")

    def _release_gpu_memory(self) -> None:
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def _to_cpu(self) -> None:
        """Move every model and tensor to the CPU and report the new device (health shows gpu: false)."""
        s = self._s
        for key in ("vae", "cmod"):
            s[key] = s[key].to("cpu")
        pred = s["pred"]
        pred["net"] = pred["net"].to("cpu")
        for key in ("x_mean", "x_std", "y_mean", "y_std"):
            pred[key] = pred[key].to("cpu")
        s["device"] = "cpu"
        self.status = {**self.status, "device": "cpu"}
        self._release_gpu_memory()

    def _nearest_stored(self, sd, tg, spec, task_fn, extra) -> list[dict[str, Any]]:
        """The stored lattices nearest to the target (picker distance), decoded and solver-verified through the same
        run_search (no steering). Empty when the reach table or the stored ids are unavailable."""
        try:
            import numpy as np
            from core import reach
            s = self._s
            ids_all = s.get("code_ids")
            if ids_all is None:
                return []
            yld = spec.get("yield_strength_mpa")
            ids, _density = reach.get_table().nearest_ids(
                spec["material"], n=int(os.environ.get("FALLBACK_N", "20")), stiffness=spec.get("stiffness_gpa"),
                strength=yld if yld is not None else spec.get("strength_mpa"), yield_only=yld is not None,
                modes=spec["modes"], tol=spec["tol"], rho=spec.get("rho"), rho_max=spec.get("rho_max"))
            pool_idx = np.flatnonzero(np.isin(ids_all, ids))
            if len(pool_idx) == 0:
                return []
            kw = {k: v for k, v in (extra or {}).items() if k != "pool_idx"}
            return sd.run_search(s["vae"], s["cmod"], s["pred"], s["mask"], s["codes"], tg, s["device"],
                                 K=len(pool_idx), use_gradient=False, pool_idx=pool_idx, log=lambda *_: None,
                                 executor=s.get("pool"), task_fn=task_fn, n_workers=s.get("workers", 1), **kw)
        except Exception:
            return []

    def close(self) -> None:
        """Stop the solver workers (also registered at exit)."""
        from core import solver_pool
        solver_pool.shutdown(self._s.pop("pool", None))
        self.status = {**self.status, "workers": 0}

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
        stored = np.load(str(model_dir / "encoded_codes.npz"))
        codes, code_ids = stored["mu"], stored["ids"]
        from core import solver_pool
        n, why = solver_pool.pick_workers()
        pool = solver_pool.make_pool(n) if n > 1 else None
        print(f"[pool] {why} -> {n} solver worker(s)", flush=True)
        eng._s = dict(vae=vae, cmod=cmod, pred=pred, mask=mask, codes=codes, code_ids=code_ids, device=device,
                      pool=pool, workers=n)
        eng.status = {"ok": True, "reason": None, "device": device, "workers": n}
    except BaseException as e:  # noqa: BLE001 - startup must not crash; health reports the reason
        eng.status = {"ok": False, "reason": f"{type(e).__name__}: {e}", "device": None, "workers": 0}
    return eng
