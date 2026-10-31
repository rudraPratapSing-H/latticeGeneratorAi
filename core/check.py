"""A small finite beam model of a lattice block: how much softer is a finite, plate-bonded block than the infinite lattice?

Not solver-verified: the verified numbers of a candidate come from the periodic (infinite) lattice solve in
strength-labels/lattice_strength.py. This module re-uses that file's Timoshenko element stiffness (`_local_k`, `_rotations`,
unchanged) on a finite block of whole cells with both end faces welded to rigid plates, applies an axial compression
along z and reports the block's stiffness. Results are labelled `beam_model_estimate`.

Units: the solver's own (cell = 2, E_s = 1); the result is a ratio times the material modulus.
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

from core import tiling

LABEL = "beam_model_estimate"
MAX_ELEMENTS = 40_000            # representative block: shrink nx, ny, nz until the model has at most this many struts
MAX_XY_CELLS = 5
MAX_Z_CELLS = 4

_mod = None


def _solver():
    """strength-labels/lattice_strength.py (folder name has a hyphen, so it is loaded by path)."""
    global _mod
    if _mod is None:
        path = Path(__file__).resolve().parent.parent / "strength-labels" / "lattice_strength.py"
        spec = importlib.util.spec_from_file_location("lattice_strength_for_check", path)
        _mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_mod)
    return _mod


def block_struts(lattice: dict[str, Any], nx: int, ny: int, nz: int) -> tuple[np.ndarray, np.ndarray]:
    """Struts of an nx x ny x nz block of cells (cell edge 2, origin at 0), shared faces merged."""
    ua, ub = tiling.unit_cell_struts(lattice)
    centres = np.array([[2 * i + 1.0, 2 * j + 1.0, 2 * k + 1.0] for i in range(nx) for j in range(ny) for k in range(nz)])
    a = (ua[None] + centres[:, None, :]).reshape(-1, 3)
    b = (ub[None] + centres[:, None, :]).reshape(-1, 3)
    return tiling._unique_struts(a, b)


def fit_block(lattice: dict[str, Any], nx: int, ny: int, nz: int) -> tuple[int, int, int]:
    """Shrink the block (z last) until it has at most MAX_ELEMENTS struts: a representative block, not the whole zone."""
    per_cell = len(tiling.unit_cell_struts(lattice)[0])
    nx, ny, nz = max(1, nx), max(1, ny), max(1, nz)
    while nx * ny * nz * per_cell > MAX_ELEMENTS and (nx > 1 or ny > 1 or nz > 2):
        if nx >= ny and nx > 1:
            nx -= 1
        elif ny > 1:
            ny -= 1
        else:
            nz -= 1
    return nx, ny, nz


def block_stiffness(lattice: dict[str, Any], r_solver: float, nx: int, ny: int, nz: int) -> dict[str, Any]:
    """Axial stiffness of the block in units of the material modulus (E_s = 1), end faces welded to rigid plates."""
    ls = _solver()
    a, b = block_struts(lattice, nx, ny, nz)
    key = np.round(np.vstack([a, b]) * tiling.KEY_SCALE).astype(np.int64)
    uniq, inv = np.unique(key, axis=0, return_inverse=True)
    inv = np.asarray(inv).ravel()
    ia, ib = inv[:len(a)], inv[len(a):]
    pos = uniq / tiling.KEY_SCALE
    n = len(uniq)
    d = b - a
    L = np.linalg.norm(d, axis=1)
    Kl, A, I, J = ls._local_k(L, r_solver)
    T = ls._rotations(d, L)
    Kg = np.einsum("mji,mjk,mkl->mil", T, Kl, T)
    idx = np.concatenate([6 * ia[:, None] + np.arange(6), 6 * ib[:, None] + np.arange(6)], axis=1)
    N6 = 6 * n
    K = coo_matrix((Kg.ravel(), (np.repeat(idx, 12, axis=1).ravel(), np.tile(idx, (1, 12)).ravel())), shape=(N6, N6)).tocsr()
    H = 2.0 * nz
    bottom = np.where(pos[:, 2] < 1e-6)[0]
    top = np.where(pos[:, 2] > H - 1e-6)[0]
    delta = 1e-3 * H
    fixed = np.concatenate([(6 * bottom[:, None] + np.arange(6)).ravel(), (6 * top[:, None] + np.arange(6)).ravel()])
    u = np.zeros(N6)
    u[(6 * top[:, None] + np.array([2])).ravel()] = -delta          # compression along z
    free = np.setdiff1d(np.arange(N6), fixed)
    rhs = -(K[free][:, fixed] @ u[fixed])
    u[free] = spsolve(K[free][:, free].tocsc(), rhs)
    f = K @ u
    reaction = float(-f[(6 * top + 2)].sum())                       # force pushing back on the top plate
    area = (2.0 * nx) * (2.0 * ny)
    e_block = (reaction / area) / (delta / H)
    return {"e_norm": float(e_block), "nodes": int(n), "struts": int(len(a)), "block_cells": [nx, ny, nz]}


def r_solver_of(lattice: dict[str, Any], cell_mm: float | None = None) -> float:
    """Strut radius in solver units (cell = 2) from the candidate's radius and cell size."""
    cell = cell_mm or lattice.get("cell_size_mm") or 1.0
    return float(lattice["strut_radius_mm"]) / float(cell) * 2.0


def zone_check(lattice: dict[str, Any], cell_mm: float, grid_cells: tuple[int, int, int], e_s_gpa: float,
               verified_z_gpa: float | None) -> dict[str, Any]:
    """Finite-block stiffness of one lattice zone along z next to the same lattice's infinite (periodic) value.

    Both numbers use the solver's element code at the same strut radius, so their ratio shows the finite-size effect
    (surface struts, welded plates) only. The candidate's own verified number is reported unchanged beside them."""
    nx, ny, nz = fit_block(lattice, min(grid_cells[0], MAX_XY_CELLS), min(grid_cells[1], MAX_XY_CELLS), min(grid_cells[2], MAX_Z_CELLS))
    r = r_solver_of(lattice, cell_mm)
    res = block_stiffness(lattice, r, nx, ny, nz)
    inf = periodic_c33(lattice, r)
    ratio = res["e_norm"] / inf if inf > 0 else None
    representative = [nx, ny, nz] != list(grid_cells)
    out = {"label": LABEL, "stiffness_z_gpa": res["e_norm"] * e_s_gpa, "infinite_lattice_z_gpa": inf * e_s_gpa,
           "ratio_to_infinite": ratio, "block_cells": [nx, ny, nz], "zone_cells": list(grid_cells), "struts": res["struts"],
           "representative": representative,
           "candidate_verified_z_gpa": float(verified_z_gpa) if verified_z_gpa else None,
           "note": ("Finite block with both ends welded to rigid plates, beam elements from the solver's own element code. "
                    "An estimate, not a solver-verified number." + (" A block of the zone, not the whole zone." if representative else ""))}
    if ratio is not None and not 0.8 <= ratio <= 1.25:
        out["warning"] = (f"The finite block is {100 * ratio:.0f}% of the infinite-lattice stiffness: with this few cells the surface "
                          "struts and plates matter. Treat the stiffness as an estimate.")
    return out


def periodic_c33(lattice: dict[str, Any], r_solver: float) -> float:
    """The infinite-lattice axial stiffness (E_s = 1) from the periodic solve, for the same cell and strut radius."""
    ls = _solver()
    nodes = np.asarray(lattice["nodes"], dtype=float)
    edges = np.asarray(lattice["edges"], dtype=int)
    n = len(nodes)
    adj = np.zeros((n, n))
    adj[edges[:, 0], edges[:, 1]] = adj[edges[:, 1], edges[:, 0]] = 1.0
    nn, ia, ib, d = ls.build_periodic_frame(adj, nodes)
    rho = math.pi * r_solver ** 2 * float(np.linalg.norm(d, axis=1).sum()) / ls.V
    return float(ls.solve_lattice(adj, nodes, rho=rho)["C"][2, 2])
