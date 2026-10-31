"""T12: test stem and zoning: section properties, stress against a hand calculation, zone counts, bad-input rows."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh
from shapely.geometry import Polygon

from core import zoning
from core.profiles import implant as profile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.make_test_stem import make_bar, make_stem  # noqa: E402


def frame_of(mesh, units="mm", flip=False):
    return zoning.to_implant_frame(mesh, units, zoning.fit_axis(mesh)["axis"], flip)


# ---- section properties
def test_rectangle_section_properties_match_the_formulas():
    b, h = 12.0, 10.0
    p = zoning.section_properties(Polygon([(0, 0), (b, 0), (b, h), (0, h)]))
    assert p["area"] == pytest.approx(b * h)
    assert (p["cx"], p["cy"]) == pytest.approx((b / 2, h / 2))
    assert p["Sxx"] == pytest.approx(h * b ** 3 / 12) and p["Syy"] == pytest.approx(b * h ** 3 / 12)
    assert p["Sxy"] == pytest.approx(0.0, abs=1e-9)


def test_section_with_a_hole_subtracts_it_whatever_the_ring_direction():
    outer = Polygon([(0, 0), (20, 0), (20, 20), (0, 20)], [[(5, 5), (5, 15), (15, 15), (15, 5)]])      # clockwise hole
    p = zoning.section_properties(outer)
    assert p["area"] == pytest.approx(400 - 100)
    assert p["Sxx"] == pytest.approx((20 ** 4 - 10 ** 4) / 12)


def test_ellipse_section_close_to_the_exact_values():
    a, b = 13.0, 10.0
    t = np.linspace(0, 2 * np.pi, 400, endpoint=False)
    p = zoning.section_properties(Polygon(np.c_[a * np.cos(t), b * np.sin(t)]))
    assert p["area"] == pytest.approx(math.pi * a * b, rel=1e-3)
    assert p["Sxx"] == pytest.approx(math.pi * a ** 3 * b / 4, rel=1e-3)


# ---- stress against a hand calculation (straight rectangular bar)
@pytest.mark.parametrize("angle,force", [(15.0, 1000.0), (30.0, 2500.0), (0.0, 1500.0)])
def test_straight_bar_stress_matches_the_hand_calculation_within_2_percent(angle, force):
    width, depth, length = 12.0, 10.0, 80.0
    mesh, info = frame_of(make_bar(length, width, depth))
    slices = zoning.slice_stack(mesh, step_mm=4.0)
    rows = zoning.slice_stress(slices, force, angle, lateral=(-1.0, 0.0))
    top = slices[-1]
    A, Iy = width * depth, depth * width ** 3 / 12        # bending about the y axis, half width 6 mm
    th = math.radians(angle)
    for s, r in zip(slices, rows):
        eccentricity = (top.z - s.z) * math.tan(th)
        expected = force * math.cos(th) / A + force * math.cos(th) * eccentricity * (width / 2) / Iy
        assert r["peak_mpa"] == pytest.approx(expected, rel=0.02, abs=1e-6), (s.z, r, expected)


def test_governing_case_takes_the_largest_and_applies_the_safety_factor():
    mesh, _ = frame_of(make_bar(80, 12, 10))
    slices = zoning.slice_stack(mesh, step_mm=8.0)
    cases = [{"name": "walking", "force_n": 1000.0, "angle_deg": 10.0}, {"name": "stumble", "force_n": 3000.0, "angle_deg": 10.0}]
    rows, names = zoning.governing_stress(slices, cases, 1.5, lateral=(-1.0, 0.0))
    assert names == ["walking", "stumble"] and all(r["case"] == "stumble" for r in rows)
    single = zoning.slice_stress(slices, 3000.0, 10.0, lateral=(-1.0, 0.0))
    assert rows[0]["design_mpa"] == pytest.approx(1.5 * single[0]["peak_mpa"])


# ---- the generated stem
@pytest.fixture(scope="module")
def stem():
    mesh = make_stem()
    fr, info = frame_of(mesh)
    slices = zoning.slice_stack(fr)
    loads = profile.load_cases_for({"body_weight_kg": 75, "activity": "moderate", "special_rules": []})
    rows, _ = zoning.governing_stress(slices, loads["cases"], loads["safety_factor"])
    return mesh, fr, info, slices, rows


def test_test_stem_is_a_closed_outward_mesh(stem):
    mesh = stem[0]
    assert mesh.is_watertight and mesh.is_winding_consistent and mesh.volume > 0


def test_stem_frame_has_tip_at_zero_and_the_thicker_end_on_top(stem):
    _, fr, info, slices, _ = stem
    assert fr.bounds[0][2] == pytest.approx(0.0, abs=1e-6) and info["length_mm"] == pytest.approx(fr.extents[2])
    assert slices[0].area < slices[-1].area                    # tip thinner than the top


def test_stem_gives_3_to_5_zones_on_the_cell_grid(stem):
    _, fr, info, slices, rows = stem
    zones = zoning.make_zones(slices, rows, info["length_mm"])
    zoning.name_zones(zones, info["length_mm"])
    assert 2 <= len(zones) <= 8
    zoning.snap_to_grid(zones, 5.0)
    assert 3 <= len(zones) <= 5
    for z in zones:
        assert z["range_mm"][1] - z["range_mm"][0] >= 3 * 5.0 - 1e-6
    for a, b in zip(zones[:-1], zones[1:]):
        assert a["range_mm"][1] == pytest.approx(b["range_mm"][0])
        assert (a["range_mm"][1] / 5.0) == pytest.approx(round(a["range_mm"][1] / 5.0))     # on the grid
    assert zones[0]["range_mm"][0] == 0.0 and zones[-1]["range_mm"][1] == pytest.approx(info["length_mm"])


def test_slice_count_is_capped_at_200():
    mesh, _ = frame_of(make_bar(800, 12, 10))
    assert len(zoning.slice_stack(mesh, step_mm=1.0)) <= 200


def test_cell_range_follows_the_plan_rule():
    lo, hi = zoning.cell_range(20.0)
    assert hi == pytest.approx(5.0) and lo == pytest.approx(0.4 / (2 * 0.045))
    lo2, hi2 = zoning.cell_range(10.0)
    assert hi2 < lo2                                                   # thin zone: empty range, the zone becomes solid


# ---- failure rows: bad STL, units, axis, repair, bodies
def test_garbage_and_tiny_files_are_rejected_with_a_plain_message():
    for data in (b"", b"hello world", b"x" * 500):
        with pytest.raises(zoning.MeshProblem) as e:
            zoning.load_mesh(data)
        assert e.value.code == "bad_mesh" and "STL" in e.value.message


@pytest.mark.parametrize("scale,units,confident", [(1.0, "mm", True), (0.001, "m", False), (1 / 25.4, "inch", False)])
def test_units_are_guessed_from_the_longest_side(scale, units, confident):
    m = make_stem()
    m.apply_scale(scale)
    g = zoning.guess_units(m)
    assert g["units"] == units and g["confident"] is confident


def test_units_outside_every_plausible_range_are_not_guessed():
    m = make_stem()
    m.apply_scale(1e-6)
    assert zoning.guess_units(m)["units"] is None
    with pytest.raises(zoning.MeshProblem) as e:
        zoning.to_implant_frame(make_stem(), "furlong", None)
    assert e.value.code == "bad_units"


def test_a_compact_body_has_an_ambiguous_axis_and_a_stem_does_not():
    cube = trimesh.creation.box(extents=(30, 28, 31))
    assert zoning.fit_axis(cube)["ambiguous"] is True
    assert zoning.fit_axis(make_stem())["ambiguous"] is False


def test_flip_reverses_the_default_orientation():
    mesh = make_stem()
    a, _ = frame_of(mesh)
    b, info = frame_of(mesh, flip=True)
    assert info["flip"] is True
    sa, sb = zoning.slice_stack(a), zoning.slice_stack(b)
    assert sa[0].area < sa[-1].area
    assert sb[0].area > sb[-1].area


def test_inverted_normals_are_repaired_and_reported():
    m = make_stem()
    m.invert()
    fixed, notes = zoning.repair(m)
    assert fixed.is_watertight and fixed.volume > 0 and notes


def test_a_small_hole_is_closed_by_the_repair():
    m = make_stem()
    holed = trimesh.Trimesh(m.vertices.copy(), m.faces[:-1].copy(), process=False)      # drop one triangle
    assert not holed.is_watertight
    fixed, notes = zoning.repair(holed)
    assert fixed.is_watertight and any("hole" in n.lower() for n in notes)


def test_several_separate_bodies_are_found_largest_first():
    a = make_stem()
    b = trimesh.creation.box(extents=(5, 5, 5))
    b.apply_translation([200, 0, 0])
    parts = zoning.split_bodies(trimesh.util.concatenate([a, b]))
    assert len(parts) == 2 and parts[0].volume > parts[1].volume


def test_a_mesh_with_no_length_says_so():
    flat = trimesh.creation.box(extents=(40, 40, 0.001))
    with pytest.raises(zoning.MeshProblem) as e:
        zoning.slice_stack(flat)
    assert "units" in e.value.message


def test_a_slightly_bent_stem_keeps_the_coordinate_axis():
    ax = zoning.fit_axis(make_stem())
    assert ax["snapped_to_coordinate_axis"] is True and ax["axis"] == [0.0, 0.0, 1.0]


# ---- load cases from the description (placeholders, labelled)
def test_load_cases_follow_weight_activity_and_rules_and_always_include_an_accident_case():
    lc = profile.load_cases_for({"body_weight_kg": 80, "activity": "sedentary", "special_rules": []})
    names = [c["name"] for c in lc["cases"]]
    assert "stumble" in names and "walking" in names and "fall" not in names
    lc2 = profile.load_cases_for({"body_weight_kg": 80, "activity": "high", "special_rules": ["history of falls"]})
    assert "fall" in [c["name"] for c in lc2["cases"]] and lc2["governing"]["name"] == "fall"
    supported = 80 * (1 - profile.BODY["leg_mass_fraction"]["value"])
    stumble = next(c for c in lc["cases"] if c["name"] == "stumble")
    assert stumble["force_n"] == pytest.approx(8.0 * supported * 9.81)


def test_heavier_patients_get_larger_loads_and_absurd_weights_are_refused():
    a = profile.load_cases_for({"body_weight_kg": 60})["governing"]["force_n"]
    b = profile.load_cases_for({"body_weight_kg": 90})["governing"]["force_n"]
    assert b == pytest.approx(a * 1.5)
    for bad in (0.0, 5.0, 900.0):
        with pytest.raises(ValueError):
            profile.load_cases_for({"body_weight_kg": bad})


def test_missing_weight_uses_the_default_and_says_where_it_came_from():
    lc = profile.load_cases_for({})
    w = next(a for a in lc["assumptions"] if a["name"] == "body weight")
    assert w["source"] == "default"
    assert next(a for a in lc["assumptions"] if a["name"] == "safety factor")["todo"] is True


def test_every_placeholder_number_is_marked_todo():
    def walk(o):
        if isinstance(o, dict):
            if "value" in o and "unit" in o:
                yield o
            for v in o.values():
                yield from walk(v)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v)
    nums = list(walk([profile.BONE_REGIONS, profile.BODY, profile.LOAD_CASES, profile.SAFETY_FACTOR, profile.GEOMETRY]))
    assert len(nums) >= 15 and all(n["source"] == "TODO" for n in nums)
