"""Mesh building blocks for the assembled implant. No boolean operations: shells are only ever concatenated.

* prisms(): closed 8/12-sided struts, outward normals, one shell each (same construction as the browser STL).
* extrude_polygon(): a closed prism of a shapely polygon (holes allowed), triangulated by shapely's constrained Delaunay.
* clip_and_cap(): the part of a closed mesh between two z planes, closed again with polygon caps.
"""
from __future__ import annotations

import numpy as np
import shapely
import trimesh
from shapely.geometry import MultiLineString, Polygon
from shapely.ops import polygonize, unary_union


def prisms(a: np.ndarray, b: np.ndarray, radius: float, sides: int = 8) -> tuple[np.ndarray, np.ndarray]:
    """Closed prisms from a[i] to b[i] with the given radius. Returns (vertices (n*(2*sides+2), 3), faces (n*4*sides, 3))."""
    n = len(a)
    d = b - a
    length = np.linalg.norm(d, axis=1)
    d = d / length[:, None]
    helper = np.where((np.abs(d[:, [0]]) < 0.9), np.array([[1.0, 0, 0]]), np.array([[0, 1.0, 0]]))
    u = np.cross(helper, d)
    u /= np.linalg.norm(u, axis=1)[:, None]
    v = np.cross(d, u)                                      # (u, v, d) right-handed
    th = 2 * np.pi * np.arange(sides) / sides
    ring = radius * (np.cos(th)[None, :, None] * u[:, None, :] + np.sin(th)[None, :, None] * v[:, None, :])    # (n, sides, 3)
    ra = a[:, None, :] + ring
    rb = b[:, None, :] + ring
    per = 2 * sides + 2
    verts = np.concatenate([ra, rb, a[:, None, :], b[:, None, :]], axis=1).reshape(-1, 3)       # per strut: ra, rb, centre a, centre b
    base = (np.arange(n) * per)[:, None]
    i = np.arange(sides)[None, :]
    j = (i + 1) % sides
    A0, A1 = base + i, base + j                        # ring a
    B0, B1 = base + sides + i, base + sides + j        # ring b
    ca, cb = base + 2 * sides, base + 2 * sides + 1
    faces = np.stack([
        np.stack([A0, A1, B1], -1), np.stack([A0, B1, B0], -1),          # side, outward
        np.stack([B0, B1, np.broadcast_to(cb, A0.shape)], -1),           # top cap, +d
        np.stack([A1, A0, np.broadcast_to(ca, A0.shape)], -1),           # bottom cap, -d
    ], axis=2).reshape(-1, 3)
    return verts, faces


def _triangles(poly: shapely.Geometry) -> list[np.ndarray]:
    tri = shapely.constrained_delaunay_triangles(poly)
    return [np.asarray(t.exterior.coords)[:3] for t in tri.geoms]


def extrude_polygon(poly: shapely.Geometry, z0: float, z1: float) -> trimesh.Trimesh:
    """Closed prism of `poly` (one polygon, holes allowed) between z0 and z1, outward normals."""
    parts = [p for p in (poly.geoms if hasattr(poly, "geoms") else [poly]) if p.geom_type == "Polygon" and p.area > 1e-9]
    verts: list[np.ndarray] = []
    faces: list[list[int]] = []
    for pg in parts:
        pg = shapely.geometry.polygon.orient(pg, 1.0)             # exterior counter-clockwise, holes clockwise
        base = sum(len(v) for v in verts)
        rings = [np.asarray(pg.exterior.coords)[:-1]] + [np.asarray(r.coords)[:-1] for r in pg.interiors]
        index: dict[tuple[float, float], int] = {}
        pts: list[tuple[float, float]] = []
        for r in rings:
            for p in r:
                key = (float(p[0]), float(p[1]))
                if key not in index:
                    index[key] = len(pts)
                    pts.append(key)
        xy = np.array(pts)
        n = len(xy)
        verts.append(np.vstack([np.c_[xy, np.full(n, z0)], np.c_[xy, np.full(n, z1)]]))
        for tri in _triangles(pg):
            ids = [index[(float(p[0]), float(p[1]))] for p in tri]
            area2 = (tri[1][0] - tri[0][0]) * (tri[2][1] - tri[0][1]) - (tri[2][0] - tri[0][0]) * (tri[1][1] - tri[0][1])
            if area2 < 0:
                ids = [ids[0], ids[2], ids[1]]
            faces.append([base + n + ids[0], base + n + ids[1], base + n + ids[2]])         # top (z1, second layer), normal +z
            faces.append([base + ids[0], base + ids[2], base + ids[1]])                      # bottom (z0, first layer), normal -z
        for r in rings:
            for k in range(len(r)):
                p, q = (float(r[k][0]), float(r[k][1])), (float(r[(k + 1) % len(r)][0]), float(r[(k + 1) % len(r)][1]))
                ip, iq = index[p], index[q]
                faces.append([base + ip, base + iq, base + n + iq])          # wall, outward (exterior ccw, holes cw)
                faces.append([base + ip, base + n + iq, base + n + ip])
    m = trimesh.Trimesh(np.vstack(verts), np.array(faces), process=False)
    return m


def _boundary_loops(mesh: trimesh.Trimesh) -> list[shapely.Geometry]:
    """Polygons (exact coordinates, even-odd nesting) bounded by the mesh's open edges, one list per call."""
    edges = mesh.edges_sorted
    uniq, counts = np.unique(edges, axis=0, return_counts=True)
    open_edges = uniq[counts == 1]
    return open_edges


def clip_and_cap(mesh: trimesh.Trimesh, z0: float, z1: float) -> trimesh.Trimesh:
    """The part of a closed mesh with z0 <= z <= z1, closed again with caps at both planes (own capping: no extra package)."""
    m = trimesh.intersections.slice_mesh_plane(mesh, [0, 0, 1], [0, 0, z0], cap=False)
    m = trimesh.intersections.slice_mesh_plane(m, [0, 0, -1], [0, 0, z1], cap=False)
    m.merge_vertices()
    open_edges = _boundary_loops(m)
    if len(open_edges) == 0:
        return m
    caps: list[list[int]] = []
    verts = np.asarray(m.vertices)
    for plane_z, sign in ((z0, -1.0), (z1, 1.0)):
        sel = open_edges[np.abs(verts[open_edges[:, 0], 2] - plane_z) < 1e-6]
        sel = sel[np.abs(verts[sel[:, 1], 2] - plane_z) < 1e-6]
        if len(sel) == 0:
            continue
        lines = MultiLineString([[tuple(verts[a][:2]), tuple(verts[b][:2])] for a, b in sel])
        polys = sorted(polygonize(unary_union(lines)), key=lambda p: -p.area)
        if not polys:
            continue
        poly = polys[0]
        for p in polys[1:]:
            poly = poly.symmetric_difference(p)
        lookup = {(float(verts[i][0]), float(verts[i][1])): int(i) for i in np.unique(sel)}
        for pg in (poly.geoms if hasattr(poly, "geoms") else [poly]):
            for tri in _triangles(pg):
                try:
                    ids = [lookup[(float(p[0]), float(p[1]))] for p in tri]
                except KeyError:
                    continue
                area2 = (tri[1][0] - tri[0][0]) * (tri[2][1] - tri[0][1]) - (tri[2][0] - tri[0][0]) * (tri[1][1] - tri[0][1])
                flip = (area2 < 0) != (sign < 0)
                caps.append([ids[0], ids[2], ids[1]] if flip else ids)
    if caps:
        m = trimesh.Trimesh(m.vertices, np.vstack([m.faces, np.array(caps)]), process=False)
    return m
