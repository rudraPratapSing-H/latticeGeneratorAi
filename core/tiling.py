"""Tile one zone's chosen lattice cell on the implant's single global grid, keeping whole cells only.

Frame: implant frame (z along the long axis, tip at 0, millimetres). Grid pitch = the implant cell size; the grid origin
is the implant's bounding-box minimum in x and y and z = 0, so zone boundaries (multiples of the pitch) fall on grid planes.
A cell is kept only when its square footprint lies inside the implant section at its bottom, middle and top height, so cell
properties stay exact (a cell is never cut). Struts on faces shared by neighbouring cells are merged (same position = one strut).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import shapely
import trimesh
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from core import zoning

SIGNS = np.array([[sx, sy, sz] for sx in (1, -1) for sy in (1, -1) for sz in (1, -1)], dtype=float)
KEY_SCALE = 1e4          # positions compared at 0.1 micrometre


def unit_cell_struts(lattice: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """The full cell [-1, 1]^3 from the stored octant: mirror about x = 0, y = 0, z = 0 and merge identical struts.
    Struts on opposite faces are both kept (tiling merges them across neighbours; the outer faces keep theirs)."""
    nodes = np.asarray(lattice["nodes"], dtype=float)
    edges = np.asarray(lattice["edges"], dtype=int)
    a = (nodes[edges[:, 0]][None] * SIGNS[:, None]).reshape(-1, 3)
    b = (nodes[edges[:, 1]][None] * SIGNS[:, None]).reshape(-1, 3)
    keep = np.linalg.norm(b - a, axis=1) > 1e-5
    return _unique_struts(a[keep], b[keep])


def _unique_struts(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Undirected, de-duplicated struts: each strut's two ends are put in lexicographic order, then equal rows merge."""
    ka, kb = np.round(a * KEY_SCALE).astype(np.int64), np.round(b * KEY_SCALE).astype(np.int64)
    first_diff = np.zeros(len(a), dtype=np.int64)
    for c in (2, 1, 0):                                      # the first coordinate (x, then y, then z) that differs decides
        d = ka[:, c] - kb[:, c]
        first_diff = np.where(d != 0, d, first_diff)
    swap = first_diff > 0
    a2 = np.where(swap[:, None], b, a)
    b2 = np.where(swap[:, None], a, b)
    keys = np.round(np.hstack([a2, b2]) * KEY_SCALE).astype(np.int64)
    _, idx = np.unique(keys, axis=0, return_index=True)
    idx = np.sort(idx)
    return a2[idx], b2[idx]


@dataclass
class Grid:
    pitch: float
    x0: float
    y0: float
    nx: int
    ny: int
    cells: list[tuple[int, int, int]] = field(default_factory=list)       # (i, j, k) kept


def implant_grid_origin(frame: trimesh.Trimesh) -> tuple[float, float]:
    return float(frame.bounds[0][0]), float(frame.bounds[0][1])


def cells_for_range(frame: trimesh.Trimesh, z0: float, z1: float, pitch: float) -> Grid:
    """Whole cells of the global grid inside the implant between z0 and z1 (both on grid planes)."""
    x0, y0 = implant_grid_origin(frame)
    nx = int(np.ceil((frame.bounds[1][0] - x0) / pitch))
    ny = int(np.ceil((frame.bounds[1][1] - y0) / pitch))
    k0, k1 = int(round(z0 / pitch)), int(round(z1 / pitch))
    grid = Grid(pitch, x0, y0, nx, ny)
    ii, jj = np.meshgrid(np.arange(nx), np.arange(ny), indexing="ij")
    ii, jj = ii.ravel(), jj.ravel()
    boxes = shapely.box(x0 + ii * pitch, y0 + jj * pitch, x0 + (ii + 1) * pitch, y0 + (jj + 1) * pitch)
    for k in range(k0, k1):
        ok = np.ones(len(boxes), dtype=bool)
        for frac in (0.05, 0.5, 0.95):                      # bottom, middle, top of the cell
            poly = zoning.section_polygon(frame, (k + frac) * pitch)
            if poly is None:
                ok[:] = False
                break
            ok &= shapely.contains(poly, boxes)
        for i, j in zip(ii[ok], jj[ok]):
            grid.cells.append((int(i), int(j), int(k)))
    return grid


def tile(lattice: dict[str, Any], grid: Grid, cell_mm: float) -> tuple[np.ndarray, np.ndarray, float]:
    """Struts (mm, implant frame) of the kept cells, merged across shared faces, and the strut radius (mm, from the
    candidate; rescaled only if the candidate was made for another cell size)."""
    ua, ub = unit_cell_struts(lattice)
    half = cell_mm / 2.0
    radius = float(lattice["strut_radius_mm"])
    if lattice.get("cell_size_mm") and abs(lattice["cell_size_mm"] - cell_mm) > 1e-9:
        radius *= cell_mm / lattice["cell_size_mm"]
    if not grid.cells:
        return np.zeros((0, 3)), np.zeros((0, 3)), radius
    centres = np.array([[grid.x0 + (i + 0.5) * grid.pitch, grid.y0 + (j + 0.5) * grid.pitch, (k + 0.5) * grid.pitch]
                        for i, j, k in grid.cells])
    a = (ua[None] * half + centres[:, None, :]).reshape(-1, 3)
    b = (ub[None] * half + centres[:, None, :]).reshape(-1, 3)
    a, b = _unique_struts(a, b)
    return a, b, radius


def remove_fragments(a: np.ndarray, b: np.ndarray, min_fraction: float = 0.01) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Drop strut groups that are not connected to the main lattice when they hold under `min_fraction` of the struts.
    Returns the cleaned struts and a report: components, struts removed, share of the main part."""
    n = len(a)
    if n == 0:
        return a, b, {"components": 0, "removed": 0, "main_share": 1.0}
    ids = np.round(np.vstack([a, b]) * KEY_SCALE).astype(np.int64)
    _, inv = np.unique(ids, axis=0, return_inverse=True)
    inv = np.asarray(inv).ravel()
    ia, ib = inv[:n], inv[n:]
    nn = int(inv.max()) + 1
    g = coo_matrix((np.ones(n), (ia, ib)), shape=(nn, nn))
    ncomp, labels = connected_components(g, directed=False)
    strut_label = labels[ia]
    counts = np.bincount(strut_label, minlength=ncomp)
    main = int(np.argmax(counts))
    drop = (counts[strut_label] < min_fraction * n) & (strut_label != main)
    return a[~drop], b[~drop], {"components": int(ncomp), "removed": int(drop.sum()), "main_share": float(counts[main] / n)}
