import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from server.jobs import (
    drop_geometric_duplicates,
    hash_lattice_edges,
    run_pipeline,
    build_spec,
    is_infeasible,
    MATERIALS_DB,
    rank_candidates,
)
from server.schemas import (
    AxisValues,
    DesignModes,
    DesignRequest,
    DesignTarget,
    PartSpec,
)
from server.store import get_job, get_job_results, init_db


def test_edge_hashing_and_deduplication():
    """Verify hashing handles undirected reversed edges and drops geometric duplicates."""
    e1 = [[0, 1], [1, 2], [2, 0]]
    e2 = [[1, 0], [2, 1], [0, 2]]  # identical geometry, different order
    e3 = [[0, 1], [1, 3], [3, 0]]  # distinct geometry

    assert hash_lattice_edges(e1) == hash_lattice_edges(e2)
    assert hash_lattice_edges(e1) != hash_lattice_edges(e3)

    candidates = [
        {"id": "c1", "lattice": {"edges": e1}},
        {"id": "c2", "lattice": {"edges": e2}},  # duplicate
        {"id": "c3", "lattice": {"edges": e3}},
    ]
    unique = drop_geometric_duplicates(candidates)
    assert len(unique) == 2
    assert [c["id"] for c in unique] == ["c1", "c3"]


def _req(**target):
    return DesignRequest(material="ti64", part=PartSpec(size_mm=[40.0, 40.0, 40.0], cell_mm=10.0),
                         target=DesignTarget(**target), modes=DesignModes())


def test_build_spec_converts_units():
    spec = build_spec(_req(stiffness_gpa=AxisValues(x=8.0, y=8.0, z=12.0),
                           strength_mpa=AxisValues(x=90.0, y=None, z=None), max_mass_g=60.0), MATERIALS_DB["ti64"])
    assert spec["stiffness_gpa"] == [8.0, 8.0, 12.0]
    assert spec["strength_mpa"] == [90.0, None, None]
    # 60 g / (64 cm3 x 4.43 g/cm3), weight mode at_most -> upper bound, free density
    assert spec["rho"] is None and abs(spec["rho_max"] - 60.0 / (64 * 4.43)) < 1e-9
    assert abs(spec["tol"] - 0.10) < 1e-9


def test_build_spec_yield_only_and_fixed_density():
    spec = build_spec(_req(yield_strength_mpa=AxisValues(x=100.0, y=100.0, z=100.0), rel_density=0.15),
                      MATERIALS_DB["ti64"])
    assert spec["strength_mpa"] is None and spec["yield_strength_mpa"] == [100.0, 100.0, 100.0]
    assert spec["rho_max"] == 0.15


def test_infeasible_stiffness_sum():
    spec = build_spec(_req(stiffness_gpa=AxisValues(x=60.0, y=60.0, z=60.0), rel_density=0.15), MATERIALS_DB["ti64"])
    assert is_infeasible(spec)


def test_rank_prefers_matches():
    c = lambda i, err, m: {"id": i, "match_error_pct": err, "matches_targets": m, "rel_density": 0.1}
    top = rank_candidates([c("a", 2.0, False), c("b", 9.0, True), c("c", 1.0, True)], 2)
    assert [t["id"] for t in top] == ["c", "b"] and [t["rank"] for t in top] == [1, 2]


@pytest.mark.asyncio
async def test_mock_replays_stored_run_that_matched_in_round_one():
    """Targets near sample_3 (matched in round 1): one round, matches_targets true, real numbers."""
    job_id = "j_replay_match"
    init_db()
    request = DesignRequest(material="ti64", part=PartSpec(size_mm=[40.0, 40.0, 40.0], cell_mm=10.0),
                            target=DesignTarget(stiffness_gpa=AxisValues(x=0.465, y=0.496, z=0.402),
                                                strength_mpa=AxisValues(x=2.22, y=2.65, z=2.19), rel_density=0.05),
                            modes=DesignModes(weight="about"))
    with ThreadPoolExecutor(max_workers=1) as pool:
        await run_pipeline(job_id=job_id, request=request, thread_pool=pool)
    job = get_job(job_id)
    assert job["status"] == "done" and len(job["rounds"]) == 1 and job["rounds"][0]["matched"]
    cands = get_job_results(job_id)
    assert len(cands) == 5 and cands[0]["matches_targets"] and cands[0]["mass_g"] > 0


@pytest.mark.asyncio
async def test_mock_replays_stored_run_that_needed_all_rounds_and_missed():
    """Targets near sample_7 (K=1000, no match): the rounds are reported and candidates say 'not a match'."""
    job_id = "j_replay_miss"
    init_db()
    request = DesignRequest(material="ti64", part=PartSpec(size_mm=[40.0, 40.0, 40.0], cell_mm=10.0),
                            target=DesignTarget(stiffness_gpa=AxisValues(x=1.45, y=3.32, z=3.35),
                                                strength_mpa=AxisValues(x=11.6, y=23.8, z=19.8), rel_density=0.25),
                            modes=DesignModes(weight="about"))
    with ThreadPoolExecutor(max_workers=1) as pool:
        await run_pipeline(job_id=job_id, request=request, thread_pool=pool)
    job = get_job(job_id)
    assert job["status"] == "done" and job["rounds"][-1]["k"] == 1000 and not job["rounds"][-1]["matched"]
    cands = get_job_results(job_id)
    assert cands and not cands[0]["matches_targets"] and any("not a match" in w for w in cands[0]["warnings"])
