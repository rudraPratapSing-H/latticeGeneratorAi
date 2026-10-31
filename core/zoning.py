"""Implant zoning: STL in, slices, section properties, peak stress per slice, zones. numpy / trimesh / shapely only.

The implant frame: the long axis is +z, distal tip at z = 0, proximal end at the top, lengths in millimetres, the
cross-section's principal axes along x and y. Stress is in MPa (newtons and millimetres). Nothing here talks to the
search or the solver; core/profiles/implant.py holds every placeholder number.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import shapely
import trimesh
from shapely.geometry import MultiLineString, Polygon
from shapely.ops import polygonize, unary_union

from core.profiles import implant as profile

UNIT_SCALE = {"mm": 1.0, "m": 1000.0, "inch": 25.4}


class MeshProblem(ValueError):
    """A request about the mesh that cannot be served. `code` is the API error code; the message is plain language."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


# ------------------------------------------------------------------ loading and repair
def load_mesh(data: bytes) -> trimesh.Trimesh:
    """STL bytes (binary or ASCII) -> one mesh with merged vertices. Raises MeshProblem('bad_mesh')."""
    if not data or len(data) < 84:
        raise MeshProblem("bad_mesh", "This file is too small to be an STL. Upload a binary or ASCII STL file.")
    try:
        loaded = trimesh.load(io.BytesIO(data), file_type="stl", force="mesh")
    except Exception as e:  # noqa: BLE001 - trimesh raises many types
        raise MeshProblem("bad_mesh", f"This does not read as an STL file ({type(e).__name__}).") from e
    if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) < 4:
        raise MeshProblem("bad_mesh", "The STL has no usable triangles.")
    if not np.isfinite(loaded.vertices).all():
        raise MeshProblem("bad_mesh", "The STL contains NaN or infinite coordinates.")
    return loaded


def repair(mesh: trimesh.Trimesh) -> tuple[trimesh.Trimesh, list[str]]:
    """Try the cheap repairs (merge, winding, normals, small holes). Returns the mesh and what was done."""
    notes: list[str] = []
    m = mesh.copy()
    m.merge_vertices()
    m.remove_unreferenced_vertices()
    if not m.is_watertight:
        trimesh.repair.fix_winding(m)
        trimesh.repair.fix_inversion(m)
        trimesh.repair.fill_holes(m)
        if m.is_watertight:
            notes.append("Closed small holes in the mesh.")
    if m.is_watertight and m.volume < 0:
        m.invert()
        notes.append("Flipped inward-facing normals.")
    elif m.is_watertight:
        before = m.volume
        trimesh.repair.fix_normals(m)
        if (before > 0) != (m.volume > 0):
            notes.append("Fixed normal directions.")
    return m, notes


def split_bodies(mesh: trimesh.Trimesh) -> list[trimesh.Trimesh]:
    parts = mesh.split(only_watertight=False)
    return sorted(parts, key=lambda p: -abs(p.volume) if p.is_watertight else -p.area)


def guess_units(mesh: trimesh.Trimesh) -> dict[str, Any]:
    """Longest side outside 20 to 600 mm is not trusted: say what was measured and ask."""
    longest = float(np.max(mesh.extents))
    if 20.0 <= longest <= 600.0:
        return {"units": "mm", "confident": True, "longest_raw": longest}
    if 0.02 <= longest <= 0.6:
        return {"units": "m", "confident": False, "longest_raw": longest}
    if 0.8 <= longest < 20.0:
        return {"units": "inch", "confident": False, "longest_raw": longest}
    return {"units": None, "confident": False, "longest_raw": longest}


def fit_axis(mesh: trimesh.Trimesh) -> dict[str, Any]:
    """Long axis by PCA of the vertices. `ambiguous` when the two largest eigenvalues are within 1.5 x of each other."""
    pts = mesh.vertices - mesh.vertices.mean(axis=0)
    w, v = np.linalg.eigh(np.cov(pts.T))
    order = np.argsort(w)[::-1]
    w, v = w[order], v[:, order]
    ratio = float(math.sqrt(w[0] / max(w[1], 1e-12)))
    axis = v[:, 0]
    if axis[np.argmax(np.abs(axis))] < 0:
        axis = -axis
    snapped = False
    k = int(np.argmax(np.abs(axis)))
    if abs(axis[k]) > math.cos(math.radians(12.0)):        # a CAD export is usually axis-aligned: a bend must not tilt the frame
        axis, snapped = np.eye(3)[k], True
    return {"axis": axis.tolist(), "ratio": ratio, "ambiguous": ratio < 1.5, "snapped_to_coordinate_axis": snapped}


def to_implant_frame(mesh: trimesh.Trimesh, units: str, axis: list[float] | None, flip: bool = False) -> tuple[trimesh.Trimesh, dict[str, Any]]:
    """Scale to mm, rotate the long axis to +z, put the principal cross-section axes on x and y, tip at z = 0.

    Default orientation: the thicker end is proximal (top). `flip` reverses that choice.
    """
    if units not in UNIT_SCALE:
        raise MeshProblem("bad_units", f"Unknown units '{units}'. Choose mm, m or inch.")
    m = mesh.copy()
    m.apply_scale(UNIT_SCALE[units])
    ax = np.array(axis if axis is not None else fit_axis(m)["axis"], dtype=float)
    ax /= np.linalg.norm(ax)
    R = trimesh.geometry.align_vectors(ax, [0, 0, 1])
    m.apply_transform(R)
    xy = m.vertices[:, :2] - m.vertices[:, :2].mean(axis=0)
    w, v = np.linalg.eigh(np.cov(xy.T))
    ang = math.atan2(v[1, np.argmax(w)], v[0, np.argmax(w)])
    Rz = trimesh.transformations.rotation_matrix(-ang, [0, 0, 1])
    m.apply_transform(Rz)
    top_thicker = _end_area(m, top=True) >= _end_area(m, top=False)
    auto_flipped = not top_thicker
    if auto_flipped:
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))
    if flip:
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))
    lo = m.bounds[0]
    m.apply_translation([-(m.bounds[0][0] + m.bounds[1][0]) / 2, -(m.bounds[0][1] + m.bounds[1][1]) / 2, -lo[2]])
    return m, {"units": units, "scale": UNIT_SCALE[units], "axis_in": ax.tolist(), "auto_flipped": auto_flipped, "flip": bool(flip),
               "length_mm": float(m.extents[2])}


def _end_area(mesh: trimesh.Trimesh, top: bool) -> float:
    lo, hi = mesh.bounds[0][2], mesh.bounds[1][2]
    span = hi - lo
    z = hi - 0.1 * span if top else lo + 0.1 * span
    poly = section_polygon(mesh, z)
    return float(poly.area) if poly is not None else 0.0


# ------------------------------------------------------------------ sections
def section_polygon(mesh: trimesh.Trimesh, z: float) -> shapely.Geometry | None:
    """Cross-section of the closed mesh at height z as a shapely polygon (holes by even-odd), or None when empty."""
    segs = trimesh.intersections.mesh_plane(mesh, [0, 0, 1], [0, 0, z], return_faces=False)
    if segs is None or len(segs) == 0:
        return None
    segs = np.round(segs[:, :, :2], 5)            # equal end points must be bit-identical for polygonize
    lines = MultiLineString([[tuple(a), tuple(b)] for a, b in segs])
    polys = sorted(polygonize(unary_union(lines)), key=lambda p: -p.area)
    if not polys:
        return None
    out = polys[0]
    for p in polys[1:]:                           # nested loops alternate solid / hole
        out = out.symmetric_difference(p)
    return out if not out.is_empty else None


def ring_moments(coords: np.ndarray) -> tuple[float, float, float, float, float]:
    """Signed area and first/second area moments about the origin of one closed ring (Green's theorem)."""
    x, y = coords[:-1, 0], coords[:-1, 1]
    x1, y1 = np.roll(x, -1), np.roll(y, -1)
    cr = x * y1 - x1 * y
    a = cr.sum() / 2
    cx = ((x + x1) * cr).sum() / 6
    cy = ((y + y1) * cr).sum() / 6
    ixx = ((y * y + y * y1 + y1 * y1) * cr).sum() / 12     # integral of y^2 dA
    iyy = ((x * x + x * x1 + x1 * x1) * cr).sum() / 12     # integral of x^2 dA
    ixy = ((x * y1 + 2 * x * y + 2 * x1 * y1 + x1 * y) * cr).sum() / 24
    return a, cx, cy, ixx, iyy, ixy


def section_properties(poly: shapely.Geometry) -> dict[str, Any]:
    """Area, centroid and second moments about the centroid (exact for polygons with holes)."""
    parts = list(poly.geoms) if hasattr(poly, "geoms") else [poly]
    A = Sx = Sy = Ixx0 = Iyy0 = Ixy0 = 0.0
    verts: list[np.ndarray] = []
    for pg in parts:
        if pg.is_empty or pg.geom_type != "Polygon":
            continue
        rings = [(np.asarray(pg.exterior.coords), 1.0)] + [(np.asarray(r.coords), -1.0) for r in pg.interiors]
        for c, sign in rings:
            a, cx, cy, ixx, iyy, ixy = ring_moments(c)
            s = sign * (1.0 if a > 0 else -1.0)          # orientation-independent
            A += s * a; Sx += s * cx; Sy += s * cy
            Ixx0 += s * ixx; Iyy0 += s * iyy; Ixy0 += s * ixy
        verts.append(np.asarray(pg.exterior.coords)[:-1])
    ccx, ccy = Sx / A, Sy / A
    return {"area": A, "cx": ccx, "cy": ccy,
            "Sxx": Iyy0 - A * ccx ** 2,       # integral of (x - cx)^2 dA  (civil "Iyy")
            "Syy": Ixx0 - A * ccy ** 2,       # integral of (y - cy)^2 dA  (civil "Ixx")
            "Sxy": Ixy0 - A * ccx * ccy,
            "verts": np.vstack(verts)}


@dataclass
class Slice:
    z: float
    area: float
    cx: float
    cy: float
    Sxx: float
    Syy: float
    Sxy: float
    verts: np.ndarray = field(repr=False)
    dx: float = 0.0
    dy: float = 0.0

    @property
    def thickness(self) -> float:
        return min(self.dx, self.dy)


def slice_stack(mesh: trimesh.Trimesh, step_mm: float | None = None, max_slices: int = 200) -> list[Slice]:
    """Slices perpendicular to z, spaced `step_mm` (at most `max_slices`). Slices under 1% of the largest area are
    skipped; the end slices inherit their neighbour (a cap face has no section of its own)."""
    L = float(mesh.bounds[1][2] - mesh.bounds[0][2])
    if L < 5.0:
        raise MeshProblem("bad_mesh", f"The implant is only {L:.2f} mm long along its long axis. Check the units and the axis.")
    step = step_mm or profile.GEOMETRY["slice_step_mm"]["value"]
    n = int(min(max_slices, max(3, round(L / step))))
    zs = np.linspace(0.0, L, n + 1)
    zs = 0.5 * (zs[:-1] + zs[1:])                       # mid-points: no slice exactly on an end cap
    out: list[Slice] = []
    for z in zs:
        poly = section_polygon(mesh, float(z))
        if poly is None or poly.is_empty:
            continue
        p = section_properties(poly)
        minx, miny, maxx, maxy = poly.bounds
        out.append(Slice(float(z), p["area"], p["cx"], p["cy"], p["Sxx"], p["Syy"], p["Sxy"], p["verts"], maxx - minx, maxy - miny))
    if not out:
        raise MeshProblem("bad_mesh", "The mesh has no cross-sections along its long axis. Check the axis and units.")
    biggest = max(s.area for s in out)
    out = [s for s in out if s.area >= 0.01 * biggest]
    return out


# ------------------------------------------------------------------ stress
def slice_stress(slices: list[Slice], force_n: float, angle_deg: float, lateral: tuple[float, float] = (-1.0, 0.0),
                 load_point: tuple[float, float, float] | None = None) -> list[dict[str, float]]:
    """Peak |stress| (MPa) per slice for one compressive load.

    The load acts at `load_point` (default: the centroid of the top slice) along a line tilted `angle_deg` from the
    axis towards `lateral`. At each slice the axial component N = F cos(a) is eccentric by the horizontal offset between
    the load line and the slice centroid, so sigma(r) = N/A + N a^T S^-1 r with S the second-moment matrix of the
    section. Evaluated at the polygon vertices, so no principal-axis search is needed (bug watchlist 17).
    """
    top = slices[-1]
    px, py, pz = load_point or (top.cx, top.cy, top.z)
    th = math.radians(angle_deg)
    N = force_n * math.cos(th)
    ux, uy = lateral
    out = []
    for s in slices:
        d = (pz - s.z) * math.tan(th)
        ax_, ay_ = px + ux * d - s.cx, py + uy * d - s.cy
        S = np.array([[s.Sxx, s.Sxy], [s.Sxy, s.Syy]])
        r = s.verts - np.array([s.cx, s.cy])
        sigma = N / s.area + N * (np.array([ax_, ay_]) @ np.linalg.solve(S, r.T))
        out.append({"z": s.z, "peak_mpa": float(np.max(np.abs(sigma))), "axial_mpa": N / s.area,
                    "moment_nmm": float(N * math.hypot(ax_, ay_)), "eccentricity_mm": float(math.hypot(ax_, ay_))})
    return out


def governing_stress(slices: list[Slice], cases: list[dict[str, Any]], safety_factor: float, **kw: Any) -> tuple[list[dict[str, float]], str]:
    """Largest peak stress per slice over the load cases, times the safety factor. Returns the table and the case names used."""
    best: list[dict[str, float]] | None = None
    names: list[str] = []
    for c in cases:
        rows = slice_stress(slices, c["force_n"], c["angle_deg"], **kw)
        for r in rows:
            r["case"] = c["name"]
        if best is None:
            best = rows
        else:
            best = [b if b["peak_mpa"] >= r["peak_mpa"] else r for b, r in zip(best, rows)]
        names.append(c["name"])
    assert best is not None
    for r in best:
        r["design_mpa"] = r["peak_mpa"] * safety_factor
    return best, names


# ------------------------------------------------------------------ zones
def make_zones(slices: list[Slice], stress: list[dict[str, float]], length_mm: float,
               ratio: float | None = None, min_zones: int | None = None, max_zones: int | None = None) -> list[dict[str, Any]]:
    """Merge neighbouring slices with similar design stress and thickness into min..max zones (distal first)."""
    ratio = ratio or profile.GEOMETRY["zone_merge_ratio"]["value"]
    lo_n = min_zones or profile.GEOMETRY["min_zones"]
    hi_n = max_zones or profile.GEOMETRY["max_zones"]
    sig = np.array([r["design_mpa"] for r in stress])
    th = np.array([s.thickness for s in slices])
    z = np.array([s.z for s in slices])

    groups: list[list[int]] = [[0]]
    for i in range(1, len(slices)):
        g = groups[-1]
        ms, mt = float(np.mean(sig[g])), float(np.mean(th[g]))
        ok_s = max(sig[i], ms) / max(min(sig[i], ms), 1e-9) <= ratio
        ok_t = max(th[i], mt) / max(min(th[i], mt), 1e-9) <= ratio
        if ok_s and ok_t:
            g.append(i)
        else:
            groups.append([i])
    while len(groups) > hi_n:                                   # merge the pair of neighbours that differ least
        diffs = [abs(math.log(max(np.mean(sig[a]), 1e-9) / max(np.mean(sig[b]), 1e-9))) for a, b in zip(groups[:-1], groups[1:])]
        k = int(np.argmin(diffs))
        groups[k:k + 2] = [groups[k] + groups[k + 1]]
    while len(groups) < lo_n:                                   # split the longest group in two
        k = int(np.argmax([len(g) for g in groups]))
        g = groups[k]
        if len(g) < 2:
            break
        groups[k:k + 1] = [g[: len(g) // 2], g[len(g) // 2:]]

    bounds = [0.0] + [float((z[g[-1]] + z[nxt[0]]) / 2) for g, nxt in zip(groups[:-1], groups[1:])] + [float(length_mm)]
    zones = []
    for i, g in enumerate(groups):
        zones.append({
            "id": f"z{i + 1}",
            "range_mm": [bounds[i], bounds[i + 1]],
            "thickness_mm": float(np.min(th[g])),
            "area_mm2": float(np.mean([slices[j].area for j in g])),
            "stress_mpa": float(np.max(sig[g])),
            "axial_mpa": float(np.max([stress[j]["axial_mpa"] * 1.0 for j in g])),
            "slices": len(g),
        })
    return zones


def name_zones(zones: list[dict[str, Any]], length_mm: float) -> None:
    """Names from the bone region at the zone's mid position (tip, mid stem, upper stem, neck)."""
    for zn in zones:
        mid = (zn["range_mm"][0] + zn["range_mm"][1]) / 2 / max(length_mm, 1e-9)
        zn["name"] = profile.region_for(mid)["name"]
        zn["position"] = mid


def snap_to_grid(zones: list[dict[str, Any]], cell_mm: float, min_cells: int | None = None) -> list[str]:
    """Move zone ends to the global cell grid (multiples of cell_mm from the tip), in place. A zone shorter than
    `min_cells` cells is merged into the neighbour whose stress is closer. Returns plain-language notes of what moved."""
    min_cells = min_cells or profile.GEOMETRY["min_zone_cells"]
    notes: list[str] = []
    length = zones[-1]["range_mm"][1]
    bounds = [0.0]
    for zn in zones[:-1]:
        raw = zn["range_mm"][1]
        snapped = round(raw / cell_mm) * cell_mm
        if abs(snapped - raw) > 1e-6:
            notes.append(f"The boundary after {zn['name']} moved from {raw:.1f} to {snapped:.1f} mm to sit on the {cell_mm:g} mm cell grid.")
        bounds.append(snapped)
    bounds.append(length)
    zs = list(zones)
    while len(zs) > 1:
        spans = [bounds[k + 1] - bounds[k] for k in range(len(zs))]
        short = [k for k, sp in enumerate(spans) if sp < min_cells * cell_mm - 1e-6]
        if not short:
            break
        i = min(short, key=lambda k: spans[k])
        if i == 0:
            j = 1
        elif i == len(zs) - 1:
            j = i - 1
        else:
            j = i - 1 if abs(zs[i]["stress_mpa"] - zs[i - 1]["stress_mpa"]) <= abs(zs[i]["stress_mpa"] - zs[i + 1]["stress_mpa"]) else i + 1
        notes.append(f"{zs[i]['name']} would be {spans[i]:.1f} mm, under {min_cells} cells, and was merged into {zs[j]['name']}.")
        zs[j]["stress_mpa"] = max(zs[j]["stress_mpa"], zs[i]["stress_mpa"])
        zs[j]["thickness_mm"] = min(zs[j]["thickness_mm"], zs[i]["thickness_mm"])
        del bounds[i if j < i else i + 1]
        del zs[i]
    for k, zn in enumerate(zs):
        zn["range_mm"] = [bounds[k], bounds[k + 1]]
        zn["id"] = f"z{k + 1}"
    zones[:] = zs
    return notes


STRUT_RATIO = {0.05: 0.0297, 0.15: 0.039, 0.25: 0.045}      # strut radius / cell size at the three dataset densities (real candidates)


def cell_range(min_thickness_mm: float, cells_across: int | None = None) -> tuple[float, float]:
    """(lower, upper) allowed cell size in mm. Upper: thinnest lattice zone / N cells. Lower: the strut must be at least
    0.4 mm thick at the densest dataset density (the least demanding one)."""
    n = cells_across or profile.GEOMETRY["cells_across_thinnest"]["value"]
    lower = profile.GEOMETRY["min_strut_mm"] / (2 * STRUT_RATIO[0.25])
    return lower, min_thickness_mm / n
