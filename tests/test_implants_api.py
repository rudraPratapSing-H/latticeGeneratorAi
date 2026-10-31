"""T13: upload, confirm, zone table with sourced requirements, picker snapping, solid reasons, edits, error rows."""
import io
import sys
from pathlib import Path

import pytest
import trimesh
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.make_test_stem import make_bar, make_stem  # noqa: E402
from server.app import app  # noqa: E402

DESCRIPTION = "Right femoral hip stem for a 75 kg active patient. Keep the neck solid. History of falls."


def stl(mesh) -> bytes:
    return mesh.export(file_type="stl")


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def upload(client, mesh, description=DESCRIPTION, material="ti64"):
    return client.post("/api/implants", files={"stl_file": ("part.stl", stl(mesh), "model/stl")},
                       data={"material": material, "description": description})


def confirmed(client, mesh=None, fields=None, **over):
    r = upload(client, mesh or make_stem())
    assert r.status_code == 201, r.text
    j = r.json()
    body = {"units": "mm", "axis": "auto", "flip": False, "fields": fields or j["fields"], **over}
    c = client.post(f"/api/implants/{j['implant_id']}/confirm", json=body)
    assert c.status_code == 200, c.text
    return j["implant_id"], c.json()


# ---- upload
def test_upload_returns_mesh_report_and_fields_from_the_description(client):
    r = upload(client, make_stem())
    j = r.json()
    assert r.status_code == 201 and j["implant_id"].startswith("i_")
    rep = j["mesh_report"]
    assert rep["watertight"] and rep["bodies"] == 1 and rep["guessed_units"] == "mm" and rep["units_confident"]
    assert rep["size_mm"][2] == pytest.approx(160.0, abs=0.5) and rep["volume_mm3"] > 90000
    f = j["fields"]
    assert f["implant_type"] == "hip stem" and f["body_weight_kg"] == 75 and f["activity"] == "active"
    assert any("neck" in r.lower() for r in f["special_rules"]) and any("fall" in r.lower() for r in f["special_rules"])
    assert set(f) == {"implant_type", "body_weight_kg", "activity", "special_rules", "force_n"}      # no stiffness or strength keys
    assert j["parsed_by"] == "offline" and "not a medical device" in j["disclaimer"]


@pytest.mark.parametrize("data,field", [(b"", "stl_file"), (b"not an stl" * 20, "stl_file")])
def test_bad_file_is_422_with_a_plain_message(client, data, field):
    r = client.post("/api/implants", files={"stl_file": ("x.stl", data, "model/stl")}, data={"material": "ti64", "description": ""})
    assert r.status_code == 422
    e = r.json()["error"]
    assert e["code"] == "bad_mesh" and "STL" in e["message"] and e["field"] == field


def test_open_mesh_that_cannot_be_repaired_is_refused_with_the_reason(client):
    m = make_stem()
    open_mesh = trimesh.Trimesh(m.vertices.copy(), m.faces[: len(m.faces) // 2].copy(), process=False)     # half the surface
    r = upload(client, open_mesh)
    assert r.status_code == 422 and "not closed" in r.json()["error"]["message"]


def test_unknown_material_and_wrong_units_are_reported(client):
    assert upload(client, make_stem(), material="unobtainium").json()["error"]["code"] == "unknown_material"
    small = make_stem()
    small.apply_scale(0.001)
    j = upload(client, small).json()
    assert j["mesh_report"]["guessed_units"] == "m" and j["mesh_report"]["units_confident"] is False
    assert any("units" in w.lower() for w in j["mesh_report"]["warnings"])


def test_two_pieces_use_the_largest_and_say_so(client):
    other = trimesh.creation.box(extents=(5, 5, 5))
    other.apply_translation([200, 0, 0])
    j = upload(client, trimesh.util.concatenate([make_stem(), other])).json()
    assert j["mesh_report"]["bodies"] == 2 and any("separate pieces" in w for w in j["mesh_report"]["warnings"])


def test_compact_body_asks_for_the_axis(client):
    j = upload(client, trimesh.creation.box(extents=(30, 28, 31))).json()
    assert j["mesh_report"]["axis_ambiguous"] is True and any("axis" in w for w in j["mesh_report"]["warnings"])


# ---- confirm and the zone table
def test_confirm_builds_the_zone_table_with_a_source_on_every_number(client):
    iid, t = confirmed(client)
    assert t["state"] == "confirmed" and 3 <= len(t["zones"]) <= 8 and t["cell_mm"] >= 4.4
    assert "not a medical device" in t["disclaimer"]
    prev_end = 0.0
    for z in t["zones"]:
        assert z["range_mm"][0] == pytest.approx(prev_end) and z["kind"] in ("lattice", "solid", "undecided") and z["reason"]
        prev_end = z["range_mm"][1]
        assert (z["range_mm"][1] / t["cell_mm"]) == pytest.approx(round(z["range_mm"][1] / t["cell_mm"])) or z is t["zones"][-1]
        for group in ("stiffness_gpa", "strength_mpa"):
            for ax in "xyz":
                assert z["requirement"][group][ax]["source"] in ("automatic", "requested")
        assert z["requirement"]["strength_mpa"]["z"]["value"] == pytest.approx(z["stress_mpa"])
        assert z["requirement"]["stiffness_gpa"]["x"]["value"] is None            # lateral axes: don't care
    assert prev_end == pytest.approx(t["length_mm"])


def test_every_assumption_in_the_load_case_names_its_source(client):
    _, t = confirmed(client)
    names = {a["name"]: a for a in t["load"]["assumptions"]}
    assert names["body weight"]["source"] == "description" and names["body weight"]["value"] == 75
    assert names["safety factor"]["todo"] is True and names["safety factor"]["source"] == "placeholder"
    cases = {c["name"] for c in t["load"]["cases"]}
    assert "stumble" in cases and "fall" in cases                                  # accident cases from the description and by default
    assert t["load"]["governing"]["name"] == "fall"


def test_high_stress_zones_are_solid_with_the_reason_and_the_description_rule_is_honoured(client):
    _, t = confirmed(client)
    solid = [z for z in t["zones"] if z["kind"] == "solid"]
    assert solid and all(z["reason"] for z in solid)
    assert any("above the most any lattice" in z["reason"] for z in solid)
    neck = [z for z in t["zones"] if z["name"] == "neck"]
    assert neck and all(z["kind"] == "solid" and "neck solid" in z["reason"] for z in neck)


def test_lattice_zones_carry_the_picker_result_and_a_snapped_target(client):
    _, t = confirmed(client, fields={"implant_type": "hip stem", "body_weight_kg": 45, "activity": "sedentary", "special_rules": []})
    lat = [z for z in t["zones"] if z["kind"] == "lattice"]
    assert lat, [ (z["name"], z["stress_mpa"], z["kind"]) for z in t["zones"]]
    for z in lat:
        r = z["reach"]
        assert r["level"] in ("covered", "extended", "outside") and r["density"] in (0.05, 0.15, 0.25)
        assert r["snapped"]["strength_mpa"]["z"] >= z["requirement"]["strength_mpa"]["z"]["value"] * 0.995 or r["level"] != "covered"
        assert r["snapped"]["lattice_id"] >= 0


def test_a_lighter_load_gives_fewer_solid_zones(client):
    heavy = confirmed(client, fields={"implant_type": "hip stem", "body_weight_kg": 110, "activity": "high", "special_rules": ["history of falls"]})[1]
    light = confirmed(client, fields={"implant_type": "hip stem", "body_weight_kg": 40, "activity": "sedentary", "special_rules": []})[1]
    n = lambda t: sum(z["kind"] == "lattice" for z in t["zones"])  # noqa: E731
    assert n(light) >= n(heavy)
    assert max(z["stress_mpa"] for z in heavy["zones"]) > max(z["stress_mpa"] for z in light["zones"])


def test_a_typed_force_replaces_the_load_model_and_is_labelled(client):
    _, t = confirmed(client, fields={"implant_type": "hip stem", "body_weight_kg": 70, "activity": "low", "special_rules": [], "force_n": 900})
    assert [c["name"] for c in t["load"]["cases"]] == ["typed force"]


def test_absurd_body_weight_is_refused_by_the_schema_and_missing_weight_uses_a_labelled_default(client):
    j = upload(client, make_stem()).json()
    bad = client.post(f"/api/implants/{j['implant_id']}/confirm", json={"units": "mm", "fields": {**j["fields"], "body_weight_kg": 900}})
    assert bad.status_code == 422
    iid, t = confirmed(client, fields={"implant_type": "hip stem", "body_weight_kg": None, "activity": "moderate", "special_rules": []})
    w = next(a for a in t["load"]["assumptions"] if a["name"] == "body weight")
    assert w["source"] == "default"


def test_zones_before_confirm_are_empty_and_unknown_ids_are_404(client):
    j = upload(client, make_stem()).json()
    z = client.get(f"/api/implants/{j['implant_id']}/zones").json()
    assert z["state"] == "uploaded" and z["zones"] == []
    assert client.get("/api/implants/i_nope/zones").status_code == 404
    assert client.post(f"/api/implants/{j['implant_id']}/zones/search").status_code in (404, 405)


def test_unknown_units_and_axis_choice_flow_through_confirm(client):
    j = upload(client, make_stem()).json()
    r = client.post(f"/api/implants/{j['implant_id']}/confirm", json={"units": "furlong", "fields": j["fields"]})
    assert r.status_code == 422
    r = client.post(f"/api/implants/{j['implant_id']}/confirm", json={"units": "mm", "axis": "x", "fields": j["fields"]})
    assert r.status_code in (200, 422)        # the stem is not long along x: the frame is built, or a plain refusal comes back


# ---- edits
def test_moved_boundaries_rezone_and_typed_targets_are_kept_as_requested(client):
    iid, t = confirmed(client, fields={"implant_type": "hip stem", "body_weight_kg": 45, "activity": "sedentary", "special_rules": []})
    length = t["length_mm"]
    edit = {"zones": [{"range_mm": [0, 60]}, {"range_mm": [60, 100], "stiffness_z": 8.0, "strength_z": 12.0}, {"range_mm": [100, length]}]}
    r = client.put(f"/api/implants/{iid}/zones", json=edit)
    assert r.status_code == 200, r.text
    z = r.json()["zones"]
    assert [x["range_mm"] for x in z][1] == [60.0, 100.0] and len(z) == 3
    assert z[1]["requirement"]["stiffness_gpa"]["z"] == {"value": 8.0, "source": "requested", "note": None}
    assert z[1]["requirement"]["strength_mpa"]["z"]["source"] == "requested"
    again = client.get(f"/api/implants/{iid}/zones").json()
    assert [x["range_mm"] for x in again["zones"]] == [x["range_mm"] for x in z]                 # saved
    forced = client.put(f"/api/implants/{iid}/zones", json={"zones": [{"range_mm": [0, 80], "kind": "solid"}, {"range_mm": [80, length], "kind": "solid"}]})
    assert [x["kind"] for x in forced.json()["zones"]] == ["solid", "solid"]
    assert all("Set to solid by you" in x["reason"] for x in forced.json()["zones"])


def test_zone_edits_that_leave_gaps_are_refused(client):
    iid, t = confirmed(client)
    r = client.put(f"/api/implants/{iid}/zones", json={"zones": [{"range_mm": [0, 40]}, {"range_mm": [60, t["length_mm"]]}]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "bad_zones"


def test_summary_endpoint(client):
    iid, t = confirmed(client)
    s = client.get(f"/api/implants/{iid}").json()
    assert s["state"] == "confirmed" and [z["id"] for z in s["zones"]] == [z["id"] for z in t["zones"]]


def test_a_thin_implant_turns_into_solid_zones_with_the_reason(client):
    thin = make_bar(120, 10, 8)
    iid, t = confirmed(client, mesh=thin, fields={"implant_type": "bone plate", "body_weight_kg": 30, "activity": "sedentary", "special_rules": []})
    assert all(z["kind"] == "solid" for z in t["zones"])
    assert any("Every zone is solid" in w for w in t["warnings"])
