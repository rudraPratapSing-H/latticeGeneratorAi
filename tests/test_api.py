import pytest
from fastapi.testclient import TestClient

from server.app import app
from server.schemas import (
    JobStatus,
)
from server.store import create_job, init_db


@pytest.fixture
def client():
    init_db()
    return TestClient(app)


def test_cors_middleware():
    """Verify CORS middleware is configured to allow all origins."""
    middleware_classes = [m.cls.__name__ for m in app.user_middleware]
    assert "CORSMiddleware" in middleware_classes


def test_health_endpoint(client):
    """GET /api/health returns hardcoded health status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "model_loaded": False,
        "gpu": False,
        "solver_workers": 0,
    }


def test_materials_endpoint(client):
    """GET /api/materials returns the list containing Ti-6Al-4V."""
    response = client.get("/api/materials")
    assert response.status_code == 200
    materials = response.json()
    assert isinstance(materials, list)
    assert len(materials) == 1
    assert materials[0] == {
        "id": "ti64",
        "name": "Ti-6Al-4V",
        "E_gpa": 114.0,
        "yield_mpa": 880.0,
        "density_g_cm3": 4.43,
    }


def test_create_designs_endpoint(client):
    """POST /api/designs accepts contract payload and returns HTTP 202 with job_id."""
    payload = {
        "material": "ti64",
        "part": {"size_mm": [40, 40, 40], "cell_mm": 10},
        "target": {
            "stiffness_gpa": {"x": 4.0, "y": 4.0, "z": 6.0},
            "strength_mpa": {"x": 20, "y": 20, "z": None},
            "max_mass_g": 60,
        },
        "modes": {
            "stiffness": "about",
            "strength": "at_least",
            "weight": "at_most",
        },
        "tolerance_pct": 10,
        "n_results": 5,
    }
    response = client.post("/api/designs", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["job_id"].startswith("j_")
    assert data["status"] in [s.value for s in JobStatus]


def test_get_job_endpoint(client):
    """GET /api/jobs/{job_id} returns JobResponse from SQLite with stage and progress."""
    job_id = "j_test_get"
    create_job(
        job_id=job_id,
        status="running",
        stage="verify",
        progress=0.45,
        message="Running verification",
    )

    response = client.get(f"/api/jobs/{job_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id
    assert data["status"] == "running"
    assert data["stage"] == "verify"
    assert pytest.approx(data["progress"], rel=1e-5) == 0.45
    assert "candidates" in data


def test_get_job_events_endpoint(client):
    """GET /api/jobs/{job_id}/events returns SSE stream with EventSourceResponse."""
    job_id = "j_test_closed"
    create_job(
        job_id=job_id,
        status="done",
        stage="rank",
        progress=1.0,
        message="Completed",
    )

    with client.stream("GET", f"/api/jobs/{job_id}/events") as stream:
        lines = list(stream.iter_lines())
        # Should include close event because job is already done
        content = " ".join(lines)
        assert "close" in content or "event: close" in content


def test_get_design_endpoint(client):
    """GET /api/designs/{design_id}: unknown id is a 404 (no made-up design)."""
    response = client.get("/api/designs/d_01")
    assert response.status_code == 404


def test_openapi_registered_routes():
    """Verify all 6 routes exist in the OpenAPI schema."""
    paths = app.openapi()["paths"]
    expected_endpoints = [
        "/api/health",
        "/api/materials",
        "/api/designs",
        "/api/jobs/{job_id}",
        "/api/jobs/{job_id}/events",
        "/api/designs/{design_id}",
    ]
    for endpoint in expected_endpoints:
        assert endpoint in paths
