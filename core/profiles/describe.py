"""The doctor's free-text description -> structured fields. The output has four keys and NO stiffness or strength numbers.

parse_offline() is deterministic and always available. T17 adds an optional Gemini call on top (server side); its answer is
cut down to the same four keys by clean_fields(), so a model can never smuggle a target into the result.
"""
from __future__ import annotations

import re
from typing import Any

IMPLANT_TYPES = {
    "hip stem": ("hip", "femoral", "femur", "stem"),
    "knee component": ("knee", "tibial", "tibia"),
    "spinal cage": ("spinal", "spine", "cage", "vertebr"),
    "bone plate": ("plate", "fixation"),
}
ACTIVITY_WORDS = [               # most specific first
    ("high", ("very active", "high impact", "high-impact", "athlete", "marathon", "heavy labour", "heavy labor", "sprint")),
    ("active", ("active", "athletic", "runner", "running", "sports", "hiker", "hiking")),
    ("sedentary", ("sedentary", "bedridden", "bed-ridden", "wheelchair", "inactive")),
    ("low", ("low activity", "elderly", "frail", "walks with", "limited mobility", "low-activity")),
    ("moderate", ("moderate", "average", "normal activity", "daily", "walking")),
]
RULE_WORDS = ("keep", "avoid", "must", "do not", "don't", "never", "fall", "osteopor", "solid", "fatigue", "allerg", "revision")
FIELD_KEYS = ("implant_type", "body_weight_kg", "activity", "special_rules")


def parse_offline(text: str) -> dict[str, Any]:
    """Keyword rules. Returns the fields plus `notes` (what was found or guessed)."""
    t = (text or "").strip()
    low = t.lower()
    notes: list[str] = []

    implant_type = "unspecified"
    for name, words in IMPLANT_TYPES.items():
        if any(w in low for w in words):
            implant_type = name
            break

    weight = None
    m = re.search(r"(\d{2,3}(?:[.,]\d+)?)\s*(kg|kilogram|kilograms|kilo|kilos|lb|lbs|pounds?)\b", low)
    if m:
        weight = float(m.group(1).replace(",", "."))
        if m.group(2).startswith(("lb", "pound")):
            weight = round(weight * 0.45359237, 1)
            notes.append("Converted the weight from pounds to kilograms.")
    else:
        notes.append("No body weight found in the description.")

    activity = None
    for level, words in ACTIVITY_WORDS:
        if any(w in low for w in words):
            activity = level
            break
    if activity is None:
        notes.append("No activity level found in the description.")

    rules: list[str] = []
    for sentence in re.split(r"(?<=[.;!?])\s+|\n", t):
        s = sentence.strip(" .;")
        if s and any(w in s.lower() for w in RULE_WORDS):
            rules.append(s)
    fields = {"implant_type": implant_type, "body_weight_kg": weight, "activity": activity, "special_rules": rules[:6]}
    return {**fields, "notes": notes, "parsed_by": "offline"}


def clean_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """Cut any dict (for example a model's answer) down to the four allowed keys with safe types. Stiffness or strength
    numbers have no key to live in, and special rules are text only."""
    w = raw.get("body_weight_kg")
    try:
        w = float(w) if w is not None else None
    except (TypeError, ValueError):
        w = None
    if w is not None and not (20.0 <= w <= 250.0):
        w = None
    activity = raw.get("activity")
    activity = activity.lower() if isinstance(activity, str) and activity.lower() in ("sedentary", "low", "moderate", "active", "high") else None
    rules = [str(r).strip()[:200] for r in (raw.get("special_rules") or []) if isinstance(r, (str, int, float)) and str(r).strip()]
    itype = raw.get("implant_type")
    return {"implant_type": itype.strip()[:60] if isinstance(itype, str) and itype.strip() else "unspecified",
            "body_weight_kg": w, "activity": activity, "special_rules": rules[:6]}
