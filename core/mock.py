"""Mock engine: replays stored REAL search output from mock/ (copied from sample_*.json, never written by hand).

MockEngine.run(...) has the same signature and result structure as core.engine.Engine.run. It picks the stored
search whose best design is nearest to the requested targets and walks through the stages with a short delay
(MOCK_STAGE_DELAY seconds, default 0.3; tests set 0). The numbers are those of the stored run, not of the request.
"""
from __future__ import annotations

import copy
import json
import math
import os
import time
from pathlib import Path
from typing import Any, Callable

MOCK_DIR = Path(os.environ.get("MOCK_DIR") or Path(__file__).resolve().parent.parent / "mock")
STAGES = (("search", "Proposing lattices"), ("repair", "Decoding and merging duplicates"),
          ("verify", "Solver checking every design"))

_samples: list[dict[str, Any]] | None = None


def load_samples() -> list[dict[str, Any]]:
    global _samples
    if _samples is None:
        _samples = []
        for f in sorted(MOCK_DIR.glob("sample_*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            d["_file"] = f.name
            _samples.append(d)
    return _samples


def _targets(spec: dict[str, Any]) -> list[float]:
    return [v for key in ("stiffness_gpa", "strength_mpa", "yield_strength_mpa") for v in (spec.get(key) or []) if v]


def _distance(spec: dict[str, Any], sample: dict[str, Any]) -> float:
    best = sample["candidates"][0]["verified"]
    pairs = []
    for key, got in (("stiffness_gpa", best["stiffness_gpa"]), ("strength_mpa", best["strength_mpa"]),
                     ("yield_strength_mpa", best["yield_strength_mpa"])):
        for a, t in zip("xyz", spec.get(key) or [None] * 3):
            if t:
                pairs.append(abs(math.log(got[a] / t)))
    return max(pairs) if pairs else 0.0


def with_predicted_governing(cand: dict[str, Any]) -> dict[str, Any]:
    """Stored samples predate predicted.governing_failure; derive it (effective strength = min(yield, buckling))."""
    cand = copy.deepcopy(cand)
    p = cand["predicted"]
    if "governing_failure" not in p:
        p["governing_failure"] = {a: ("yield" if p["yield_strength_mpa"][a] <= p["buckling_strength_mpa"][a] else "buckling")
                                  for a in "xyz"}
    return cand


class MockEngine:
    status = {"ok": True, "reason": None, "device": "mock", "workers": 0}
    ok = True

    def health(self) -> dict[str, Any]:
        return {"model_loaded": False, "gpu": False, "solver_workers": 0, "reason": "mock mode"}

    def run(self, request: Any, on_progress: Callable[[dict], None] | None = None,
            should_stop: Callable[[], bool] | None = None, *, ladder=(100, 300, 1000), time_budget_s=None,
            request_echo=None, search_kwargs=None) -> dict[str, Any]:
        from server import units
        emit = on_progress or (lambda _e: None)
        spec = request if isinstance(request, dict) else units.to_search_spec(
            request, units.MATERIALS[request.material.lower()])
        echo = request_echo if request_echo is not None else (
            None if isinstance(request, dict) else request.model_dump(mode="json"))
        sample = min(load_samples(), key=lambda s: _distance(spec, s))
        rounds = sample["rounds"]
        delay = float(os.environ.get("MOCK_STAGE_DELAY", "0.3"))
        n = max(1, len(rounds))
        for r, row in enumerate(rounds, 1):
            for si, (stage, text) in enumerate(STAGES):
                if should_stop and should_stop():
                    return self._result(spec, sample, rounds[: r - 1], [], echo, stopped=True)
                emit({"stage": stage, "round": r, "k": row["K"],
                      "progress": round(0.95 * ((r - 1) + (si + 1) / 3) / n, 3),
                      "message": f"Round {r} of up to {n}: {text} (replaying stored real output, {sample['_file']})"})
                if delay:
                    time.sleep(delay)
            emit({"stage": "verify", "round": r, "k": row["K"], "row": row, "progress": round(0.95 * r / n, 3),
                  "message": f"Round {r} of up to {n} done"})
        return self._result(spec, sample, rounds, sample["candidates"], echo)

    @staticmethod
    def _result(spec, sample, rounds, cands, echo, stopped: bool = False) -> dict[str, Any]:
        return {"material": sample["material"], "rounds": copy.deepcopy(rounds), "infeasible": bool(sample["infeasible"]),
                "candidates": [with_predicted_governing(c) for c in cands], "request": echo, "stopped": stopped}
