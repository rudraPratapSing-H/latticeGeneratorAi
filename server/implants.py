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
