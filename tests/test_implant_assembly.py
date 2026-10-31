"""T15: zone searches become ordinary jobs, the assemble job tiles whole cells and builds closed shells.

The solver is not run here: a finished search is seeded from the stored demo results (real candidates).
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import assemble, meshing, tiling  # noqa: E402
from scripts.make_test_stem import make_bar, make_stem  # noqa: E402
from server import implants  # noqa: E402
from server.app import app  # noqa: E402
from server.store import create_job, save_results, update_job_status  # noqa: E402
from tests.test_implants_api import confirmed  # noqa: E402

DEMO = Path(__file__).resolve().parent.parent / "demo" / "jobs"


def demo_candidates():
    f = sorted(DEMO.glob("*/results.json"))[0]
    return json.loads(f.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def seed_searches(implant_id: str):
    """Pretend every lattice zone's search finished with the demo candidates (ids prefixed per zone)."""
    d = implants.idir(implant_id)
    zt = implants.read_json(d / "zones.json")
    jobs, cands = {}, demo_candidates()
    for z in zt["zones"]:
        if z["kind"] != "lattice":
            continue
        jid = f"j_{implant_id[-6:]}_{z['id']}"
        mine = [{**c, "id": f"{jid}_{n}"} for n, c in enumerate(cands)]
        create_job(jid, status="done", stage="rank", progress=1.0, message="done", meta={"kind": "design", "implant_id": implant_id, "zone_id": z["id"]})
        save_results(jid, mine)
        jobs[z["id"]] = jid
    implants.write_json(d / "jobs.json", jobs)
    return jobs


def light_case(client):
    """A 45 kg sedentary stem: low stress, so several zones are lattice."""
    fields = {"implant_type": "hip stem", "body_weight_kg": 45, "activity": "sedentary", "special_rules": []}
    return confirmed(client, make_stem(), fields=fields)


def wait(client, job_id, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.2)
    raise AssertionError("assemble job did not finish")


# ---- core: tiling and shells
def lattice():
    return demo_candidates()[0]["lattice"]


def test_unit_cell_is_a_full_cell_and_tiling_merges_shared_faces():
    ua, ub = tiling.unit_cell_struts(lattice())
    assert len(ua) > 20 and np.abs(np.vstack([ua, ub])).max() <= 1 + 1e-9
    bar = make_bar(length=60, width=20, depth=20)
    grid = tiling.cells_for_range(bar, 0, 30, 10.0)
    assert len(grid.cells) == 2 * 2 * 3
    a, b, r = tiling.tile(lattice(), grid, 10.0)
    single, _, _ = tiling.tile(lattice(), tiling.Grid(10.0, grid.x0, grid.y0, 1, 1, [(0, 0, 0)]), 10.0)
    assert len(a) < 12 * len(single)                        # struts on shared faces are one strut, not two


def test_assembled_bar_is_lattice_solid_lattice_with_watertight_shells():
    bar = make_bar(length=60, width=20, depth=20)
    zones = [{"id": "z1", "name": "A", "range_mm": [0, 20], "kind": "lattice"}, {"id": "z2", "name": "B", "range_mm": [20, 40], "kind": "solid"},
             {"id": "z3", "name": "C", "range_mm": [40, 60], "kind": "lattice"}]
    lat = {**lattice(), "rel_density": 0.15}
    a = assemble.assemble(bar, zones, 10.0, {"z1": lat, "z3": lat})
    kinds = [p.kind for p in a.parts]
    assert kinds.count("lattice") == 2 and kinds.count("solid") == 1 and kinds.count("interface") == 2
    assert all(p.mesh.is_watertight for p in a.parts)
    assert all(np.isfinite(p.mesh.vertices).all() for p in a.parts)
    assert {s["zone_id"]: s["kind"] for s in a.zones} == {"z1": "lattice", "z2": "solid", "z3": "lattice"}


def test_zone_too_short_for_a_cell_becomes_solid_with_a_warning():
    bar = make_bar(length=60, width=20, depth=20)
    zones = [{"id": "z1", "name": "A", "range_mm": [0, 30], "kind": "solid"}, {"id": "z2", "name": "B", "range_mm": [30, 36], "kind": "lattice"},
             {"id": "z3", "name": "C", "range_mm": [36, 60], "kind": "solid"}]
    a = assemble.assemble(bar, zones, 10.0, {"z2": lattice()})
    assert not [p for p in a.parts if p.kind == "lattice"]
    assert any("No whole" in w for w in a.warnings)


def test_undecided_zone_is_refused():
    bar = make_bar(length=60, width=20, depth=20)
    with pytest.raises(ValueError, match="undecided"):
        assemble.assemble(bar, [{"id": "z1", "name": "A", "range_mm": [0, 60], "kind": "undecided"}], 10.0, {})


def test_cancel_stops_assembly():
    bar = make_bar(length=60, width=20, depth=20)
    zones = [{"id": "z1", "name": "A", "range_mm": [0, 60], "kind": "lattice"}]
    with pytest.raises(InterruptedError):
        assemble.assemble(bar, zones, 10.0, {"z1": lattice()}, should_stop=lambda: True)


def test_triangle_budget_is_enforced():
    bar = make_bar(length=60, width=20, depth=20)
    zones = [{"id": "z1", "name": "A", "range_mm": [0, 60], "kind": "lattice"}]
    with pytest.raises(assemble.AssemblyFailed, match="triangles"):
        assemble.assemble(bar, zones, 10.0, {"z1": lattice()}, max_triangles=1000)


def test_disconnected_lattice_fails_instead_of_exporting_a_broken_part():
    broken = {**lattice(), "edges": [[0, 1]] * 1}               # a single strut: nothing connected to speak of
    bar = make_bar(length=60, width=20, depth=20)
    zones = [{"id": "z1", "name": "A", "range_mm": [0, 60], "kind": "lattice"}]
    try:
        a = assemble.assemble(bar, zones, 10.0, {"z1": broken})
    except assemble.AssemblyFailed:
        return
    assert a.zones[0]["main_share"] >= 0.9


# ---- API
def test_search_requires_confirmation_and_decided_zones(client):
    r = client.post("/api/implants", files={"stl_file": ("s.stl", make_stem().export(file_type="stl"), "model/stl")}, data={"material": "ti64", "description": ""})
    iid = r.json()["implant_id"]
    s = client.post(f"/api/implants/{iid}/search")
    assert s.status_code == 422 and s.json()["error"]["code"] == "not_confirmed"


def test_search_queues_one_job_per_lattice_zone_with_snapped_targets(client):
    iid, zt = light_case(client)
    lattice_zones = [z for z in zt["zones"] if z["kind"] == "lattice"]
    if not lattice_zones:
        pytest.skip("this load produces no lattice zone")
    jobs = implants.search_zones(iid)
    assert set(jobs) == {z["id"] for z in lattice_zones}
    for zid, jid in jobs.items():
        j = client.get(f"/api/jobs/{jid}").json()
        assert j["kind"] == "design" and j["implant_id"] == iid and j["zone_id"] == zid
        req = j["request"]
        assert req["part"]["cell_mm"] == zt["cell_mm"] and req["target"]["rel_density"] in (0.05, 0.15, 0.25)
        assert "stiffness_gpa" in req["target"] or "strength_mpa" in req["target"]
        assert all(v is None for k, v in (req["target"].get("stiffness_gpa") or {}).items() if k != "z")          # targets along z only
        client.post(f"/api/jobs/{jid}/cancel")
    c = client.get(f"/api/implants/{iid}/zones/{lattice_zones[0]['id']}/candidates").json()
    assert c["zone_id"] == lattice_zones[0]["id"] and c["grid"]["whole_cells"] > 0 and c["job"]["job_id"] == jobs[lattice_zones[0]["id"]]


def test_candidates_of_a_solid_zone_are_empty_with_the_reason(client):
    iid, zt = confirmed(client, make_stem())
    solid = next((z for z in zt["zones"] if z["kind"] == "solid"), None)
    assert solid is not None
    c = client.get(f"/api/implants/{iid}/zones/{solid['id']}/candidates").json()
    assert c["candidates"] == [] and c["kind"] == "solid" and c["reason"]
    assert client.get(f"/api/implants/{iid}/zones/nope/candidates").status_code == 404


def test_assemble_validates_choices(client):
    iid, zt = light_case(client)
    lz = [z for z in zt["zones"] if z["kind"] == "lattice"]
    if not lz:
        pytest.skip("no lattice zone")
    r = client.post(f"/api/implants/{iid}/assemble", json={"choices": {}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "missing_choice"
    jobs = seed_searches(iid)
    r = client.post(f"/api/implants/{iid}/assemble", json={"choices": {z["id"]: "j_nope_1" for z in lz}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_candidate"
    r = client.post(f"/api/implants/{iid}/assemble", json={"choices": {z["id"]: f"{jobs[z['id']]}_0" for z in lz}, "interface_mm": 99})
    assert r.status_code == 422


def test_assemble_job_runs_reports_progress_and_is_cached(client):
    iid, zt = light_case(client)
    lz = [z for z in zt["zones"] if z["kind"] == "lattice"]
    if not lz:
        pytest.skip("no lattice zone")
    jobs = seed_searches(iid)
    body = {"choices": {z["id"]: f"{jobs[z['id']]}_0" for z in lz}}
    r = client.post(f"/api/implants/{iid}/assemble", json=body)
    assert r.status_code == 202, r.text
    job = wait(client, r.json()["job_id"])
    assert job["status"] == "done", job
    assert job["kind"] == "assemble" and job["implant_id"] == iid
    s = job["summary"]
    assert s["triangles"] > 0 and all(p["watertight"] for p in s["parts"]) and s["verification"]["geometry"] == "geometry_only"
    again = client.post(f"/api/implants/{iid}/assemble", json=body).json()
    assert again["job_id"] == r.json()["job_id"]                  # same choices -> the finished job is reused


def test_assemble_failure_is_a_failed_job_with_a_message(client, monkeypatch):
    iid, zt = light_case(client)
    lz = [z for z in zt["zones"] if z["kind"] == "lattice"]
    if not lz:
        pytest.skip("no lattice zone")
    jobs = seed_searches(iid)

    def boom(*a, **k):
        raise assemble.AssemblyFailed("The lattice fell apart (test).")
    monkeypatch.setattr(implants, "build_assembly", boom)
    r = client.post(f"/api/implants/{iid}/assemble", json={"choices": {z["id"]: f"{jobs[z['id']]}_0" for z in lz}, "sides": 12})
    job = wait(client, r.json()["job_id"])
    assert job["status"] == "failed" and "fell apart" in job["message"]
