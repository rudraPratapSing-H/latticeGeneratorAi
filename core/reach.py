"""Dataset picker: where does a target sit relative to the 900,000 solved lattices (300,000 x 3 densities)?

numpy only (no torch). The table comes from scripts/build_reach_table.py (core/tables/reach_table.npz).

Levels: covered (within tolerance of a stored lattice), extended (to 25%), outside (beyond), infeasible (no beam
lattice can do it: stiffnesses add up to more than 1.05 x density x E_s, or strength above the density's maximum).
The picker only suggests; it never changes a user's numbers.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

import numpy as np

DEFAULT_TABLE = Path(__file__).resolve().parent / "tables" / "reach_table.npz"
DENSITIES = (0.05, 0.15, 0.25)
EXTENDED_LIMIT = 0.25          # 10% .. 25% from the nearest stored lattice
INFEASIBLE_MARGIN = 1.05
AX = "xyz"


class ReachUnavailable(RuntimeError):
    pass


def rel_errors(pred: np.ndarray, target: float, mode: str) -> np.ndarray:
    """Per-row relative error of one value in the sense of its mode: 'about' two-sided, 'at_least' only a
    shortfall, 'at_most' only an excess. Vectorised form of search_design.solver_errors (a test pins them equal)."""
    rel = pred / target - 1.0
    if mode == "about":
        return np.abs(rel)
    if mode == "at_least":
        return np.maximum(-rel, 0.0)
    return np.maximum(rel, 0.0)


class ReachTable:
    def __init__(self, data: dict[str, np.ndarray]) -> None:
        self.densities = tuple(float(x) for x in data["densities"])
        self.E = [data[f"E{i}"] for i in range(3)]           # (n,3) units of E_s
        self.Y = [data[f"Y{i}"] for i in range(3)]           # (n,3) units of sigma_y
        self.B = [data[f"B{i}"] for i in range(3)]           # (n,3) units of E_s
        self.ids = [data[f"id{i}"] for i in range(3)]
        self._cache: dict[tuple, dict[str, Any]] = {}
        self._lock = threading.Lock()

    @classmethod
    def load(cls, path: str | Path | None = None) -> "ReachTable":
        path = Path(path or os.environ.get("REACH_TABLE") or DEFAULT_TABLE)
        if not path.is_file():
            raise ReachUnavailable(f"reach table not found at {path}; build it with scripts/build_reach_table.py")
        with open(path, "rb") as f:
            if f.read(7) == b"version":
                raise ReachUnavailable(f"{path} is a Git LFS pointer; run: git lfs pull")
        with np.load(path) as z:
            return cls({k: z[k] for k in z.files})

    @property
    def nbytes(self) -> int:
        return sum(a.nbytes for grp in (self.E, self.Y, self.B, self.ids) for a in grp)

    # ------------------------------------------------------------------ material-specific values
    def values(self, material: dict[str, Any], i: int) -> dict[str, np.ndarray]:
        """Stiffness (GPa), yield (MPa), effective strength min(yield, E_s x buckling) (MPa) for density index i."""
        key = (round(material["E_gpa"], 6), round(material["yield_mpa"], 6), i)
        with self._lock:
            if key not in self._cache:
                Es_mpa = material["E_gpa"] * 1000.0
                stiff = (self.E[i] * np.float32(material["E_gpa"])).astype(np.float32)
                yld = (self.Y[i] * np.float32(material["yield_mpa"])).astype(np.float32)
                eff = np.minimum(yld, self.B[i] * np.float32(Es_mpa)).astype(np.float32)
                self._cache[key] = {"stiff": stiff, "yield": yld, "eff": eff}
            return self._cache[key]

    def bounds(self, material: dict[str, Any], i: int, yield_only: bool = False) -> dict[str, float]:
        v = self.values(material, i)
        return {"stiffness_sum_max_gpa": float(self.densities[i] * material["E_gpa"]),
                "stiffness_axis_max_gpa": float(v["stiff"].max()),
                "strength_max_mpa": float((v["yield"] if yield_only else v["eff"]).max())}

    def limits(self, material: dict[str, Any]) -> dict[str, Any]:
        """Per-density ranges for the form hints and validation (GET /api/limits)."""
        rows = []
        for i, rho in enumerate(self.densities):
            v = self.values(material, i)
            stat = lambda a: {"min": float(a.min()), "median": float(np.median(a)), "max": float(a.max())}  # noqa: E731
            rows.append({"rel_density": round(rho, 4), "stiffness_gpa": stat(v["stiff"]),
                         "strength_mpa": stat(v["eff"]), "yield_strength_mpa": stat(v["yield"]),
                         "stiffness_sum_max_gpa": float(rho * material["E_gpa"]),
                         "strength_max_mpa": float(v["eff"].max())})
        return {"material": material.get("id"), "densities": rows,
                "stiffness_max_gpa": max(r["stiffness_gpa"]["max"] for r in rows),
                "strength_max_mpa": max(r["strength_mpa"]["max"] for r in rows)}

    # ------------------------------------------------------------------ distance
    def _distance(self, material, i, stiffness, strength, yield_only, modes, tol):
        """(distance per row, two-sided distance per row) at density index i."""
        v = self.values(material, i)
        S = v["yield"] if yield_only else v["eff"]
        n = len(S)
        dist = np.zeros(n, dtype=np.float32)
        dist2 = np.zeros(n, dtype=np.float32)
        for arr, tgt, mode in ((v["stiff"], stiffness, modes["stiffness"]), (S, strength, modes["strength"])):
            if tgt is None:
                continue
            for a in range(3):
                if tgt[a] is None:
                    continue
                rel = arr[:, a] / np.float32(tgt[a]) - np.float32(1.0)      # same rule as rel_errors, computed once
                ab = np.abs(rel)
                np.maximum(dist2, ab, out=dist2)
                if mode == "about":
                    np.maximum(dist, ab, out=dist)
                elif mode == "at_least":
                    np.maximum(dist, np.maximum(-rel, 0.0), out=dist)
                else:
                    np.maximum(dist, np.maximum(rel, 0.0), out=dist)
        return dist, dist2

    def _infeasible(self, material, i, stiffness, strength, yield_only, modes, tol) -> str | None:
        rho = self.densities[i]
        if stiffness is not None and modes["stiffness"] != "at_most":
            given = [x for x in stiffness if x is not None]
            if given and sum(given) > INFEASIBLE_MARGIN * rho * material["E_gpa"] and len(given) == 3:
                return (f"the three stiffnesses add up to {sum(given):.2f} GPa, but at relative density {rho:g} "
                        f"no lattice can exceed about {rho * material['E_gpa']:.2f} GPa in total")
            if given and max(given) > INFEASIBLE_MARGIN * rho * material["E_gpa"]:
                return (f"a stiffness of {max(given):.2f} GPa is above density x E_s = "
                        f"{rho * material['E_gpa']:.2f} GPa at relative density {rho:g}")
        if strength is not None and modes["strength"] != "at_most":
            smax = self.bounds(material, i, yield_only)["strength_max_mpa"]
            given = [x for x in strength if x is not None]
            if given:
                need = max(given) * (1 - tol if modes["strength"] == "about" else 1.0)
                if need > smax:
                    return f"a strength of {max(given):g} MPa is above the {smax:.1f} MPa maximum at relative density {rho:g}"
        return None

    # ------------------------------------------------------------------ the picker
    def check(self, material: dict[str, Any], *, stiffness=None, strength=None, yield_only: bool = False,
              modes: dict[str, str] | None = None, tol: float = 0.10, rho: float | None = None,
              rho_max: float | None = None) -> dict[str, Any]:
        """Level, distance, chosen density, nearest stored lattice and bounds for one request.

        stiffness / strength: [x, y, z] with None for an ignored axis (GPa / MPa), or None for the whole group.
        rho: fixed density (weight 'about'); rho_max: a weight limit ('at_most'); both None: any dataset density.
        """
        modes = {"stiffness": "about", "strength": "at_least", "weight": "at_most", **(modes or {})}
        if stiffness is None and strength is None:
            raise ValueError("give at least one stiffness or strength value")
        warnings: list[str] = []
        if rho is not None:
            allowed = [int(np.argmin([abs(d - rho) for d in self.densities]))]
            if not (self.densities[0] * 0.95 <= rho <= self.densities[-1] * 1.05):
                warnings.append(f"relative density {rho:.3f} is outside the trained range 0.05 to 0.25; "
                                f"using {self.densities[allowed[0]]:g}")
        elif rho_max is not None:
            allowed = [i for i, d in enumerate(self.densities) if d <= rho_max * 1.02]
            if not allowed:
                allowed = [0]
                warnings.append(f"the weight limit implies a relative density of {rho_max:.3f}, below the lightest "
                                f"lattice in the data (0.05); results are extrapolated")
        else:
            allowed = [0, 1, 2]

        per = []
        for i in allowed:
            bad = self._infeasible(material, i, stiffness, strength, yield_only, modes, tol)
            dist, dist2 = self._distance(material, i, stiffness, strength, yield_only, modes, tol)
            j = int(np.argmin(dist))
            tied = np.flatnonzero(dist <= dist[j] + 1e-9)
            j = int(tied[np.argmin(dist2[tied])]) if len(tied) > 1 else j
            per.append({"i": i, "infeasible": bad, "d": float(dist[j]), "row": j})

        feasible = [p for p in per if p["infeasible"] is None]
        if not feasible:
            pick = min(per, key=lambda p: p["d"])
            level = "infeasible"
        else:
            if rho is None and rho_max is None:
                cov = [p for p in feasible if p["d"] <= tol]
                pick = cov[0] if cov else min(feasible, key=lambda p: p["d"])    # lowest covered density first
            else:
                pick = min(feasible, key=lambda p: p["d"]) if rho_max is not None else feasible[0]
            d = pick["d"]
            level = "covered" if d <= tol else ("extended" if d <= EXTENDED_LIMIT else "outside")

        i, row = pick["i"], pick["row"]
        v = self.values(material, i)
        S = v["yield"] if yield_only else v["eff"]
        b = self.bounds(material, i, yield_only)
        result = {
            "level": level,
            "distance_pct": round(100.0 * pick["d"], 2),
            "density": round(self.densities[i], 4),
            "requested": {"stiffness_gpa": stiffness, "strength_mpa": strength},
            "nearest": {"stiffness_gpa": [round(float(x), 4) for x in v["stiff"][row]],
                        "strength_mpa": [round(float(x), 3) for x in S[row]],
                        "lattice_id": int(self.ids[i][row])},
            "bounds": {"stiffness_sum_max_gpa": round(b["stiffness_sum_max_gpa"], 3),
                       "strength_max_mpa": round(b["strength_max_mpa"], 2)},
            "warnings": warnings,
        }
        result["message"] = self._message(level, result, pick["infeasible"], tol)
        return result

    @staticmethod
    def _message(level: str, r: dict, reason: str | None, tol: float) -> str:
        pct = f"{100 * tol:g}%"
        if level == "covered":
            return f"A stored lattice is within {pct} of this target. The search should match quickly."
        if level == "extended":
            return f"No stored lattice is within {pct}. The search will try to design a new one."
        if level == "outside":
            return "This target is far from every stored lattice; a match is unlikely. See the closest achievable target."
        return f"No lattice can reach this: {reason}. The closest achievable target is shown."

    def nearest_ids(self, material: dict[str, Any], *, n: int = 20, **kw: Any) -> tuple[np.ndarray, float]:
        """Lattice ids of the n stored lattices nearest to the request at the density check() picks, and that density.
        Nearest = smallest mode-aware distance, ties broken by the two-sided distance."""
        res = self.check(material, **kw)
        i = int(np.argmin([abs(d - res["density"]) for d in self.densities]))
        modes = {"stiffness": "about", "strength": "at_least", "weight": "at_most", **(kw.get("modes") or {})}
        dist, dist2 = self._distance(material, i, kw.get("stiffness"), kw.get("strength"),
                                     bool(kw.get("yield_only")), modes, kw.get("tol", 0.10))
        order = np.lexsort((dist2, dist))[:n]
        return self.ids[i][order].astype(np.int64), self.densities[i]

    def snap(self, material: dict[str, Any], **kw: Any) -> dict[str, Any]:
        """The six values of the nearest stored lattice at the chosen density, and how far they moved."""
        r = self.check(material, **kw)
        return {"stiffness_gpa": r["nearest"]["stiffness_gpa"], "strength_mpa": r["nearest"]["strength_mpa"],
                "density": r["density"], "lattice_id": r["nearest"]["lattice_id"], "moved_pct": r["distance_pct"]}


_table: ReachTable | None = None
_table_error: str | None = None
_load_lock = threading.Lock()


def get_table() -> ReachTable:
    """Load the table once; raises ReachUnavailable with the reason when it cannot be loaded."""
    global _table, _table_error
    if _table is None:
        with _load_lock:
            if _table is None:
                try:
                    _table = ReachTable.load()
                    _table_error = None
                except ReachUnavailable as e:
                    _table_error = str(e)
                    raise
    return _table
