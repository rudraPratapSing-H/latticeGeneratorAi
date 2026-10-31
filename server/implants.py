"""Implant endpoints: upload, confirm (frame + zones), zone table, edits. Files live in runs/implants/<id>/.

Geometry (mesh repair, slicing, zoning) is CPU work: it runs in a thread, never on the event loop.
"""
from __future__ import annotations

import asyncio
import json
import threading
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from core import implant_plan, reach as reach_mod, zoning
from core.profiles import describe
from core.profiles import implant as profile
from server import units
from server.finalize import sanitize
from server.implant_schemas import (
    AssembleRequest,
    ConfirmImplantRequest,
    CreateImplantResponse,
    ImplantFields,
    ZoneEditRequest,
    ZoneTable,
)
from server.picker import BadTarget, material_or_raise
from server.store import DEFAULT_RUNS_DIR

router = APIRouter(prefix="/api/implants", tags=["implants"])
MAX_UPLOAD_BYTES = 60 * 1024 * 1024
_locks: dict[str, threading.Lock] = {}
_prepared: dict[str, dict[str, Any]] = {}


def root() -> Path:
    d = Path(DEFAULT_RUNS_DIR) / "implants"
    d.mkdir(parents=True, exist_ok=True)
    return d


def idir(implant_id: str) -> Path:
    d = root() / implant_id
    if not d.is_dir() or not implant_id.startswith("i_"):
        raise HTTPException(status_code=404, detail=f"Implant {implant_id} not found")
    return d


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(sanitize(data), indent=2, allow_nan=False), encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except (OSError, json.JSONDecodeError):
        return default


def lock(implant_id: str) -> threading.Lock:
    return _locks.setdefault(implant_id, threading.Lock())


# ------------------------------------------------------------------ service functions (blocking; called in a thread)
def create_implant(data: bytes, material: str, description: str, parse=describe.parse_offline) -> dict[str, Any]:
    material_or_raise(material)
    try:
        raw = zoning.load_mesh(data)
        fixed, repairs = zoning.repair(raw)
        bodies = zoning.split_bodies(fixed)
    except zoning.MeshProblem as e:
        raise BadTarget(e.message, code=e.code, field="stl_file") from e
    body = bodies[0]
    warnings: list[str] = []
    if len(bodies) > 1:
        warnings.append(f"The file has {len(bodies)} separate pieces. The largest one is used; send body_index to pick another.")
    if not body.is_watertight:
        raise BadTarget("The mesh is not closed (it has holes or loose edges that could not be repaired automatically), so it cannot be "
                        "sliced. Close the holes in your CAD tool and upload again.", code="bad_mesh", field="stl_file")
    g = zoning.guess_units(body)
    ax = zoning.fit_axis(body)
    scale = zoning.UNIT_SCALE.get(g["units"] or "mm", 1.0)
    if not g["confident"]:
        warnings.append("The size does not look like millimetres. Check the units: the longest side measures "
                        f"{g['longest_raw']:.3g} in the file's own units.")
    if ax["ambiguous"]:
        warnings.append("There is no clear long axis (the body is almost as wide as it is long). Pick the axis and the direction.")
    implant_id = f"i_{uuid.uuid4().hex[:8]}"
    d = root() / implant_id
    d.mkdir(parents=True)
    (d / "mesh.stl").write_bytes(data)
    parsed = parse(description)
    fields = describe.clean_fields(parsed)
    report = {"watertight": True, "bodies": len(bodies), "size_mm": [float(v * scale) for v in body.extents],
              "guessed_units": g["units"], "units_confident": bool(g["confident"]), "volume_mm3": float(abs(body.volume) * scale ** 3),
              "axis_ratio": ax["ratio"], "axis_ambiguous": bool(ax["ambiguous"]), "repairs": repairs, "warnings": warnings}
    write_json(d / "implant.json", {"implant_id": implant_id, "state": "uploaded", "material": material, "description": description,
                                    "fields": fields, "mesh_report": report, "parsed_by": parsed.get("parsed_by", "offline"),
                                    "parse_notes": parsed.get("notes", [])})
    return {"implant_id": implant_id, "mesh_report": report, "fields": fields, "parsed_by": parsed.get("parsed_by", "offline"),
            "parse_notes": parsed.get("notes", []),
            "suggested": {"units": g["units"], "axis": "auto", "flip": False}}


def prepare(implant_id: str) -> dict[str, Any]:
    """Frame mesh, slices and stress for a confirmed implant (cached; rebuilt from the saved mesh after a restart)."""
    meta = read_json(idir(implant_id) / "implant.json")
    if meta.get("state") != "confirmed":
        raise BadTarget("Confirm the units, axis and fields first (POST /api/implants/{id}/confirm).", code="not_confirmed")
    key = json.dumps(meta["confirm"], sort_keys=True)
    cached = _prepared.get(implant_id)
    if cached and cached["key"] == key:
        return cached
    c = meta["confirm"]
    raw = zoning.load_mesh((idir(implant_id) / "mesh.stl").read_bytes())
    fixed, _ = zoning.repair(raw)
    bodies = zoning.split_bodies(fixed)
    if c["body_index"] >= len(bodies):
        raise BadTarget(f"The file has {len(bodies)} piece(s); body_index {c['body_index']} does not exist.", code="bad_mesh")
    body = bodies[c["body_index"]]
    axis = None if c["axis"] == "auto" else np.eye(3)[{"x": 0, "y": 1, "z": 2}[c["axis"]]].tolist()
    frame, info = zoning.to_implant_frame(body, c["units"], axis, c["flip"])
    slices = zoning.slice_stack(frame)
    loads = profile.load_cases_for(c["fields"])
    stress, _ = zoning.governing_stress(slices, loads["cases"], loads["safety_factor"])
    cached = {"key": key, "frame": frame, "info": info, "slices": slices, "stress": stress, "loads": loads}
    _prepared[implant_id] = cached
    return cached


def zone_table(implant_id: str, edits: dict[str, Any] | None = None) -> dict[str, Any]:
    d = idir(implant_id)
    meta = read_json(d / "implant.json")
    material = material_or_raise(meta["material"])
    prep = prepare(implant_id)
    cell = meta["confirm"].get("cell_mm")
    if edits and edits.get("cell_mm"):
        cell = edits["cell_mm"]
    plan = implant_plan.build_zone_table(prep["slices"], prep["stress"], prep["info"]["length_mm"], meta["confirm"]["fields"], material,
                                         cell_mm=None if cell is None else float(cell), edits=edits)
    loads = prep["loads"]
    table = {
        "implant_id": implant_id, "state": "confirmed", "length_mm": prep["info"]["length_mm"], "cell_mm": plan["cell_mm"],
        "cell_range_mm": plan["cell_range_mm"],
        "load": {"cases": [{"name": c["name"], "force_n": c["force_n"], "angle_deg": c["angle_deg"]} for c in loads["cases"]],
                 "governing": {k: loads["governing"][k] for k in ("name", "force_n", "angle_deg")},
                 "safety_factor": loads["safety_factor"], "supported_weight_kg": loads["supported_weight_kg"],
                 "assumptions": loads["assumptions"]},
        "zones": plan["zones"], "notes": plan["notes"], "warnings": plan["warnings"],
    }
    write_json(d / "zones.json", table)
    return table


def confirm(implant_id: str, body: dict[str, Any]) -> dict[str, Any]:
    d = idir(implant_id)
    with lock(implant_id):
        meta = read_json(d / "implant.json")
        try:
            profile.load_cases_for(body["fields"])            # absurd weight etc. is refused here, in plain words
        except ValueError as e:
            raise BadTarget(str(e), code="bad_fields", field="fields.body_weight_kg") from e
        meta["state"] = "confirmed"
        meta["confirm"] = {k: body[k] for k in ("units", "axis", "flip", "body_index", "fields", "cell_mm")}
        meta["fields"] = body["fields"]
        write_json(d / "implant.json", meta)
        _prepared.pop(implant_id, None)
        try:
            return zone_table(implant_id)
        except zoning.MeshProblem as e:
            raise BadTarget(e.message, code=e.code) from e


def edit_zones(implant_id: str, edit: dict[str, Any]) -> dict[str, Any]:
    prep = None
    with lock(implant_id):
        meta = read_json(idir(implant_id) / "implant.json")
        if meta.get("state") != "confirmed":
            raise BadTarget("Confirm the implant first.", code="not_confirmed")
        prep = prepare(implant_id)
        zs = edit.get("zones")
        if zs:
            zs = sorted(zs, key=lambda z: z["range_mm"][0])
            length = prep["info"]["length_mm"]
            ok = abs(zs[0]["range_mm"][0]) < 0.5 and abs(zs[-1]["range_mm"][1] - length) < 0.5
            ok = ok and all(abs(a["range_mm"][1] - b["range_mm"][0]) < 0.5 and a["range_mm"][1] > a["range_mm"][0] for a, b in zip(zs, zs[1:]))
            ok = ok and zs[-1]["range_mm"][1] > zs[-1]["range_mm"][0] and 2 <= len(zs) <= profile.GEOMETRY["max_zones"]
            if not ok:
                raise BadTarget(f"Zones must follow each other from 0 to {length:.1f} mm without gaps (2 to {profile.GEOMETRY['max_zones']} zones).",
                                code="bad_zones", field="zones")
            edit = {**edit, "zones": [{**z, "range_mm": [max(0.0, z["range_mm"][0]), min(length, z["range_mm"][1])]} for z in zs]}
        return zone_table(implant_id, edit)


# ------------------------------------------------------------------ routes
async def _bg(fn, *a):
    return await asyncio.get_running_loop().run_in_executor(None, fn, *a)


@router.post("", response_model=CreateImplantResponse, status_code=201)
async def post_implant(stl_file: UploadFile = File(...), material: str = Form("ti64"), description: str = Form("")) -> dict:
    data = await stl_file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise BadTarget(f"The file is larger than {MAX_UPLOAD_BYTES // 2 ** 20} MB.", code="bad_mesh", field="stl_file")
    return sanitize(await _bg(create_implant, data, material, description[:4000], _parser()))


def _parser():
    from server import describe_service
    return describe_service.parse


@router.get("/{implant_id}")
async def get_implant(implant_id: str) -> dict:
    d = idir(implant_id)
    meta = read_json(d / "implant.json")
    zt = read_json(d / "zones.json", {})
    return sanitize({"implant_id": implant_id, "state": meta["state"], "material": meta["material"], "fields": meta["fields"],
                     "mesh_report": meta["mesh_report"], "cell_mm": zt.get("cell_mm"),
                     "zones": [{"id": z["id"], "name": z["name"], "kind": z["kind"]} for z in zt.get("zones", [])],
                     "jobs": read_json(d / "jobs.json", {}), "assembly": read_json(d / "assembly.json")})


@router.post("/{implant_id}/confirm", response_model=ZoneTable)
async def post_confirm(implant_id: str, payload: ConfirmImplantRequest) -> dict:
    idir(implant_id)
    return sanitize(await _bg(confirm, implant_id, payload.model_dump(mode="json")))


@router.get("/{implant_id}/zones", response_model=ZoneTable)
async def get_zones(implant_id: str) -> dict:
    d = idir(implant_id)
    zt = read_json(d / "zones.json")
    if zt is None:
        meta = read_json(d / "implant.json")
        return {"implant_id": implant_id, "state": meta["state"], "zones": []}
    return sanitize(zt)


@router.put("/{implant_id}/zones", response_model=ZoneTable)
async def put_zones(implant_id: str, payload: ZoneEditRequest) -> dict:
    idir(implant_id)
    return sanitize(await _bg(edit_zones, implant_id, payload.model_dump(mode="json", exclude_none=False)))


# ------------------------------------------------------------------ zone searches (ordinary design jobs, one per lattice zone)
def zone_request(zt: dict[str, Any], zone: dict[str, Any], material: str, frame_extents: list[float]):
    """The DesignRequest for one lattice zone: snapped targets along z, the picker's density, the implant's cell size."""
    from server.schemas import DesignRequest
    req = zone["requirement"]
    snap = (zone.get("reach") or {}).get("snapped")
    k, s = req["stiffness_gpa"]["z"], req["strength_mpa"]["z"]
    kz = snap["stiffness_gpa"]["z"] if (snap and k["source"] == "automatic") else k["value"]
    sz = snap["strength_mpa"]["z"] if (snap and s["source"] == "automatic") else s["value"]
    size = [float(frame_extents[0]), float(frame_extents[1]), float(zone["range_mm"][1] - zone["range_mm"][0])]
    target: dict[str, Any] = {"rel_density": float(zone["reach"]["density"])}
    if kz:
        target["stiffness_gpa"] = {"z": float(kz)}
    if sz:
        target["strength_mpa"] = {"z": float(sz)}
    return DesignRequest(material=material, part={"size_mm": size, "cell_mm": float(zt["cell_mm"])}, target=target,
                         modes={"stiffness": "about", "strength": "at_least", "weight": "about"}, tolerance_pct=10.0, n_results=5)


def search_zones(implant_id: str) -> dict[str, str]:
    from server.design_service import submit_design
    d = idir(implant_id)
    zt = read_json(d / "zones.json")
    if not zt or not zt.get("zones"):
        raise BadTarget("Confirm the implant first (POST /api/implants/{id}/confirm).", code="not_confirmed")
    undecided = [z for z in zt["zones"] if z["kind"] == "undecided"]
    if undecided:
        raise BadTarget(f"{undecided[0]['name']} is undecided: choose solid or lattice (PUT zones with kind) before searching.",
                        code="undecided_zone", field="zones")
    meta = read_json(d / "implant.json")
    prep = prepare(implant_id)
    extents = [float(v) for v in prep["frame"].extents]
    jobs: dict[str, str] = {}
    for z in zt["zones"]:
        if z["kind"] != "lattice":
            continue
        req = zone_request(zt, z, meta["material"], extents)
        jobs[z["id"]] = submit_design(req, {"implant_id": implant_id, "zone_id": z["id"]})["job_id"]
    write_json(d / "jobs.json", jobs)
    return jobs


def zone_candidates(implant_id: str, zone_id: str) -> dict[str, Any]:
    from server.store import get_job
    d = idir(implant_id)
    zt = read_json(d / "zones.json") or {"zones": []}
    zone = next((z for z in zt["zones"] if z["id"] == zone_id), None)
    if zone is None:
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found")
    base = {"zone_id": zone_id, "kind": zone["kind"], "reason": zone.get("reason"), "candidates": [], "grid": None, "job": None}
    if zone["kind"] != "lattice":
        return base
    prep = prepare(implant_id)
    a, b = zone["range_mm"]
    pitch = zt["cell_mm"]
    import math
    from core import tiling
    c0, c1 = math.ceil(a / pitch - 1e-6) * pitch, math.floor(b / pitch + 1e-6) * pitch
    grid = tiling.cells_for_range(prep["frame"], c0, c1, pitch) if c1 > c0 else None
    base["grid"] = {"cell_mm": pitch, "cells": [grid.nx, grid.ny, int(round((c1 - c0) / pitch))] if grid else [0, 0, 0],
                    "whole_cells": len(grid.cells) if grid else 0}
    job_id = read_json(d / "jobs.json", {}).get(zone_id)
    if job_id:
        job = get_job(job_id)
        if job:
            base["job"] = {"job_id": job_id, "status": job["status"], "stage": job.get("stage"), "progress": job.get("progress"),
                           "message": job.get("message"), "queue_position": job.get("queue_position")}
            base["candidates"] = job.get("candidates", [])
    return base


@router.post("/{implant_id}/search")
async def post_search(implant_id: str) -> dict:
    from server.jobs import QueueFull
    idir(implant_id)
    try:
        return await _bg(search_zones, implant_id)
    except QueueFull as e:
        raise HTTPException(status_code=429, detail=str(e), headers={"Retry-After": "60"})


@router.get("/{implant_id}/zones/{zone_id}/candidates")
async def get_zone_candidates(implant_id: str, zone_id: str) -> dict:
    idir(implant_id)
    return sanitize(await _bg(zone_candidates, implant_id, zone_id))


# ------------------------------------------------------------------ assembly (one queued job)
def resolve_choices(implant_id: str, choices: dict[str, str]) -> dict[str, dict[str, Any]]:
    """zone id -> the chosen candidate (with its lattice), checked against the zone's own search results."""
    from server.store import get_job
    d = idir(implant_id)
    zt = read_json(d / "zones.json")
    if not zt or not zt.get("zones"):
        raise BadTarget("Confirm the implant first.", code="not_confirmed")
    jobs = read_json(d / "jobs.json", {})
    out: dict[str, dict[str, Any]] = {}
    for z in zt["zones"]:
        if z["kind"] == "undecided":
            raise BadTarget(f"{z['name']} is undecided: choose solid or lattice first.", code="undecided_zone", field="zones")
        if z["kind"] != "lattice":
            continue
        cid = choices.get(z["id"])
        if not cid:
            raise BadTarget(f"Choose a candidate for {z['name']}.", code="missing_choice", field="choices")
        job_id = jobs.get(z["id"])
        job = get_job(job_id) if job_id else None
        if job is None or job["status"] != "done":
            raise BadTarget(f"The search for {z['name']} has not finished.", code="search_not_done", field="choices")
        cand = next((c for c in job.get("candidates", []) if c["id"] == cid), None)
        if cand is None:
            raise BadTarget(f"{cid} is not a candidate of {z['name']}.", code="unknown_candidate", field="choices")
        out[z["id"]] = cand
    extra = set(choices) - {z["id"] for z in zt["zones"]}
    if extra:
        raise BadTarget(f"Unknown zone(s): {', '.join(sorted(extra))}.", code="unknown_zone", field="choices")
    return out


def build_assembly(implant_id: str, chosen: dict[str, dict[str, Any]], interface_mm: float | None, sides: int,
                   progress=None, should_stop=None):
    from core import assemble as asm
    d = idir(implant_id)
    zt = read_json(d / "zones.json")
    prep = prepare(implant_id)
    lattices = {zid: {**c["lattice"], "rel_density": c["rel_density"]} for zid, c in chosen.items()}
    return asm.assemble(prep["frame"], zt["zones"], zt["cell_mm"], lattices, interface_mm, sides, progress, should_stop)


def assembly_summary(a) -> dict[str, Any]:
    return {"length_mm": a.length_mm, "cell_mm": a.cell_mm, "interface_mm": a.interface_mm, "sides": a.sides,
            "triangles": a.triangles, "zones": a.zones, "warnings": a.warnings, "notes": a.notes,
            "parts": [{"name": p.name, "kind": p.kind, "zone_ids": p.zone_ids, "triangles": int(len(p.mesh.faces)),
                       "watertight": bool(p.mesh.is_watertight), "volume_mm3": float(abs(p.mesh.volume))} for p in a.parts],
            "verification": {"geometry": "geometry_only"}}


class AssembleTask:
    """Runs on the job worker thread: tile -> assemble (T16 adds check and export). Cancel and progress work as for searches."""

    def __init__(self, implant_id: str, chosen: dict[str, dict[str, Any]], interface_mm: float | None, sides: int) -> None:
        self.implant_id, self.chosen, self.interface_mm, self.sides = implant_id, chosen, interface_mm, sides

    def run(self, job_id: str, should_stop) -> None:
        from core.assemble import AssemblyFailed
        from server.store import update_job_status

        def progress(stage: str, frac: float, msg: str) -> None:
            update_job_status(job_id, status="running", stage=stage, progress=frac, message=msg)
        try:
            a = build_assembly(self.implant_id, self.chosen, self.interface_mm, self.sides, progress, should_stop)
            summary = assembly_summary(a)
            out = idir(self.implant_id) / "assemblies" / job_id
            write_json(out / "assembly.json", sanitize(summary))
            from server.store import save_results
            save_results(job_id, [])                       # marks the job as reusable for find_by_cache_key
            update_job_status(job_id, status="done", stage="assemble", progress=1.0, message="Assembly finished",
                              meta=sanitize({"summary": summary}))
        except InterruptedError:
            update_job_status(job_id, status="cancelled", message="Cancelled.")
        except (AssemblyFailed, ValueError) as e:
            update_job_status(job_id, status="failed", message=str(e))


def submit_assemble(implant_id: str, body: dict[str, Any]) -> dict[str, str]:
    import hashlib
    from server.jobs import runner
    from server.store import create_job, find_by_cache_key, update_job_status
    chosen = resolve_choices(implant_id, body["choices"])
    d = idir(implant_id)
    key_src = json.dumps({"implant": implant_id, "zones": read_json(d / "zones.json"), "confirm": read_json(d / "implant.json")["confirm"],
                          "choices": {z: c["id"] for z, c in sorted(chosen.items())}, "interface": body.get("interface_mm"),
                          "sides": body.get("sides", 8)}, sort_keys=True, default=str)
    key = "asm_" + hashlib.sha256(key_src.encode()).hexdigest()[:24]
    same = find_by_cache_key(key)
    if same is not None:
        return same
    job_id = f"a_{uuid.uuid4().hex[:8]}"
    create_job(job_id=job_id, status="queued", message="Assembly queued",
               meta=sanitize({"cache_key": key, "kind": "assemble", "implant_id": implant_id}))
    try:
        runner.submit(job_id, AssembleTask(implant_id, chosen, body.get("interface_mm"), body.get("sides", 8)))
    except Exception as e:
        update_job_status(job_id, status="failed", message=str(e))
        raise
    return {"job_id": job_id, "status": "queued"}


@router.post("/{implant_id}/assemble", status_code=202)
async def post_assemble(implant_id: str, payload: AssembleRequest) -> dict:
    from server.jobs import QueueFull
    idir(implant_id)
    try:
        return await _bg(submit_assemble, implant_id, payload.model_dump())
    except QueueFull as e:
        raise HTTPException(status_code=429, detail=str(e), headers={"Retry-After": "60"})
