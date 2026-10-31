"""T6: picker first, then the engine, then mass/printability warnings; cache; sanitize; no silent target changes."""
import copy
import json
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

import core
from core.mock import MockEngine, load_samples, with_predicted_governing
from server import units
from server.app import app
from server.finalize import finalize_candidates, mass_g, min_cell_mm, printability_warning, sanitize

MAT = units.MATERIALS["ti64"]
GOOD = {"material": "ti64", "part": {"size_mm": [40, 40, 40], "cell_mm": 10},
        "target": {"stiffness_gpa": {"x": 0.465, "y": 0.496, "z": 0.402},
                   "strength_mpa": {"x": 2.22, "y": 2.65, "z": 2.19}, "rel_density": 0.05},
        "modes": {"weight": "about"}}
_n = [0]


def fresh(**over):
    _n[0] += 1
    return {**copy.deepcopy(GOOD), "tolerance_pct": 10 + _n[0] * 0.0013, **over}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MOCK_STAGE_DELAY", "0")
    return TestClient(app)


def finish(client, jid, timeout=30):
    t = time.time()
    while time.time() - t < timeout:
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.05)
    raise AssertionError("job did not finish")


# ---- picker first
def test_infeasible_target_is_422_with_bound_and_nearest_unless_forced(client):
    body = fresh(target={"stiffness_gpa": {"x": 8, "y": 8, "z": 12}, "max_mass_g": 60}, modes={"weight": "at_most"})
    r = client.post("/api/designs", json=body)
    assert r.status_code == 422
    e = r.json()["error"]
    assert e["code"] == "bad_target" and "17.1" in e["message"] or "GPa in total" in e["message"]
    assert e["reach"]["level"] == "infeasible" and e["reach"]["nearest"]["stiffness_gpa"]
    forced = client.post("/api/designs", json={**body, "force": True})
    assert forced.status_code == 202
    j = finish(client, forced.json()["job_id"])
    assert j["reach"]["level"] == "infeasible" and any("closest" in w.lower() for w in j["warnings"])


def test_reach_level_and_warnings_are_stored_on_the_job_and_target_is_never_changed(client):
    body = fresh()
    jid = client.post("/api/designs", json=body).json()["job_id"]
    j = finish(client, jid)
    assert j["reach"]["level"] in ("covered", "extended", "outside") and "nearest" in j["reach"]
    assert j["request"]["target"]["stiffness_gpa"] == body["target"]["stiffness_gpa"]       # untouched
    assert j["request"]["target"]["strength_mpa"] == body["target"]["strength_mpa"]


def test_unknown_material_is_422_up_front(client):
    r = client.post("/api/designs", json=fresh(material="unobtainium"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_material"


def test_value_above_the_material_is_422_with_unit_hint(client):
    r = client.post("/api/designs", json=fresh(target={"stiffness_gpa": {"x": 900, "y": None, "z": None}}))
    assert r.status_code == 422 and "GPa" in r.json()["error"]["message"] and r.json()["error"]["field"].endswith("x")


def test_weight_limit_below_lightest_lattice_is_422_with_the_lightest_mass(client):
    r = client.post("/api/designs", json=fresh(target={"stiffness_gpa": {"x": 0.3, "y": None, "z": None}, "max_mass_g": 5}))
    lightest = 0.05 * 64 * 4.43
    assert r.status_code == 422 and f"{lightest:.1f}" in r.json()["error"]["message"]


def test_weight_limit_above_dense_end_uses_025_and_says_so(client):
    body = fresh(target={"stiffness_gpa": {"x": 2.0, "y": 2.0, "z": 2.0}, "max_mass_g": 250}, modes={"weight": "at_most"})
    j = finish(client, client.post("/api/designs", json=body).json()["job_id"])
    assert any("0.25" in w for w in j["warnings"])


def test_part_that_is_not_a_whole_number_of_cells_gets_a_warning(client):
    body = fresh(part={"size_mm": [45, 40, 40], "cell_mm": 10})
    j = finish(client, client.post("/api/designs", json=body).json()["job_id"])
    assert any("whole number" in w and "4 cells" in w and "5 cells" in w for w in j["warnings"])


# ---- cache
def test_identical_request_returns_the_stored_job(client):
    body = fresh()
    a = client.post("/api/designs", json=body).json()["job_id"]
    finish(client, a)
    r = client.post("/api/designs", json=json.loads(json.dumps(body)))        # same content
    assert r.status_code == 202 and r.json()["job_id"] == a and r.json()["status"] == "done"
    reordered = {k: body[k] for k in reversed(list(body))}                    # dictionary order must not matter
    assert client.post("/api/designs", json=reordered).json()["job_id"] == a
    b = client.post("/api/designs", json={**body, "n_results": 4}).json()["job_id"]
    assert b != a


def test_cache_clears_when_a_model_file_changes(client, monkeypatch):
    body = fresh()
    a = client.post("/api/designs", json=body).json()["job_id"]
    finish(client, a)
    monkeypatch.setattr(core, "_hash", "a-different-model-hash")
    b = client.post("/api/designs", json=body).json()["job_id"]
    assert b != a
    finish(client, b)


# ---- mass and printability
def test_mass_is_density_times_volume_times_material_density_never_zero():
    assert mass_g(0.05, [40, 40, 40], MAT) == pytest.approx(0.05 * 64 * 4.43, abs=1e-3)
    cand = with_predicted_governing(load_samples()[0]["candidates"][0])
    cand["mass_g"] = 0.0                                                       # whatever the engine said
    out = finalize_candidates([cand], "j_x", None, MAT, [40, 40, 40], 10)[0]
    assert out["mass_g"] == pytest.approx(cand["rel_density"] * 64 * 4.43, abs=1e-3) and out["mass_g"] > 0


def test_thin_struts_warn_with_the_smallest_passing_cell_size():
    lat = {"strut_radius_mm": 0.29672, "cell_size_mm": 10.0}
    assert printability_warning(lat) is None                                    # 0.59 mm struts print
    small = {"strut_radius_mm": 0.29672 / 2, "cell_size_mm": 5.0}               # 0.30 mm at a 5 mm cell
    w = printability_warning(small)
    assert w and "0.30 mm" in w and f"{min_cell_mm(0.29672 / 2, 5.0):.1f} mm" in w
    assert min_cell_mm(0.29672, 10.0) == pytest.approx(10 * 0.4 / 0.59344, rel=1e-3)


def test_cell_size_rescales_the_strut_radius():
    cand = with_predicted_governing(load_samples()[0]["candidates"][0])
    out = finalize_candidates([cand], "j_x", None, MAT, [40, 40, 40], 5.0)[0]
    assert out["lattice"]["cell_size_mm"] == 5.0
    assert out["lattice"]["strut_radius_mm"] == pytest.approx(cand["lattice"]["strut_radius_mm"] / 2)
    assert out["warnings"] and "mm" in out["warnings"][0]


# ---- sanitize
def test_sanitize_removes_nan_inf_and_numpy_types():
    dirty = {"a": float("nan"), "b": [np.float32(1.5), np.int64(3), float("inf")], "c": np.array([1.0, np.nan]),
             "d": np.bool_(True), "t": (1, 2)}
    clean = sanitize(dirty)
    json.dumps(clean, allow_nan=False)
    assert clean == {"a": None, "b": [1.5, 3, None], "c": [1.0, None], "d": True, "t": [1, 2]}
    assert type(clean["b"][0]) is float and type(clean["b"][1]) is int


class _DirtyEngine(MockEngine):
    def run(self, request, *a, **kw):
        res = super().run(request, *a, **kw)
        c = res["candidates"][0]
        c["verified"]["stiffness_gpa"]["x"] = float("nan")
        c["predicted"]["strength_mpa"]["y"] = np.float32("inf")
        c["match_error_pct"] = np.float64(3.25)
        return res


def test_api_responses_never_contain_nan_or_numpy(client, monkeypatch):
    monkeypatch.setattr(core, "_engine", _DirtyEngine())
    jid = client.post("/api/designs", json=fresh()).json()["job_id"]
    t = client.get(f"/api/jobs/{jid}")
    finish(client, jid)
    r = client.get(f"/api/jobs/{jid}")
    assert r.status_code == 200
    json.loads(r.text, parse_constant=lambda c: (_ for _ in ()).throw(AssertionError(f"{c} in response")))
    dirty = [c for c in r.json()["candidates"] if c["verified"]["stiffness_gpa"]["x"] is None]
    assert len(dirty) == 1                                                     # the NaN became null, not 500
    d = client.get(f"/api/designs/{dirty[0]['id']}")
    assert d.status_code == 200
    json.loads(d.text, parse_constant=lambda c: (_ for _ in ()).throw(AssertionError(c)))


class _EmptyEngine(MockEngine):
    def run(self, request, *a, **kw):
        res = super().run(request, *a, **kw)
        res["candidates"] = []
        return res


def test_no_candidates_fails_with_no_valid_design(client, monkeypatch):
    monkeypatch.setattr(core, "_engine", _EmptyEngine())
    j = finish(client, client.post("/api/designs", json=fresh()).json()["job_id"])
    assert j["status"] == "failed" and "no_valid_design" in j["message"]


def test_failed_jobs_are_not_served_from_the_cache(client, monkeypatch):
    monkeypatch.setattr(core, "_engine", _EmptyEngine())
    body = fresh()
    a = client.post("/api/designs", json=body).json()["job_id"]
    finish(client, a)
    monkeypatch.setattr(core, "_engine", MockEngine())
    b = client.post("/api/designs", json=body).json()["job_id"]
    assert b != a and finish(client, b)["status"] == "done"
