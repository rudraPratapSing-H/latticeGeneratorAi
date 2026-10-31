# Phase B design note: from one lattice to a whole implant

Status: proposal, nothing built yet. "**Plan silent**" marks a place `docs/BUILD_PLAN.md` does not say; the line after it is my proposed
default. Lines starting **Q#** are questions for you (listed again at the end). This is a design demo, not a medical device: no
clinical, safety or regulatory claim appears in the UI, the API or the docs.

## Reading of the plan's Phase B tasks

| Task | Plan's "Done when" | My reading |
|---|---|---|
| T12 | `scripts/make_test_stem.py`, `core/zoning.py`: a generated stem gives 3 to 5 zones; stress per slice matches a hand calculation for a straight bar within 2%; bad STL, units, axis rows work | as written |
| T13 | `core/profiles/implant.py` + zone-table API: targets from a placeholder bone table and load case, snapped by the picker; each default records its source; solid zones flagged with the reason | as written |
| T14 | frontend zone editor and zone results | the teammate's `lattice-web`; covered by your section 3 (contract, fixtures, browser run), not by new UI design |
| T15 | `core/tiling.py`, `core/assemble.py`: whole-cell tiling per zone on one global grid; one connected lattice per zone; fragments under 1% removed; interface layers; no boolean operations | as written |
| T16 | `core/check.py`, `core/export.py`: stiffness along the length against the target; server-side STL; report | as written |
| T17 | free text becomes structured fields (type, body weight, activity, special rules); never stiffness or strength numbers; user confirms | as written (see Q1) |

## 1. Input and frame

`POST /api/implants` (multipart): STL (binary or ASCII), `material` (Ti-6Al-4V is the only one the backend has), `description`.
Returns `implant_id`, a mesh report (watertight, bodies, size, guessed units, volume, warnings) and the extracted fields.
Nothing is zoned until `POST .../confirm` (units mm / m / inch, axis choice, flip, fields). Units guess: longest side 20 to 600 mm means
mm; outside that the user must confirm and sees the measured size. Axis: PCA of the vertices; if the eigenvalue ratio is under 1.5 the
user must pick the axis. After confirmation the mesh is rotated once into the **implant frame**: long axis = +z running distal (z=0) to
proximal, x and y from the cross-section's principal axes. The lattice cell is placed with its z along the long axis, so the solver's
z is the implant's axial direction. **Plan silent** (which end is "proximal" when the ends look alike): the user flips it; default is the
thicker end proximal for a hip stem.

Storage: `runs/implants/<id>/` holds `mesh.stl`, `implant.json` (fields, frame, units), `zones.json`, `choices.json`, `result.json`,
`export.stl`, `report.md`, written atomically; job state stays in SQLite.

## 2. Zones

Slice at most every 2 mm and at most 200 slices (bug watchlist 18), perpendicular to the axis. Per slice: section polygon (holes allowed),
area, centroid, second moments (shapely). Slices under 1% of the largest area are skipped; end slices inherit their neighbour. Peak stress per slice:
`sigma = N/A + M x c / I`, largest absolute value over the polygon vertices (vertices, so no principal-axis search), in newtons and
millimetres so it is MPa, times a safety factor. Neighbouring slices are merged into 2 to 8 zones when peak stress and thickness stay
within a factor 1.5 (**plan silent**: factor; default 1.5, editable). Zone ends are **snapped to the global cell grid**, so a zone edge can
move by up to half a cell; the zone table shows requested and snapped ends and flags the move. A zone shorter than three cells is merged
with its neighbour or marked solid. Names (neck, upper stem, mid stem, tip) come from the implant type and relative position.

**Load case** (**plan silent**): force `F = activity_factor x body_weight x g` applied at the proximal end centroid, tilted by an angle from
the axis (default 20 degrees); moment at a slice = lateral component x distance along the axis + axial component x the centroid's offset
from the load line. All of it in `core/profiles/implant.py`, with `source: "TODO"` on every number. The same file holds the bone
stiffness placeholders by region. No citation is invented; the UI shows these as "placeholder default".

**Zone decision**: strength need above the dataset's maximum for the chosen density (76.1 MPa at 0.25 for titanium, from the picker) means
`solid`, with the reason; stiffness need above the dataset maximum (about 13 GPa) means "solid, or closest lattice (softer than target)"
and the user chooses; no cell-size range means solid. Everything else is `lattice`. If every zone is solid the response says which limit
forced it. Expect the neck and upper stem to be solid under the placeholder load case; that is an honest result.

## 3. One search per lattice zone (reuse, nothing new in the search)

For each lattice zone the backend builds an ordinary `DesignRequest`: material, `part.size_mm` = the zone's bounding box, `cell_mm` = the one
implant cell size, target = the zone's **snapped** values (stiffness and strength along z only; x and y null = ignored, **plan silent**,
Q6), density limit = the lowest dataset density at which the picker says covered, tolerance 10%, 5 results. `POST /api/implants/{id}/search`
queues them through the existing runner (one at a time on the GPU) and returns `{zone_id: job_id}`; each job has its own SSE stream,
cancel, cache and queue position exactly as in Phase A. `GET .../zones/{zone}/candidates` returns that job's candidates plus the zone's
cell grid. A cache hit makes a repeat run instant. The solver verifies every candidate exactly as before.

**Cell size** (one for the whole implant): upper limit = thinnest lattice zone's thickness / 4 (editable N); lower limit = 0.4 mm / (strut
diameter per cell size from real candidates, about 0.02 to 0.05 of the cell at the three densities). Default = the largest cell in
range that divides the zones well.

## 4. Tiling, boundaries, assembly (no boolean operations)

* **Grid**: one global grid of pitch `cell_mm`, origin at the implant's bounding-box minimum. A cell belongs to a lattice zone when its z-range lies in
  the zone and its square footprint lies inside the implant section at the cell's bottom, middle and top heights (shapely `contains`). Only
  whole cells are kept, so cell properties stay exact; the stair-stepped outer surface is expected (see Q2 for a skin).
* **Cell**: the chosen candidate's octant is mirrored into the full [-1,1]^3 cell and scaled so the side equals `cell_mm`; the strut radius is
  the candidate's, unchanged. Faces tile seamlessly (Phase A test).
* **Different zones, different cells**: the plan's first version puts a **thin solid interface plate** at each boundary plane: the section
  polygon extruded by `interface_mm` (**plan silent**; default 0.6 mm), centred on the grid plane so it overlaps the cells on both sides
  by a small margin. No graded transitions (the plan's later stretch).
* **Solid zones**: the original mesh clipped to the zone's range and capped (own capping with shapely 2.2's triangulation; trimesh's own
  capping needs an extra package, see the dependency note). Solid regions overlap neighbouring lattice by the same margin.
* **Assembly**: concatenate closed shells (struts as prisms, plates, solid parts, optional skin). Connected components are computed per
  lattice zone; fragments under 1% of the zone's struts are removed; if the main part is under 90% the job fails with a message.
* **Printability**: strut diameter below 0.4 mm warns per zone with the smallest passing cell (Phase A rule).

## 5. Export and how it is checked

`GET .../export.stl`: binary STL in millimetres, Z up, built on the server (vectorised numpy; 8-sided struts by default; above about
1,000,000 triangles it warns and drops to 8 sides, and over a hard cap it asks for a larger cell). `GET .../report` is a markdown report
(inputs, zones, targets with sources, per-zone verified numbers, check results, warnings, limits). Proof script
`scripts/validate_implant_stl.py`: loads with `trimesh.load(process=False)` (merging vertices would turn touching shells into
non-manifold edges), checks every shell is closed with consistent winding, outward normals, positive volume, finite values, and that it
opens in trimesh. Run as a test on at least three layouts: straight bar (lattice + solid + lattice), the generated tapered bent stem, and a
four-zone layout with interface plates.

## 6. Endpoints (from the plan, plus two small additions)

| Call | Result |
|---|---|
| `POST /api/implants` | `{implant_id, mesh_report, fields}`; 422 `bad_mesh` / `bad_units` with a plain message |
| `POST /api/implants/{id}/confirm` | units, axis, flip, fields; starts zoning (fast, in a thread) |
| `GET /api/implants/{id}/zones` | zones with requested and snapped values, `source` per value, picker result, `kind` and `reason` |
| `PUT /api/implants/{id}/zones` | edited table (moved boundaries re-zone; changed targets re-snapped; forced solid) |
| `POST /api/implants/{id}/search` | `{zone_id: job_id}` |
| `GET /api/implants/{id}/zones/{zone}/candidates` | candidates (Phase A shape) + `grid` |
| `POST /api/implants/{id}/assemble` | `{choices: {zone_id: candidate_id}, skin_mm?, interface_mm?}` returns a job id |
| `GET /api/implants/{id}/result` | zones, per-zone target vs achieved, length profile, warnings, `verification` labels |
| `GET /api/implants/{id}/export.stl`, `/report` | file downloads |
| *added* `GET /api/implants/{id}` | one-call summary: stage, zone job statuses, so the page can show multi-zone progress |
| *added* `POST /api/implants/{id}/parse` | T17 field extraction for a description (also done at upload) |

Errors use `{"error": {"code", "message"}}`. Every response goes through `sanitize()`. Schemas are Pydantic models; the frontend types are
generated from `openapi.json` (Q8).

## 7. Jobs and SSE for several zones

Design jobs per zone are the Phase A jobs, unchanged. The runner gains a `kind` (`design` or `assemble`); an assemble job has stages
`tile`, `assemble`, `check`, `export` with real progress, runs on the same single worker thread (long geometry never on the event loop),
and is cancellable between stages. Implant-level progress is the summary endpoint (zone jobs done / total). Restart handling is the Phase A
rule. Caching: the assemble job is cached on the canonical request (implant mesh hash, choices, options) plus the model hash.

## 8. What is solver-verified and what is not (stated in the response and the UI)

| Quantity | Source label in the response | Meaning |
|---|---|---|
| Per-zone stiffness, strength, governing failure of the chosen candidate | `solver_verified_infinite_lattice` | Phase A solver, periodic cell |
| Per-zone finite-block stiffness and softening vs the infinite value | `beam_model_estimate` | new finite beam model on a representative block per zone; **not** the per-cell solver check (Q3) |
| Stiffness along the length | piecewise: verified per zone, solid zones from the material modulus | built from the two rows above, never a measurement of the assembled part |
| Mass, volume, strut count, connectivity, printability | `geometry_only` | counted from the mesh; mass is an estimate |
| Interface plates and skin | `not_modelled` | not in any stiffness number |

## 9. New dependencies

`trimesh` (4.12.2) and `shapely` (2.2.0): installed and checked to import together with torch 2.1.2 and numpy 1.26 on Windows. Not needed
for the search, so worker processes never import them (test). **Found while probing**: `trimesh.creation.extrude_polygon` and
`slice_plane(cap=True)` need a triangulation engine (`mapbox-earcut`, `triangle` or `manifold3d`) that is not installed; I will use shapely
2.2's constrained Delaunay triangulation instead, so no further package is needed (Q5).

## Questions (also at the end of my message)

* **Q1 (T17)**: parse the description with the Claude API (needs an API key and the `anthropic` package) or with a deterministic offline
  parser? Proposal: offline rules by default, the Claude API only when `ANTHROPIC_API_KEY` is set, same output schema, never any stiffness
  or strength numbers. Do you want the `anthropic` dependency now?
* **Q2**: lattice zones with whole cells only leave a stepped outer surface. Default **no skin** (`skin_mm` = 0), optional thin ring-prism skin
  on request. Or skin on by default (0.8 mm)?
* **Q3**: add a small finite beam model (`core/check.py`, reusing the element stiffness from `lattice_strength.py` without changing it) for
  the whole-part check, labelled `beam_model_estimate`, or limit the check to per-zone verified numbers plus geometry?
* **Q4**: confirm one cell size for the whole implant (the plan) and the interface-plate default of 0.6 mm.
* **Q5**: OK to use shapely's triangulation rather than adding `mapbox-earcut`?
* **Q6**: zone targets along z only (lateral axes ignored), or the same value on all three axes?
* **Q7**: the load case in section 2 (activity factor x body weight, 20 degree tilt, load at the proximal centroid) as the placeholder, all
  numbers marked `source: TODO`?
* **Q8**: generating TypeScript types needs `openapi-typescript` as an npm dev dependency (the teammate's `types.ts` says not to add it). Add it?
* **Q9 (left as is)**: nested `.git` in `lattice-web/` and the `web/` vs `lattice-web/` name: unchanged, as you did not resolve them.
