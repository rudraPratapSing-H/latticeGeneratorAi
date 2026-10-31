import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from server.app import process_pool, thread_pool
from server.jobs import (
    active_sse_queues,
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


def test_executors_initialization():
    """Verify ThreadPool and ProcessPool executors in app.py."""
    assert thread_pool._max_workers == 1
    expected_workers = int(os.environ.get("WORKERS", max(1, (os.cpu_count() or 2) - 1)))
    assert process_pool._max_workers == expected_workers


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
    c = lambda i, err, m: {"id": i, "match_error_pct": err, "matches_targets": m, "rel_density": 0.1,
                           "lattice": {"edges": [[0, ord(i)]]}}
    top = rank_candidates([c("a", 2.0, False), c("b", 9.0, True), c("c", 1.0, True)], 2)
    assert [t["id"] for t in top] == ["c", "b"] and [t["rank"] for t in top] == [1, 2]


@pytest.mark.asyncio
async def test_adaptive_escalation_break_early():
    """Verify early exit from k_values loop when tolerance is met at k=100."""
    init_db()
    job_id = "j_test_escalation_early"
    active_sse_queues[job_id] = asyncio.Queue()

    # Broad tolerance (50%) ensures k=100 satisfies target
    request = DesignRequest(
        material="ti64",
        part=PartSpec(size_mm=[40.0, 40.0, 40.0], cell_mm=10.0),
        target=DesignTarget(
            stiffness_gpa=AxisValues(x=8.0, y=8.0, z=12.0),
            strength_mpa=AxisValues(x=90.0, y=90.0, z=None),
            max_mass_g=60.0,
        ),
        modes=DesignModes(),
        tolerance_pct=50.0,
        n_results=3,
    )

    # Use ThreadPoolExecutor for test isolation to avoid multiprocessing spawn overhead in fast tests
    with ThreadPoolExecutor(max_workers=2) as test_p_pool, ThreadPoolExecutor(max_workers=1) as test_t_pool:
        await run_pipeline(
            job_id=job_id,
            request=request,
            process_pool=test_p_pool,
            thread_pool=test_t_pool,
            k_values=[100, 300, 1000],
        )

    # Check job completed
    job = get_job(job_id)
    assert job is not None
    assert job["status"] == "done"
    assert job["stage"] == "rank"

    # Verify results saved
    candidates = get_job_results(job_id)
    assert len(candidates) == 3

    # Collect SSE events
    events = []
    while not active_sse_queues[job_id].empty():
        events.append(await active_sse_queues[job_id].get())

    # Should not have escalated to 300 since k=100 met tolerance
    escalation_messages = [e.get("message", "") for e in events if "Escalating to" in e.get("message", "")]
    assert len(escalation_messages) == 0


@pytest.mark.asyncio
async def test_adaptive_escalation_escalates():
    """Verify escalation through k_values when tolerance is strict (0.01%) and not met."""
    init_db()
    job_id = "j_test_escalation_tight"
    active_sse_queues[job_id] = asyncio.Queue()

    # Very tight tolerance (0.001%) forces escalation through 100 -> 300
    request = DesignRequest(
        material="ti64",
        part=PartSpec(size_mm=[40.0, 40.0, 40.0], cell_mm=10.0),
        target=DesignTarget(
            stiffness_gpa=AxisValues(x=4.0, y=4.0, z=6.0),
            strength_mpa=AxisValues(x=90.0, y=90.0, z=None),
            max_mass_g=60.0,
        ),
        modes=DesignModes(),
        tolerance_pct=0.001,
        n_results=3,
    )

    with ThreadPoolExecutor(max_workers=2) as test_p_pool, ThreadPoolExecutor(max_workers=1) as test_t_pool:
        await run_pipeline(
            job_id=job_id,
            request=request,
            process_pool=test_p_pool,
            thread_pool=test_t_pool,
            k_values=[50, 100],  # test with 2 escalation levels
        )

    events = []
    while not active_sse_queues[job_id].empty():
        events.append(await active_sse_queues[job_id].get())

    # Check that escalation event was published
    esc_events = [e for e in events if "Escalating to 100" in e.get("message", "")]
    assert len(esc_events) >= 1
    assert esc_events[0]["stage"] == "search"
    assert esc_events[0]["progress"] > 0.0
