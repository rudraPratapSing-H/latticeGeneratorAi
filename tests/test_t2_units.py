"""T2: round trips, titanium ratio 129.5, and request validation (invariant 3, bug watchlist 3 and 4)."""
import pytest
from pydantic import ValidationError

from server import units
from server.schemas import DesignRequest

TI = units.MATERIALS["ti64"]


def body(**target):
    return {"material": "ti64", "part": {"size_mm": [40, 40, 40], "cell_mm": 10}, "target": target}


def test_titanium_ratio_is_129_5():
    assert units.strength_ratio(TI) == pytest.approx(129.5454, abs=1e-3)
    assert round(units.strength_ratio(TI), 1) == 129.5


def test_effective_strength_uses_buckling_relative_to_E_not_yield():
    # buckling 0.002 (x E_s) -> 0.259 in sigma_y units; yield 0.1 governs
    assert units.effective_strength(0.1, 0.002, TI) == pytest.approx(0.1)
    # buckling 0.0005 -> 0.0648 < yield 0.1 -> buckling governs. Dividing by yield instead would give 0.0000007
    assert units.effective_strength(0.1, 0.0005, TI) == pytest.approx(0.0005 * 129.5454, rel=1e-4)


@pytest.mark.parametrize("gpa", [0.005, 0.465, 2.0, 13.15, 114.0])
def test_stiffness_round_trip(gpa):
    n = units.normalize_stiffness(gpa, TI["E_gpa"])
    assert units.denormalize_stiffness(n, TI["E_gpa"]) == pytest.approx(gpa, rel=1e-12)


@pytest.mark.parametrize("mpa", [0.08, 2.22, 76.1, 880.0])
def test_strength_round_trip(mpa):
    n = units.normalize_strength(mpa, TI["yield_mpa"])
    assert units.denormalize_strength(n, TI["yield_mpa"]) == pytest.approx(mpa, rel=1e-12)


@pytest.mark.parametrize("mass", [5.0, 14.2, 60.0, 283.5])
def test_mass_round_trip(mass):
    vol = units.calculate_volume_cm3([40, 40, 40])
    rho = units.mass_to_relative_density(mass, vol, TI["density_g_cm3"])
    assert units.relative_density_to_mass(rho, vol, TI["density_g_cm3"]) == pytest.approx(mass, rel=1e-12)
    assert units.mass_to_relative_density(283.52, vol, TI["density_g_cm3"]) == pytest.approx(1.0, abs=1e-3)


def test_valid_request_passes():
    DesignRequest(**body(stiffness_gpa={"x": 1, "y": None, "z": None}, strength_mpa={"x": 5, "y": 5, "z": None},
                         max_mass_g=30))


def test_rejects_strength_with_yield_strength():
    with pytest.raises(ValidationError, match="not both"):
        DesignRequest(**body(strength_mpa={"x": 5, "y": None, "z": None},
                             yield_strength_mpa={"x": 5, "y": None, "z": None}))


def test_rejects_mass_with_density():
    with pytest.raises(ValidationError, match="not both"):
        DesignRequest(**body(stiffness_gpa={"x": 1, "y": 1, "z": 1}, max_mass_g=30, rel_density=0.15))


@pytest.mark.parametrize("target", [
    {}, {"stiffness_gpa": None}, {"stiffness_gpa": {"x": None, "y": None, "z": None}},
    {"strength_mpa": {"x": None, "y": None, "z": None}, "max_mass_g": 30},
])
def test_rejects_all_null_targets(target):
    with pytest.raises(ValidationError, match="at least one"):
        DesignRequest(**body(**target))


def test_yield_only_spec_has_no_effective_strength_target():
    req = DesignRequest(**body(yield_strength_mpa={"x": 9, "y": 9, "z": 9}, rel_density=0.15))
    spec = units.to_search_spec(req, TI)
    assert spec["strength_mpa"] is None and spec["yield_strength_mpa"] == [9, 9, 9] and spec["rho_max"] == 0.15
