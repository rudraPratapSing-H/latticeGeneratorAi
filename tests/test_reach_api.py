import pytest
from fastapi.testclient import TestClient

from server.app import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def body(**target):
    return {"material": "ti64", "target": target}


def test_limits_endpoint(client):
    r = client.get("/api/limits?material=ti64")
    assert r.status_code == 200
    j = r.json()
    assert [d["rel_density"] for d in j["densities"]] == [0.05, 0.15, 0.25]
    assert round(j["densities"][2]["strength_mpa"]["max"], 1) == 76.1
    assert client.get("/api/limits?material=zzz").status_code == 422


def test_reach_covered_extended_and_shape(client):
    lim = client.get("/api/limits").json()["densities"][1]
    st = lim["stiffness_gpa"]["median"]
    r = client.post("/api/reach", json={**body(stiffness_gpa={"x": st, "y": st, "z": st}, rel_density=0.15), "modes": {"weight": "about"}})
    assert r.status_code == 200
    j = r.json()
    assert set(j) >= {"level", "distance_pct", "density", "requested", "nearest", "bounds", "message"}
    assert j["density"] == 0.15 and j["bounds"]["stiffness_sum_max_gpa"] == pytest.approx(17.1)
    assert set(j["nearest"]) == {"stiffness_gpa", "strength_mpa", "lattice_id"}


def test_reach_infeasible_and_error_shape(client):
    r = client.post("/api/reach", json=body(strength_mpa={"x": 90, "y": None, "z": None}))
    assert r.status_code == 200 and r.json()["level"] == "infeasible"
    bad = client.post("/api/reach", json=body(stiffness_gpa={"x": 500, "y": None, "z": None}))
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "bad_target"
    assert "GPa" in bad.json()["error"]["message"] and bad.json()["error"]["field"] == "target.stiffness_gpa.x"
    assert client.post("/api/reach", json={"material": "ti64", "target": {}}).json()["error"]["code"] == "bad_target"
    assert client.post("/api/reach", json={"material": "nope", "target": {"stiffness_gpa": {"x": 1}}}).json()["error"]["code"] == "unknown_material"


def test_404_uses_error_shape(client):
    r = client.get("/api/jobs/j_nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
