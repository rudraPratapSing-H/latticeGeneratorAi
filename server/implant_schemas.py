"""Pydantic models for the implant API (the contract the frontend types are generated from)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DISCLAIMER = ("Design demo, not a medical device. Bone and load numbers are placeholders (source: TODO); nothing here is a "
              "clinical, safety or regulatory claim.")


class MeshReport(BaseModel):
    watertight: bool
    bodies: int
    size_mm: list[float] = Field(..., description="extent along x, y, z of the chosen body, in the guessed units converted to mm")
    guessed_units: str | None = Field(default=None, description="mm, m or inch; null when the size fits none of them")
    units_confident: bool = False
    volume_mm3: float | None = None
    axis_ratio: float | None = Field(default=None, description="sqrt of the two largest PCA eigenvalues; under 1.5 the axis is ambiguous")
    axis_ambiguous: bool = False
    repairs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ImplantFields(BaseModel):
    """What the description says. Never stiffness or strength numbers."""
    implant_type: str = "unspecified"
    body_weight_kg: float | None = Field(default=None, ge=20, le=250)
    activity: Literal["sedentary", "low", "moderate", "active", "high"] | None = None
    special_rules: list[str] = Field(default_factory=list, max_length=8)
    force_n: float | None = Field(default=None, gt=0, le=50000, description="a joint force typed by the user; replaces the load model")


class SuggestedFrame(BaseModel):
    units: str | None = None
    axis: Literal["auto", "x", "y", "z"] = "auto"
    flip: bool = False


class CreateImplantResponse(BaseModel):
    implant_id: str
    mesh_report: MeshReport
    fields: ImplantFields
    parsed_by: Literal["offline", "gemini"] = "offline"
    parse_notes: list[str] = Field(default_factory=list)
    suggested: SuggestedFrame = Field(default_factory=SuggestedFrame)
    disclaimer: str = DISCLAIMER


class ConfirmImplantRequest(BaseModel):
    units: Literal["mm", "m", "inch"]
    axis: Literal["auto", "x", "y", "z"] = "auto"
    flip: bool = False
    body_index: int = Field(default=0, ge=0)
    fields: ImplantFields
    cell_mm: float | None = Field(default=None, gt=0.5, le=50)


class SourcedValue(BaseModel):
    value: float | None = None
    source: Literal["requested", "adjusted", "predicted", "verified", "stored", "estimate", "automatic"] = "automatic"
    note: str | None = None


class AxisSourced(BaseModel):
    x: SourcedValue
    y: SourcedValue
    z: SourcedValue


class ZoneRequirement(BaseModel):
    stiffness_gpa: AxisSourced
    strength_mpa: AxisSourced
    density: SourcedValue | None = None
    max_mass_g: SourcedValue | None = None


class AxisNumbers(BaseModel):
    x: float
    y: float
    z: float


class ZoneSnapped(BaseModel):
    stiffness_gpa: AxisNumbers
    strength_mpa: AxisNumbers
    lattice_id: int


class ZoneReach(BaseModel):
    level: Literal["covered", "extended", "outside", "infeasible"]
    distance_pct: float
    density: float
    message: str
    snapped: ZoneSnapped


class Zone(BaseModel):
    id: str
    name: str
    range_mm: list[float] = Field(..., min_length=2, max_length=2, description="axial range, tip = 0, snapped to the cell grid")
    thickness_mm: float
    area_mm2: float
    stress_mpa: float = Field(..., description="design stress: peak stress of the governing load case x safety factor")
    cells: int = Field(..., description="whole cells along the axis in this zone")
    bone_region: str | None = None
    requirement: ZoneRequirement
    reach: ZoneReach | None = None
    kind: Literal["lattice", "solid", "undecided"]
    reason: str | None = None


class LoadCaseOut(BaseModel):
    name: str
    force_n: float
    angle_deg: float


class Assumption(BaseModel):
    name: str
    value: float | str
    unit: str = ""
    source: Literal["description", "default", "placeholder", "user"]
    todo: bool = False


class LoadSummary(BaseModel):
    cases: list[LoadCaseOut]
    governing: LoadCaseOut
    safety_factor: float
    supported_weight_kg: float
    assumptions: list[Assumption]


class ZoneTable(BaseModel):
    implant_id: str
    state: Literal["uploaded", "confirmed"]
    length_mm: float | None = None
    cell_mm: float | None = None
    cell_range_mm: list[float] | None = None
    load: LoadSummary | None = None
    zones: list[Zone] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER


class ZoneEdit(BaseModel):
    id: str | None = None
    range_mm: list[float] = Field(..., min_length=2, max_length=2)
    kind: Literal["lattice", "solid"] | None = None
    stiffness_z: float | None = Field(default=None, gt=0, le=200)
    strength_z: float | None = Field(default=None, gt=0, le=5000)


class ZoneEditRequest(BaseModel):
    zones: list[ZoneEdit] | None = None
    cell_mm: float | None = Field(default=None, gt=0.5, le=50)


class AssembleRequest(BaseModel):
    choices: dict[str, str] = Field(..., description="zone id -> candidate id, one per lattice zone")
    interface_mm: float | None = Field(default=None, gt=0.1, le=5, description="thickness of the solid plate between zones (default 0.6)")
    sides: Literal[8, 12] = 8
