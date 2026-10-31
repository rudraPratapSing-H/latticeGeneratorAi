"""Search + solver interface used by the FastAPI backend.

Real mode wraps search_design.py (VAE decoder, 15-output predictor, beam solver).
Set MOCK=1 to use canned results with the same signatures (core/mock.py).

    load_models()                     once at startup
    search_round(spec, K, cache)      one search at K starting points; returns solver-verified candidates

`spec` is a plain dict (see server/jobs.py:build_spec). Each returned candidate is a dict in the API's
Candidate shape plus `matches_targets`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MOCK = os.environ.get("MOCK", "") == "1"

if MOCK:
    from core.mock import search_round  # noqa: F401
    from core.mock import is_loaded, load_models, health  # noqa: F401
else:
    sys.path.insert(0, str(ROOT))
    _state: dict[str, Any] = {}

    def load_models() -> None:
        """Load VAE, paper stiffness head, predictor and stored codes once (idempotent)."""
        if _state:
            return
        import numpy as np
        import torch
        import search_design as sd

        model_dir = Path(os.environ.get("MODEL_DIR", ROOT))
        device = os.environ.get("DEVICE") or ("cuda:0" if torch.cuda.is_available() else "cpu")
        vae, cmod, mask = sd.load_models(str(model_dir / "results"), str(model_dir / "data"), device)
        pred = sd.load_predictor(str(model_dir / os.environ.get("PREDICTOR", "q1.pt")), device)
        codes = np.load(str(model_dir / "encoded_codes.npz"))["mu"]
        from core import solver_pool
        n, why = solver_pool.pick_workers()
        pool = solver_pool.make_pool(n) if n > 1 else None
        print(f"[pool] {why} -> {n} solver worker(s)", flush=True)
        _state.update(vae=vae, cmod=cmod, mask=mask, pred=pred, codes=codes, device=device, pool=pool, workers=n)

    def is_loaded() -> bool:
        return bool(_state)

    def health() -> dict[str, Any]:
        return {"model_loaded": is_loaded(), "gpu": bool(_state) and str(_state["device"]).startswith("cuda"),
            "solver_workers": _state.get("workers", 0)}

    def _failure(y, b, E_gpa, yield_mpa):
        return {k: ("yield" if yv * yield_mpa <= bv * E_gpa * 1000 else "buckling") for k, yv, bv in zip("xyz", y, b)}

    def search_round(spec: dict[str, Any], K: int, cache: dict | None = None) -> list[dict[str, Any]]:
        """One search round at K starting points. Starts, an early snapshot and the steered end point of every
        start are all solver-verified, duplicates (same verified behaviour) are merged, best first."""
        import search_design as sd
        from core.solver_pool import solve_task as solver_pool_task

        load_models()
        mat = spec["material"]
        sdm = dict(E_gpa=mat["E_gpa"], yield_mpa=mat["yield_mpa"], density_g_cc=mat["density_g_cm3"])
        tg = sd.Target(sdm, stiffness_gpa=spec.get("stiffness_gpa"), strength_mpa=spec.get("strength_mpa"),
                       yield_mpa=spec.get("yield_strength_mpa"), rho=spec.get("rho"), rho_max=spec.get("rho_max"),
                       modes=spec["modes"], tol=spec["tol"])
        s = _state
        cands = sd.run_search(s["vae"], s["cmod"], s["pred"], s["mask"], s["codes"], tg, s["device"], K=K,
                              steps=100, lr=0.002, cache=cache,
                              executor=s.get("pool"), task_fn=solver_pool_task, n_workers=s.get("workers", 1),
                              log=lambda *a: print("[search]", *a, flush=True))   # progress lines in the server console
        out = []
        for rank, c in enumerate(cands, 1):
            j = sd.to_candidate_json(c, tg, rank, spec["cell_mm"], spec.get("part_mm"))
            j["predicted"]["governing_failure"] = _failure(c["pred"]["y"], c["pred"]["b"], mat["E_gpa"], mat["yield_mpa"])
            j.setdefault("mass_g", 0.0)
            j["origin"] = c["origin"]
            out.append(j)
        return out
