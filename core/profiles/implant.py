"""Implant demo defaults: bone stiffness by region, body-weight distribution and load cases.

EVERY NUMBER IN THIS FILE IS A PLACEHOLDER with ``source: "TODO"``. None is clinical data, none has a citation, and
nothing here is a safety, clinical or regulatory claim: this is a design demo, not a medical device. Replace the
numbers (and fill in ``source``) before anyone treats an output as more than an illustration.

What the load model does (all numbers below):
* The doctor's description gives body weight, activity and special rules (see core/profiles/describe.py).
* Body-weight distribution: in single-leg stance the joint carries the body weight minus the weight of the supporting
  leg itself (``leg_mass_fraction`` of body weight), multiplied by a joint factor per load case.
* Accident cases (stumble, fall) are always design cases, so the zone targets are sized for the accident load, not only
  for walking. The design load of a zone is the largest of its cases times the safety factor.
"""
from __future__ import annotations

from typing import Any

G = 9.81  # m/s^2


def P(value: Any, unit: str, note: str) -> dict[str, Any]:
    """A placeholder number that records where it came from (nowhere yet)."""
    return {"value": value, "unit": unit, "source": "TODO", "note": note}


# ---------------------------------------------------------------- bone stiffness by region (0 = distal tip, 1 = proximal end)
BONE_REGIONS: list[dict[str, Any]] = [
    {"name": "tip", "from": 0.00, "to": 0.25, "stiffness": P(12.0, "GPa", "placeholder: stiff diaphyseal bone")},
    {"name": "mid stem", "from": 0.25, "to": 0.55, "stiffness": P(10.0, "GPa", "placeholder")},
    {"name": "upper stem", "from": 0.55, "to": 0.80, "stiffness": P(6.0, "GPa", "placeholder: metaphyseal bone")},
    {"name": "neck", "from": 0.80, "to": 1.00, "stiffness": P(4.0, "GPa", "placeholder")},
]

# ---------------------------------------------------------------- body-weight distribution
BODY = {
    "default_weight_kg": P(70.0, "kg", "used only when the description gives no weight; the UI asks to confirm it"),
    "leg_mass_fraction": P(0.16, "-", "share of body weight carried by the supporting leg itself, subtracted in single-leg stance"),
    "weight_range_kg": {"min": 20.0, "max": 250.0},   # outside this the value is rejected as absurd (bug watchlist: absurd input)
}

# ---------------------------------------------------------------- load cases: joint force = factor x supported weight
LOAD_CASES: dict[str, dict[str, Any]] = {
    "walking": {"factor": P(3.0, "x supported weight", "placeholder"), "angle_deg": P(20.0, "deg", "load line tilt from the axis")},
    "stairs": {"factor": P(4.0, "x supported weight", "placeholder"), "angle_deg": P(22.0, "deg", "placeholder")},
    "stumble": {"factor": P(8.0, "x supported weight", "placeholder: accident case"), "angle_deg": P(25.0, "deg", "placeholder")},
    "fall": {"factor": P(12.0, "x supported weight", "placeholder: accident case"), "angle_deg": P(30.0, "deg", "placeholder")},
}

# which cases the activity level adds; accident cases are ALWAYS included
ALWAYS = ["stumble"]
ACTIVITY_CASES: dict[str, list[str]] = {
    "sedentary": ["walking"],
    "low": ["walking"],
    "moderate": ["walking", "stairs"],
    "active": ["walking", "stairs"],
    "high": ["walking", "stairs", "fall"],
}
RULE_CASES = {"fall": "fall"}      # a special rule mentioning falls adds the fall case

SAFETY_FACTOR = P(1.5, "-", "multiplies the peak stress of the governing case; placeholder")

# ---------------------------------------------------------------- geometry rules
GEOMETRY = {
    "slice_step_mm": P(2.0, "mm", "slice spacing (at most 200 slices)"),
    "zone_merge_ratio": P(1.5, "-", "neighbouring slices merge while peak stress and thickness stay within this factor"),
    "min_zones": 2,
    "max_zones": 8,
    "min_zone_cells": 3,
    "cells_across_thinnest": P(4, "cells", "upper limit of the cell size: thinnest lattice zone thickness / this"),
    "min_strut_mm": 0.4,
    "interface_mm": P(0.6, "mm", "thin solid plate between zones"),
    "stiffness_ratio_warn": P(3.0, "-", "warn when neighbouring zones differ in stiffness by more than this"),
}


def region_for(position: float) -> dict[str, Any]:
    """Bone region at relative position along the axis (0 distal .. 1 proximal)."""
    for r in BONE_REGIONS:
        if r["from"] <= position <= r["to"]:
            return r
    return BONE_REGIONS[-1] if position > 1 else BONE_REGIONS[0]


def load_cases_for(fields: dict[str, Any]) -> dict[str, Any]:
    """Load cases for one implant from the confirmed fields (body weight, activity, special rules).

    Returns the cases with their force in newtons, the governing one, the safety factor, and every assumption with its
    source ('description', 'default' or 'placeholder'), so the UI can show where each number came from.
    """
    w = fields.get("body_weight_kg")
    weight_source = "description"
    if w is None:
        w, weight_source = BODY["default_weight_kg"]["value"], "default"
    lo, hi = BODY["weight_range_kg"]["min"], BODY["weight_range_kg"]["max"]
    if not (lo <= float(w) <= hi):
        raise ValueError(f"body weight {w} kg is outside {lo:g} to {hi:g} kg")
    supported = float(w) * (1.0 - BODY["leg_mass_fraction"]["value"])
    activity = (fields.get("activity") or "moderate").lower()
    names = list(dict.fromkeys(ACTIVITY_CASES.get(activity, ACTIVITY_CASES["moderate"]) + ALWAYS))
    rules = " ".join(str(r).lower() for r in fields.get("special_rules") or [])
    for word, case in RULE_CASES.items():
        if word in rules and case not in names:
            names.append(case)
    if fields.get("force_n"):                                   # a force the user typed in replaces the model
        cases = [{"name": "typed force", "force_n": float(fields["force_n"]), "angle_deg": 20.0}]
    else:
        cases = [{"name": n, "force_n": LOAD_CASES[n]["factor"]["value"] * supported * G,
                  "angle_deg": LOAD_CASES[n]["angle_deg"]["value"]} for n in names]
    governing = max(cases, key=lambda c: c["force_n"])
    return {
        "cases": cases,
        "governing": governing,
        "safety_factor": SAFETY_FACTOR["value"],
        "supported_weight_kg": supported,
        "assumptions": [
            {"name": "body weight", "value": float(w), "unit": "kg", "source": weight_source},
            {"name": "weight carried by the supporting leg itself", "value": BODY["leg_mass_fraction"]["value"], "unit": "of body weight",
             "source": "placeholder", "todo": True},
            {"name": "activity", "value": activity, "unit": "", "source": "description" if fields.get("activity") else "default"},
            {"name": "design cases", "value": ", ".join(c["name"] for c in cases), "unit": "", "source": "placeholder", "todo": True},
            {"name": "safety factor", "value": SAFETY_FACTOR["value"], "unit": "", "source": "placeholder", "todo": True},
        ],
    }
