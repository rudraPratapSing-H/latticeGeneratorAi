# Lattice Designer: build plan and team split

Oct 29, 2026 · @33° Tilted

## Read this first: rules for the coding agent

This plan is written to be built from. Work through the task list near the end in order, keep to the contracts, and treat every "must" as something a test checks. Where this plan and the existing code disagree, the code in `search_design.py` and `strength-labels/lattice_strength.py` is right and the plan is the thing to fix; say so in the pull request.

### Repository layout

The repo already holds the paper's code (`models/`, `fwdTrain/`, `invOpt/`, `dataGeneration/`), our `search_design.py`, `train_predictor.py`, `encode_lattices.py`, `eval_unseen.py`, the trained `q1.pt`, `encoded_codes.npz`, `results/best_model.pt`, `results/best_c_model.pt`, `data/ptb_mask.csv` and `strength-labels/lattice_strength.py`. Leave all of that where it is. Add:

- `core/`: thin wrappers around the existing search and solver (the only place that imports `search_design`).
- `server/`: the FastAPI app.
- `web/`: the React app.
- `mock/`: real search output used by the mock server (copy from `sample_*.json`, do not invent numbers).
- `scripts/`: one-off tools (build the dataset table, make a test stem, environment check).
- `tests/`: pytest.

### Environment (these cause most first-day failures)

- Python 3.11 only. `numpy<2` (the pinned PyTorch 2.1.2 breaks with NumPy 2).
- PyTorch with CUDA: `pip install torch==2.1.2 --index-url https://download.pytorch.org/whl/cu121`. A plain `pip install torch` on Windows installs the CPU build, which still runs but is many times slower.
- Git LFS must be installed before cloning. Without it the model files arrive as tiny text pointers and loading fails. `scripts/check_env.py` must detect this and say so.
- Node 20 or newer for `web/`.
- Start the mock backend with `MOCK=1 uvicorn server.app:app --port 8000` (PowerShell: `$env:MOCK=1; uvicorn server.app:app --port 8000`). Do not use `--reload` with the real backend; it breaks the process pool on Windows.
- Tests: `pytest -q` (no GPU needed) and `pytest -q -m gpu` (needs the models).

### Invariants (never break these)

1. **The solver decides.** A design counts as a match only after `lattice_strength` verified it. The predictor only proposes.
2. **Do not change the search or solver numbers.** Wrap them. The only edit allowed in `search_design.py` is an optional `should_stop` callback checked between rounds, so a job can be cancelled.
3. **Units.** Physical units at the API edge; normalised inside: stiffness / E\_s and strength / sigma\_y. Buckling from the solver is already relative to E\_s, not sigma\_y. Effective strength = min(yield, (E\_s / sigma\_y) x buckling). For titanium (114 GPa, 880 MPa) the ratio is 129.5. All conversions live in `server/units.py`.
4. **Density is counted periodically.** A strut on the +1 face of the cell is the same strut as on the -1 face. Naively mirroring the octant and merging only identical coordinates counts face struts twice and overstates density by 9% to 118% on our samples. Mass and density come from the periodic count; the strut radius comes from the candidate and is never recomputed in the frontend.
5. **The dataset has three densities: 0.05, 0.15 and 0.25.** The default product uses only these. Other densities are an Advanced option, because the predictor was not trained or tested between them.
6. **Every number on screen names its source:** requested, adjusted, predicted or verified.
7. **Never silently change a user's target.** Show the suggested adjustment and let them accept it. Automatic zone targets are the exception and are labelled as such.
8. **No NaN or Infinity in JSON and no NumPy types in responses.** One `sanitize()` function converts the response before it is sent.
9. **Long work never runs in a request handler or on the event loop.** One GPU job at a time; the rest wait in `queued`.
10. **Missing or broken model files never crash at import.** `/api/health` reports what is wrong.

### Do not

- Add Celery, Redis or a second language for the server.
- Re-implement the solver or the search in JavaScript.
- Assume a GPU is present, or that the dataset file is in the repo (only the compact table described below is).
- Put bone or load numbers in code without a cited source. They live in one config file marked as placeholders.
- Edit mock files by hand. Regenerate them from real runs.

### Done means

Each task in the task list has a test that fails before the work and passes after it. A pull request without that test is not finished.

## What we are building

Lattice Designer takes a target (how stiff, how strong, how heavy) and returns 3D-printable lattice designs whose properties are checked by a physics solver, not just guessed by an AI model. It is our entry for AI Manthan 2.0, Problem Statement 10 (AI-generated lattice design and material property prediction).

Four terms the whole team needs:

- **Lattice:** a 3D mesh of thin struts, repeated like bricks. The repeating block is the unit cell (up to 27 nodes joined by struts).
- **Stiffness:** how little the lattice deforms under load, in GPa, measured along x, y and z.
- **Strength:** how much load it carries before failing, in MPa, along x, y and z. We use the lower of yield and buckling strength.
- **Weight:** set by relative density, the share of the unit cell's volume that is solid.

The demo flow, as the user sees it:

1. Pick a material, then enter target stiffness and strength for x, y and z, plus a weight limit.
2. The backend searches the AI model's design space for lattices likely to match (10 to 20 seconds, up to about 2 minutes when it needs more candidates).
3. A physics solver recomputes the real stiffness and strength of every candidate.
4. The screen lists the best designs ranked by error, with predicted and verified numbers side by side.
5. The user rotates a design in 3D, tiles it into a block, and downloads an STL file for printing.

The selling point: every number on screen is solver-verified, and the AI only proposes.

## Architecture and tech choices

We build one Python service (FastAPI) and one React app, with no separate Node.js layer. The physics solver and the AI models are already Python (NumPy, SciPy, PyTorch), so a Node server would only forward requests and add a second thing to run and debug.

&#91;embedded content: system architecture · 3 services, 4-step pipeline\]

Only the Verify step decides whether a design counts as a match; the AI search just proposes candidates.

| Layer | Choice | Why |
| --- | --- | --- |
| Web app | React + TypeScript + Vite | Fast to start, one codebase for forms, results and 3D |
| 3D view | three.js via @react-three/fiber and @react-three/drei | Scenes written as React components; orbit controls and instancing (thousands of struts) built in |
| Styling | Tailwind CSS | Quick, consistent layout without a design system |
| Data fetching | TanStack Query + server-sent events (SSE) | Job polling and live progress with little code |
| API | Python 3.11, FastAPI, Uvicorn | Same language as solver and models; Pydantic models are the API contract; free interactive docs at /docs |
| Job runner | Process pool inside the FastAPI app | A search takes 10 seconds to 2 minutes, so it runs off the request; Celery and Redis would be overkill for a 3-day build |
| ML runtime | PyTorch (decoder + predictor), loaded once at startup | Runs on the GPU laptop; no model loading per request |
| Solver | `lattice_strength.py` in worker processes | The final judge of every design; about 25 ms per lattice (measured) |
| Storage | SQLite file, plus JSON files per job | Zero setup; survives restarts, so results can be reopened |
| STL export | In the browser (three.js STLExporter) from the strut list | Keeps the API small; backend STL via `trimesh` only as a fallback |
| Hosting | Run on the team GPU laptop; FastAPI also serves the built web app; share through a tunnel (Cloudflare Tunnel or ngrok) | One command to start, one URL for judges, no cloud bill or cold starts |
| Tests | pytest (backend), a written demo checklist (frontend) | Enough to stop regressions without slowing the build |

## API contract

The frontend and backend agree on the endpoints and JSON shapes below before either is built, and the frontend works against a mock server until the real search is ready. FastAPI's Pydantic models are the source of truth; this section is the plan they are written from.

| Method | Path | What it does | Returns |
| --- | --- | --- | --- |
| GET | /api/health | Is the service up, are the models loaded, is a GPU present | `{status, model_loaded, gpu}` |
| GET | /api/materials | Material presets for the dropdown | list of `{id, name, E_gpa, yield_mpa, density_g_cm3}` |
| POST | /api/designs | Start a design job from a target | `202 {job_id}` |
| GET | /api/jobs/{job\_id} | Status, progress and, when done, the ranked candidates | job JSON (below) |
| GET | /api/jobs/{job\_id}/events | Live progress as server-sent events | stream of `{stage, progress, message}` |
| GET | /api/designs/{design\_id} | One candidate in full | candidate JSON (below) |
| POST | /api/verify | Stretch: run the solver on any lattice the user edited | `properties` block |
| GET | /api/designs/{design\_id}/stl | Stretch: STL built on the server (fallback) | binary STL |

**Request: POST /api/designs.** Units are physical (GPa, MPa, mm, g). The backend converts to the model's normalised units: relative density = mass / (volume × material density), stiffness divided by the material's modulus, strength divided by its yield stress. Strength defaults to `strength_mpa`, the lower of yield and buckling; `yield_strength_mpa` (first yield only, tension) is the Advanced alternative, and the two are never sent together. Weight is `max_mass_g` by default, or `rel_density` in Advanced, not both. An axis set to `null` is ignored. `modes` says how each target is judged: `about` (within `tolerance_pct` either side), `at_least` (verified value at or above the target) or `at_most` (at or below). The defaults are stiffness `about`, strength `at_least` and weight `at_most`; with `at_most` the search may try lower densities. Unit-cell size only scales the printed part; the relative properties do not change with it.

```json
{
  "material": "ti64",
  "part": { "size_mm": [40, 40, 40], "cell_mm": 10 },
  "target": {
    "stiffness_gpa": { "x": 8.0, "y": 8.0, "z": 12.0 },
    "strength_mpa": { "x": 90, "y": 90, "z": null },
    "max_mass_g": 60
  },
  "modes": { "stiffness": "about", "strength": "at_least", "weight": "at_most" },
  "tolerance_pct": 10,
  "n_results": 5
}
```

**Job: GET /api/jobs/{job\_id}.** `status` is one of `queued`, `running`, `done`, `failed`. `stage` is `search`, `repair`, `verify` or `rank`. `candidates` stays empty until `status` is `done`.

```json
{
  "job_id": "j_01",
  "status": "running",
  "stage": "verify",
  "round": 2,
  "k": 300,
  "progress": 0.45,
  "message": "Round 2 of up to 3: checking 180 of 400 designs",
  "rounds": [
    { "round": 1, "k": 100, "best_error_pct": 11.8, "matched": false, "n_candidates": 240, "round_seconds": 10.1, "elapsed_seconds": 10.1 }
  ],
  "infeasible": false,
  "warnings": [],
  "reach": { "level": "covered", "distance_pct": 3.2 },
  "candidates": []
}
```

**Job fields.** These come straight from the engine's search output. `rounds` lists each search round with its K, its best error and whether it matched; the engine's `best_err` is a fraction and the server converts it to percent. `infeasible` is true when the requested stiffnesses add up to more than 1.05 x density x E\_s, which no beam lattice can reach. `warnings` holds plain-language strings (printability, density clamped, target far from the data). `reach` is the picker result for the request. When `status` is `done` with no match, `candidates` still holds the closest designs and each has `matches_targets: false`.

**Candidate.** The lattice is stored in the dataset's own format: one octant of the unit cell, as 27 nodes with positions in \[0, 1\]³ and a list of edges (pairs of node indexes). The AI model decodes to exactly this, so the backend does no conversion. The viewer and the STL exporter rebuild the full cell by mirroring the octant about x = 0, y = 0 and z = 0 (all 8 sign combinations), which gives the unit cell \[-1, 1\]³ (side 2). Struts that land in the same place are merged. Opposite faces of the cell are the same plane, so copies tile by shifting 2 units along each axis. All struts share one radius. `predicted` is from the AI model and `verified` from the physics solver; both carry the same fields: stiffness, yield strength, buckling strength, effective strength (the lower of the two) and the governing failure, each per axis, next to the design's density and mass.

```json
{
  "id": "d_a47b310b",
  "rank": 1,
  "match_error_pct": 0.88,
  "matches_targets": true,
  "rel_density": 0.05,
  "mass_g": 14.2,
  "lattice": {
    "format": "octant27",
    "nodes": [[0.0, 0.0, 0.0], [0.5, 0.0, 0.0], [0.5, 0.5, 0.0]],
    "edges": [[8, 12], [1, 4]],
    "cell_size_mm": 10.0,
    "strut_radius_mm": 0.29672
  },
  "predicted": {
    "stiffness_gpa": { "x": 0.456, "y": 0.496, "z": 0.423 },
    "yield_strength_mpa": { "x": 3.7, "y": 3.44, "z": 3.03 },
    "buckling_strength_mpa": { "x": 4.11, "y": 4.5, "z": 4.02 },
    "strength_mpa": { "x": 3.7, "y": 3.44, "z": 3.03 }
  },
  "verified": {
    "stiffness_gpa": { "x": 0.467, "y": 0.5, "z": 0.403 },
    "yield_strength_mpa": { "x": 3.6, "y": 2.7, "z": 2.59 },
    "buckling_strength_mpa": { "x": 4.06, "y": 4.35, "z": 3.5 },
    "strength_mpa": { "x": 3.6, "y": 2.7, "z": 2.59 },
    "governing_failure": { "x": "yield", "y": "yield", "z": "yield" }
  }
}
```

This is a real candidate from a search (titanium, density 0.05), shortened to three nodes and two edges; a full candidate has 27 nodes and 12 to 25 edges. Everything except `mass_g` is produced by the engine; the server adds `mass_g` from the part volume.

The mirroring step, as the viewer and the exporter should implement it (`nodes` has 27 entries in a real candidate):

```ts
const SIGNS = [1, -1].flatMap(sx => [1, -1].flatMap(sy => [1, -1].map(sz => [sx, sy, sz])));

function mirrorOctant(nodes: number[][], edges: number[][]): number[][] {
  const seen = new Set<string>();
  const segments: number[][] = [];
  for (const [i, j] of edges) {
    for (const s of SIGNS) {
      const a = nodes[i].map((v, k) => v * s[k]);
      const b = nodes[j].map((v, k) => v * s[k]);
      const key = [a, b]
        .map(p => p.map(v => Math.round(v * 1e6)).join(','))
        .sort()
        .join('|');
      if (!seen.has(key)) {
        seen.add(key);
        segments.push([...a, ...b]);
      }
    }
  }
  return segments; // [ax, ay, az, bx, by, bz] inside [-1, 1]^3
}
```

When tiling, shift every segment by 2 units per tile and run the same merge, because struts lying on a shared face appear in both neighbouring cells.

`verified` always comes from the physics solver and `predicted` from the AI model. The UI shows both, so the gap is visible per axis. `strength_mpa` is the lower of the yield and buckling values, and `governing_failure` names which one set it. The numbers above are illustrative, not real output.

**Density, radius and mass.** The solver sets one strut radius so that the relative density is exact when struts are counted periodically: a strut on the +1 face of the cell is the same strut as on the -1 face, and is counted once. The viewer's mirror-and-merge step (above) draws the face struts on both faces, which is right for tiling but double counts them for density: on our seven sample files the naive count overstated density by 9% to 118%, while the periodic count matched to 0.004%. So compute density and mass with the periodic rule (wrap +1 to -1 before deduplicating), use `strut_radius_mm` exactly as given, and label mass an estimate: a finite block is a little heavier than density x volume because the struts on its outer faces are whole.

Errors use one shape everywhere: `{"error": {"code": "bad_target", "message": "..."}}`.

**Mock first.** A `mock/` folder in the repo holds `materials.json` and `job_done.json` (five candidates). The backend serves them when started with `MOCK=1`, and the frontend develops against that from day one. The candidates are real solver output from the start: the repository already has sample\_3.json to sample\_9.json from real searches, so copy those in and never write mock numbers by hand. Add the job fields (rounds, infeasible, warnings, reach) to the mock job, and check every mock file against the Pydantic models in the tests.

## Frontend plan

The web app is three screens and one reusable 3D component, built in an order that gives a clickable demo against the mock server within the first days. It lives in `web/` (React + TypeScript + Vite).

**Screens**

1. **Design form.** Material dropdown; stiffness x, y, z (GPa); strength x, y, z (MPa), meaning the load it takes before failing (the lower of yield and buckling; yield-only is under Advanced); maximum mass in grams with part size and cell size (relative density is under Advanced); a "same in all directions" tick box and a "don't care" option per axis; a selector per target (about, at least or at most; defaults: stiffness about, strength at least, weight at most); tolerance. A "fill example" button loads a demo target. Allowed ranges are shown as hints; the limits come from the limits endpoint and the level badge from the reach endpoint (see the target picker section).
2. **Progress.** The four stages (search, repair, verify, rank) with a progress bar fed by the events stream. The job id is in the URL (`/job/:id`), so a refresh does not lose the run.
3. **Results.** One card per candidate, ranked by match error: error badge, mass, relative density, a small 3D thumbnail. A table compares target, predicted and verified values per axis and names the governing failure (yield or buckling). Values outside the tolerance are marked.
4. **Detail.** Large 3D viewer, the same comparison table, and the download buttons.

**The 3D component, `<LatticeViewer>`**

- Takes the candidate's `lattice` and a `tiles` count (1 to 5) and draws every strut as one instanced cylinder, oriented along its segment. It first rebuilds the full unit cell from the stored octant by mirroring, as described in the API contract. Five tiles per side is about 12,000 instances, which a laptop handles.
- Tiling shifts copies by 2 units along each axis, as described in the API contract.
- Controls: orbit and zoom, tile count, solid or wireframe, colour by axis direction. Stretch: a clip plane to see inside, and a colour map of strut stress.

**STL export**

- Built in the browser from the same strut list (for a single lattice block; a whole implant is exported by the server): clip each segment to the block's bounding box (so struts do not stick out of the faces), make a cylinder per strut with 8 to 12 sides, merge, and write with three.js's STLExporter.
- Overlapping cylinders at the nodes are fine; slicers merge them.
- Warn when the strut diameter is below a printer's usual minimum (a 0.4 mm nozzle is a common reference).

**Code layout**

- `web/src/api/` typed client and the TypeScript types copied from the contract
- `web/src/pages/` the four screens
- `web/src/components/LatticeViewer/` the 3D component
- `web/src/lib/` `tiling.ts`, `clip.ts`, `stl.ts` (plain functions, unit-testable)

The API address comes from `VITE_API_URL`, so the same build points at the mock or the real backend.

## Backend plan

The backend is one FastAPI app in `server/` that wraps three things Aryan owns (the search, the models and the solver) behind the API contract. Its own job is the plumbing: requests, unit conversion, background jobs, progress, storage and serving the web app.

**What happens on POST /api/designs**

1. Validate the request and convert physical units to normalised targets (relative density, stiffness over modulus, strength over yield stress).
2. Create a job row in SQLite and return `202 {job_id}` straight away.
3. A worker runs the pipeline and reports `{stage, progress, message}` after each step: **search** (AI model proposes lattices), **repair** (fix invalid ones), **verify** (solver recomputes stiffness and strength at the real density), **rank** (keep those that satisfy each target's mode (about, at least or at most), order by match error).
4. Results are written as JSON under `runs/<job_id>/` and into SQLite; the job moves to `done`.

**Interfaces the backend codes against**

The existing search and solver are wrapped in one file, `core/engine.py`, written against `search_design.py`. Nothing else in the backend imports PyTorch or `search_design`. The verification step is inside the search (it checks the starting designs, an early snapshot and the final designs), so the backend never verifies candidates again.

- `load_engine(model_dir, device) -> Engine`: loads the VAE, the stiffness head, the predictor, the stored codes and the node mask once. It returns a status object with a reason if something is missing, and never raises at startup.
- `Engine.run(request, on_progress, should_stop) -> SearchResult`: builds the `Target`, runs the adaptive search (K = 100, then 300, then 1000; it stops on a match, when a round gains under half a point, or at the time budget) and returns `{material, rounds, infeasible, candidates}`, the same structure `search_design.py` writes with `--out`. Candidates are already solver-verified and ranked.
- `core.reach` is the dataset picker described below.
- `core.verify(lattice, rel_density, material) -> Properties` exists only for the stretch endpoint `/api/verify` and calls `solve` from `lattice_strength.py`.

Until the engine is wired in, `core/mock.py` returns the real results stored in `mock/` through the same signatures, so the backend and frontend are never blocked.

**Design decisions**

- The verify step runs in a process pool (solver calls are independent, about 25 ms each, measured), but verification already happens inside the search, so the real timing is what we measured: about 10 to 20 s for the first round (K=100), about 30 s with K=300 and about 2 minutes with K=1000 on a busy GPU. Pool workers import only the NumPy solver, never PyTorch. The search runs on the GPU in one dedicated process.
- One search at a time by default; extra jobs wait in `queued`. A demo does not need more.
- Progress goes out over server-sent events; the status endpoint works as a polling fallback.
- Config in environment variables: `MOCK`, `MODEL_DIR`, `DEVICE`, `WORKERS`.
- A `/api/health` check reports whether the models loaded and whether a GPU is in use, which saves time on demo day.
- Cache: identical requests return the stored job. A few pre-run demo targets are stored so the demo still works if the GPU misbehaves.

**Code layout**

- `server/app.py` routes and startup
- `server/schemas.py` Pydantic models (the contract)
- `server/jobs.py` queue, worker, progress
- `server/units.py` unit conversion, with tests
- `server/store.py` SQLite access
- `core/` engine.py (wrapper over search\_design.py), reach.py (dataset picker) and mock.py; Aryan owns the search and solver code they wrap
- `tests/` pytest: unit conversion, schema round-trip, a mock end-to-end job
- `scripts/` check\_env.py, build\_reach\_table.py, make\_test\_stem.py
- `mock/` real search output (copied from `sample_*.json`), validated against the schemas in the tests

## Target picker grounded in the dataset (`core/reach.py`)

Every target the system accepts, suggests or assigns automatically is checked against what the dataset actually contains. The dataset is 300,000 lattices, each solved at relative density 0.05, 0.15 and 0.25 (900,000 rows). The search can reach somewhat beyond stored lattices, but far from them it fails, and some targets are impossible for any beam lattice. The picker tells the user which case they are in before a search runs, and snaps automatic targets to values that exist.

### What the dataset covers (titanium Ti-6Al-4V: 114 GPa, 880 MPa)

Computed from all 900,000 solver rows. Stiffness is per axis; strength is the effective strength min(yield, ratio x buckling) per axis.

| Relative density | Stiffness min / median / max (GPa) | Strength min / median / max (MPa) |
| --- | --- | --- |
| 0.05 | 0.005 / 0.33 / 2.5 | 0.08 / 2.3 / 16.0 |
| 0.15 | 0.04 / 1.2 / 7.8 | 0.40 / 7.5 / 45.3 |
| 0.25 | 0.10 / 2.3 / 13.1 | 0.83 / 13.1 / 76.1 |

Two hard limits show in the data. The three axis stiffnesses always sum to at most density x E\_s (the maximum in the data is exactly 1.000 of that bound, the plain cubic lattice). Strength never exceeds about 0.36 x density x sigma\_y. These numbers are for titanium; `reach.py` recomputes them for any material, because the strength limit depends on E\_s and sigma\_y.

Consequence for products: a titanium lattice in this dataset cannot be stiffer than about 13 GPa or stronger than about 76 MPa along an axis. A requirement above that (for example, a stem zone needing hundreds of MPa) cannot be a lattice from this dataset. It becomes solid, and the tool says so.

### How it works

1. **Table.** `scripts/build_reach_table.py` reads `labels_300k_x3.csv` once and writes `reach_table.npz`: for each row, the density index (0, 1, 2), the three normalised stiffnesses (from the inverse of the 3x3 stiffness block, the same formula `search_design.py` uses), the three yield values and the three buckling values. Float32, about 36 MB, tracked with Git LFS so a teammate does not need the 205 MB CSV.
2. **Load.** At startup, load the table and compute the material-specific values: stiffness = normalised x E\_s, strength = min(yield x sigma\_y, E\_s x buckling).
3. **Distance.** For a request (six numbers, some possibly null, plus modes) and one density, the distance to each stored lattice is the largest relative error over the active values, using the same rule as the solver check ("about" is two-sided, "at\_least" counts only a shortfall, "at\_most" only an excess). Reuse that function; do not write a second version. Over 300,000 rows this takes milliseconds in NumPy.
4. **Level.** Take the best distance over the allowed densities and label it:

| Level | Rule | What it means, from our own tests |
| --- | --- | --- |
| `covered` | within the tolerance (10%) of a stored lattice | Requests from lattices the predictor never saw matched 10 of 10, nine in the first round |
| `extended` | 10% to 25% from the nearest stored lattice | The search has to invent a new design. With the nearest 15% removed it matched 65% of targets at K=100 and 80% at K=300 (20 targets) |
| `outside` | more than 25% | Not tested well. Run it, but warn that a match is unlikely |
| `infeasible` | stiffness sum above 1.05 x density x E\_s, or strength above the density's maximum | No beam lattice can do this. Do not search; show the bound and the nearest achievable target |

5. **Density.** If the user gave a mass limit or a density, use it. If not, check the three dataset densities from lowest to highest and take the first one that is `covered`; if none is, take the one with the smallest distance. Densities between the three are only used when the user asks for them in Advanced.
6. **Snap.** `snap(target)` returns the six values of the nearest stored lattice at the chosen density, and how far they moved from the request.

### Where the picker is used

- **Design form:** `GET /api/limits?material=ti64` returns the per-density ranges above, for hints and input validation. As the user types, `POST /api/reach` returns the level, the distance, the nearest achievable target and a one-line message. The form shows "closest achievable" with an Accept button; it never changes the user's numbers by itself.
- **`POST /api/designs`:** runs the check first. `infeasible` returns 422 `bad_target` with the bound unless the request carries `force: true`. Other levels run and the result carries the level as a warning.
- **Implant zones:** every automatic zone target is snapped before it is shown in the zone table. A zone whose strength need is above the density maximum is marked solid; one whose stiffness need is above the dataset maximum is marked "solid, or closest lattice (softer than target)" and the user chooses.

### `/api/reach` shape

```json
{
  "level": "extended",
  "distance_pct": 17.3,
  "density": 0.15,
  "requested": { "stiffness_gpa": [2.0, 1.7, 2.2], "strength_mpa": [13, 12, 13] },
  "nearest": { "stiffness_gpa": [1.9, 1.6, 2.0], "strength_mpa": [11.5, 10.8, 12.1], "lattice_id": 123456 },
  "bounds": { "stiffness_sum_max_gpa": 17.1, "strength_max_mpa": 45.3 },
  "message": "No stored lattice is within 10%. The search will try to design a new one."
}
```

### Tests the picker must pass

1. For 1,000 random rows, the six values of that row return distance 0 and `covered`.
2. The same values multiplied by 1.5 return distance of about 50% and `outside`.
3. Stiffness values summing to 1.2 x density x E\_s return `infeasible`.
4. Strength above 76.1 MPa for titanium returns `infeasible` at 0.25 and at every lower density.
5. Switching the material to a softer one with a lower yield changes the strength limit in the expected direction.
6. A query over 300,000 rows takes under 100 ms and the loaded table uses under 300 MB.
7. GPU test: 10 targets taken from lattices outside the 100k, with the nearest same-density lattice kept in the pool, come back `covered`, and the search matches at least 9 of 10.

## Implant story: from one lattice to a whole femoral implant

The single-request flow gives one unit cell for one set of requirements. The implant story builds on it: an implant has different requirements along its length, so we split the implant into zones, design a lattice for each zone, tile and trim each, and join them into one part. It starts after the single-request flow works end to end, and it reuses that flow's search job unchanged, once per zone.

### User journey

1. The user uploads an STL of the implant, picks the material and types a short description (for example: hip stem, 75 kg patient, keep the neck solid).
2. Claude turns the description into structured fields: implant type, body weight, activity and special rules. It does not choose any stiffness or strength numbers. The user confirms the fields.
3. The backend slices the STL along its long axis and proposes zones, each with stiffness, strength and weight targets and a lattice or solid flag.
4. In the zone table the user checks and edits the targets and drags the zone boundaries on the 3D view. In automatic mode this step is skipped.
5. The backend runs one search per zone. The user sees ranked candidates for every zone, tiled and trimmed in a preview, with their verified specs.
6. The user picks one candidate per zone. The backend assembles the implant and runs a check on the whole part.
7. The user sees stiffness along the length against the target, a pass or fail per zone, and downloads the STL and a short report.

### How zones and targets are made

- **Zones.** Fit the long axis to the mesh, cut slices every few millimetres (at most 200), measure each slice's area and second moment of area, then merge neighbouring slices with a similar load level or thickness into 2 to 8 zones. Name the groups from the implant type (neck, upper stem, mid stem, tip). An optional outer layer and inner core split is available.
- **Strength.** From a load case (body weight and activity, or a force the user types in): axial force and bending moment at each slice, using newtons and millimetres so stress is in MPa. Stress at each point of the outline = force / area + moment x distance / second moment; take the largest absolute value over the zone and multiply by a safety factor.
- **Stiffness.** Match the local bone stiffness for that region to limit stress shielding. The bone table is a placeholder to be checked and cited, and the user can overwrite it. In titanium the dataset reaches about 13 GPa per axis at most, so a bone-matching target above that cannot be met by a lattice from this dataset; the picker flags it.
- **Weight.** The lowest of the three dataset densities (0.05, 0.15, 0.25) at which the zone is `covered` by the picker.
- **Snap.** Every automatic target is snapped by the picker to the nearest value that exists in the dataset. The zone table shows requested and snapped values side by side.
- **Solid or lattice.** A zone whose strength need is above the dataset maximum is flagged solid, or solid core with a lattice shell, and is not searched. The limit comes from the picker for the chosen material (76 MPa at density 0.25 for Ti-6Al-4V, from the data).
- **Cell size.** One size for the whole implant. Upper limit: the thinnest zone's thickness divided by N cells (N = 4 as an adjustable default, to be checked against the finite-block result). Lower limit: the printable minimum strut, cell size at least 0.4 mm / (2 x strut radius per cell size); from our samples that ratio is about 0.02 to 0.03 at density 0.05, 0.04 to 0.05 at 0.15 and 0.045 to 0.05 at 0.25, and it is re-checked once real candidates exist. If the range is empty, thin zones become solid.

### Joining zones

Different lattices do not line up at a boundary. The first version puts a thin solid interface layer between zones. If time allows, choose per-zone candidates whose boundary nodes are closest and snap them. Graded transition cells made by blending latent codes are a later stretch goal.

### Limits to state in the demo

- Strength is static; fatigue is not modelled.
- A finite part is a little softer than the infinite lattice the properties describe. The check on the assembled part reports how much.
- Trimming along whole cells keeps cell properties exact; cut struts, if any, are removed.
- This is a design aid. Printing and mechanical tests are needed before any clinical claim.

### Implant API (added to the contract)

Same style as the single-request API: JSON, jobs polled for status, errors as `{"error": ...}`. Each zone search is an ordinary search job from the contract above, so the progress and candidate shapes do not change.

| Call | What it does |
| --- | --- |
| `POST /api/implants` | Multipart upload: STL file, material, description. Returns `implant_id`, a mesh report (watertight, number of bodies, size, guessed units) and the structured fields Claude extracted |
| `POST /api/implants/{id}/confirm` | The user confirms units, axis and direction (flip), and the extracted fields. Zoning does not start before this |
| `GET /api/implants/{id}/zones` | Proposed zones. Per zone: id, axial range, thickness, area and stress, a requirement (stiffness x, y, z, strength x, y, z, density or mass limit) with the source of each value, the picker result (level, snapped values), and `kind`: lattice, solid or undecided, with the reason |
| `PUT /api/implants/{id}/zones` | The edited zone table (moved boundaries, changed targets, forced solid) |
| `POST /api/implants/{id}/search` | Creates one ordinary design job per lattice zone, using that zone's snapped target and density limit; returns `{zone_id: job_id}` |
| `GET /api/implants/{id}/zones/{zone_id}/candidates` | Ranked candidates for one zone (same shape as a design candidate) and the zone's cell grid: cell counts per axis and cell size |
| `POST /api/implants/{id}/assemble` | Body `{choices: {zone_id: candidate_id}}`. Starts assembly and the whole-part check; returns a job id |
| `GET /api/implants/{id}/result` | Assembled strut network, per-zone target against achieved, stiffness along the length, warnings |
| `GET /api/implants/{id}/export.stl` | Printable file built on the server (an implant can reach about a million triangles, too heavy for a browser). The report is `GET /api/implants/{id}/report` |

Mock first, as before: `mock/implant_zones.json`, `mock/implant_candidates.json` and `mock/implant_result.json` let the frontend build every implant screen before the backend exists.

### Frontend plan for the implant story

New screens, in the same `web/` app, reusing the lattice viewer and candidate card:

1. **Upload and describe.** STL drop zone, material dropdown, description box, then a confirmation card with the fields Claude extracted.
2. **Zone editor.** A 3D view of the implant with draggable slice planes, next to the zone table (stiffness, strength, weight, lattice or solid). Blank fields mean use the default, and the default source is shown. A toggle chooses automatic or semi-automatic mode.
3. **Zone results.** One tab per zone, each showing ranked candidate cards with target against verified values and a small tiled preview. A solid zone shows its reason instead. The user picks one per zone.
4. **Assembled implant.** The whole implant in 3D with zones coloured, a plot of stiffness along the length against the target, pass or fail per zone, and the export buttons.

New components: `<ImplantViewer>` (STL plus zone overlay, slice-plane drag), `<ZoneTable>`, `<ZoneCandidates>` and `<StiffnessProfile>` (the plot). The 3D viewer loads STL with the same Three.js setup already used for lattices.

### Backend plan for the implant story

New modules under `core/`, with the endpoints above added to `server/`. The search itself is untouched.

- `core/reach.py`: the dataset picker, shared with the single-request flow.
- `core/zoning.py`: load the STL, check and repair the mesh, fit the axis, slice, section properties, load case stress, group into zones, lattice or solid flag.
- `core/profiles/implant.py`: the bone stiffness table, default load case and safety factor, and the schema Claude fills from the description. Kept in one config file so the numbers can be cited and changed in one place.
- `core/tiling.py`: repeat a candidate cell on one global grid inside a zone mask, keep whole cells, add the optional skin.
- `core/assemble.py`: merge the zones into one strut network, join nodes, add interface layers, remove loose fragments. Concatenate meshes; no boolean operations.
- `core/check.py`: a finite-block beam model of the assembled part, loaded along each axis, to report stiffness along the length and the softening against the infinite-lattice values.
- `core/export.py`: strut network to STL, and the report.

Design decisions: zones are stored with the implant so edits are saved; every default records where it came from; zone searches run one after another on the GPU and the job list reports progress per zone (about 10 to 30 s each, so a five-zone implant takes a few minutes).

### Build order and risks for the implant story

1. Zoning on a test stem STL (a tapered, bent stem we generate), with the zone table as JSON and the mock files.
2. Frontend: upload, zone editor and zone results against the mocks, in parallel with step 1.
3. Hook zone searches to the existing search job.
4. Tiling, assembly, export.
5. The whole-part check and the stiffness-along-length plot.
6. Description parsing by Claude; graded transitions only if time remains.

Risks: the interface between zones is the weakest point (start with solid interface layers); STL files that are not watertight need repair or a clear error; the bone and load defaults need citing; many stem zones will be solid, which is an honest result and should be shown clearly; and time, since the zone, tiling and assembly code is new. If time runs short, the minimum demo is zoning, per-zone search and a tiled preview of each zone, with assembly shown as a roadmap slide.

## Failure cases and how the system handles them

Each row is a case that can break the system, how the code notices it, and what the user sees. Every row needs a test, and the user-facing text must be plain.

### Requests and targets

| Case | How it is detected | What the system does |
| --- | --- | --- |
| No target given (all values null) | Validation | 422 `bad_target`: give at least one stiffness or strength |
| Zero, negative, NaN, text, or a value above the material itself (stiffness above E\_s, strength above yield) | Validation and plausibility rules | 422 naming the field; a unit hint when stiffness looks like MPa instead of GPa |
| Stiffness sum above 1.05 x density x E\_s, or strength above the density's maximum | Picker level `infeasible` | No search. Show the bound and the nearest achievable target; `force: true` runs it anyway |
| Target far from every stored lattice | Picker level `outside` | Run with a warning and offer the nearest achievable target |
| Stiff but weak, or soft but strong, a combination the dataset lacks | Large distance on one axis | Name the value that conflicts; show the nearest achievable |
| Mass limit implies density below 0.05 or above 0.25 | `units.py` | Below: 422 with the lightest mass possible. Above: use 0.25 and say so |
| Cell larger than the part, or part not a whole number of cells | Validation | Error if the cell is larger; otherwise a warning with the nearest whole count |
| Different material changes which failure governs and the strength limit | Picker recomputes per material | Show governing failure per axis and the limits for that material |

### Search, solver and server

| Case | How it is detected | What the system does |
| --- | --- | --- |
| Search ends with no design inside the tolerance | `matches_targets` false for all | Return the closest five labelled "closest, not a match" with the shortfall per axis. A strength shortfall of more than 0.5% counts as a miss, so show the number |
| Search returns no valid lattice at all (all empty or disconnected) | Zero candidates | Fall back to the nearest stored lattices from the picker, solver-verified, and say so; error code `no_valid_design` only if that also fails |
| Solver returns NaN, infinity, or a floppy lattice with absurd stiffness | Finite and positive check; stiffness sum above 1.05 x density x E\_s | Skip the candidate and count it in the job's round summary |
| Near-duplicate designs | The 1% signature rule already in the search | Keep one |
| GPU missing or out of memory | Exception around each round | Retry with a smaller K, then the CPU; `/api/health` shows the device |
| Last round (K=1000) takes about two minutes on a busy GPU | Time budget | Stop escalating, return the best so far with the elapsed time |
| User cancels or closes the page | `should_stop` flag | Stop after the current round; status `cancelled` |
| Server restarts during a job | Job rows saved at start | On startup mark running jobs `failed` with reason `restart`; the page offers retry |
| Several users at once | Queue length | Show queue position; refuse beyond a set length with 429 |
| Same request again | Cache keyed by the canonical request and the model file hash | Return the stored result; the cache clears when a model file changes |
| Model files missing or are Git LFS pointer text | Size and header check at startup | `model_loaded: false` with the reason and the fix |
| NumPy 2 or CPU-only PyTorch | `scripts/check_env.py` | Print the exact fix command |
| Windows process pool re-imports the app and hangs | Startup test | Use the spawn context, put pool creation under the main guard, and make workers import only the NumPy solver, never PyTorch |
| Tunnel or proxy buffers or drops the progress stream | No event for 20 s | Heartbeat every 15 s from the server; the page falls back to polling the job every 2 s |

### Output, 3D view and printing

| Case | How it is detected | What the system does |
| --- | --- | --- |
| Strut too thin to print | Diameter = 2 x strut radius; warn below 0.4 mm | Show the smallest cell size that passes: cell size at least 0.4 mm / (2 x radius per cell size). Example: a 10 mm cell at density 0.05 has a 0.59 mm strut; at 5 mm it is 0.30 mm and fails |
| Shown mass differs from the printed block | Periodic count versus a finite block | Mass = density x part volume x material density, labelled "estimate"; a finite block is a little heavier because outer-face struts are whole |
| User asks for 50 tiles | Input clamp | 1 to 5 in the viewer; up to 8 for STL with a warning |
| STL too large | Estimate = struts x sides x 2 triangles | Warn above 1 million triangles and drop from 12 to 8 sides |
| WebGL context lost, weak laptop | `webglcontextlost` event | Show a message and the rendered thumbnail instead of a blank canvas |
| NaN in a response | `sanitize()` | Never reaches the client (see invariants) |

### Implant

| Case | How it is detected | What the system does |
| --- | --- | --- |
| STL not watertight, flipped normals, or several separate pieces | Mesh checks (watertight, volume sign, body count) | Try an automatic repair; if it still fails, say what is wrong and let the user pick one body |
| Units unknown (mm, m or inch) | Longest side outside 20 to 600 mm | Ask the user to confirm the units and show the measured size |
| No clear long axis, or the head end is ambiguous | Axis eigenvalue ratio below 1.5; end areas similar | Ask the user to pick the axis and flip the direction in the viewer |
| Slices with holes, several loops, or almost empty end slices | Polygon area with holes; skip slices under 1% of the largest area | Compute area and inertia from the polygon; end slices inherit the neighbour |
| Too many or too few zones, or a zone shorter than three cells | Rule: 2 to 8 zones, each at least three cells long | Merge with the neighbour or mark solid |
| Thin section needs a small cell, printing needs a large one | Cell range = section size / N up to the printable minimum | If the range is empty, mark the zone solid and explain |
| Neighbouring zones differ hugely in stiffness | Ratio above 3 (adjustable) | Warn, use the interface layer; graded transition is the later fix |
| Every zone is solid | Count of lattice zones | Explain which limit forced it (strength above the dataset maximum) and suggest a lighter load or a solid core with a lattice shell |
| Body weight, load or angle missing, zero or absurd | Range check | Use the default, show it with its source, and ask for confirmation |
| Loose strut groups after assembly | Connected components per lattice zone | Remove fragments under 1% of the struts; fail with a message if the main part is under 90% |
| Whole-part check too big for memory | Node count limit | Check a representative block per zone instead of the full part |

## Bug watchlist: mistakes an agent is likely to make

Each item is a guard test, not advice.

1. **Density counted by naive mirroring.** Guard: for the seven `sample_*.json` files, the periodic count (wrap +1 to -1 before deduplicating) gives a density within 0.1% of `rel_density`; on our samples the naive count was 9% to 118% too high, and the periodic one deviated by 0.004%.
2. **Stiffness taken as C1111.** Young's modulus along x is 1 / S11 of the inverse of the 3 x 3 normal block, not C1111. The dataset columns are normalised stiffness entries. Guard: on a row where C1122 is not zero, E\_x differs from C1111, and the code must give the same value as `E_x` produced by c9\_to\_E in search\_design.py.
3. **Buckling divided by yield.** Buckling is relative to E\_s. Guard: effective strength unit test with the titanium ratio 129.5.
4. **Sending both strength and yield strength**, or a mass limit and a density together. Guard: schema validator rejects it.
5. **Axis or unit-scale confusion in tiling.** The cell spans 2 units and equals `cell_size_mm`, so one unit is `cell_size_mm / 2`. The radius is already in mm. x, y and z in the UI are the solver's x, y and z; the STL must not swap them (three.js is Y-up, STL is Z-up, so rotate once, on export only).
6. **Float equality on density.** The table stores float32. Compare with `isclose` or map to the index 0, 1, 2; never `==`.
7. **Search on the event loop.** A synchronous call inside `async def` freezes every request. Guard: while a job runs, `/api/health` still answers in under 100 ms.
8. **NaN, infinity or NumPy types in JSON.** Guard: a test that feeds NaN through `sanitize()` and checks the response parses with `allow_nan=False`.
9. **Pydantic version mix-up.** Pin Pydantic 2 and use its syntax throughout.
10. **Cache key from dictionary order.** Use canonical JSON (sorted keys, floats rounded to 6 digits) plus the model hash.
11. **SQLite across threads.** Use WAL mode and a connection per call, not one shared connection.
12. **Progress stream through a proxy.** Use `sse-starlette`, send heartbeats, and pass the job id in the URL; the browser's `EventSource` cannot set headers.
13. **React StrictMode runs effects twice in development** and can submit the design twice. Guard: the form submits from an event handler, not an effect.
14. **Windows paths and line endings.** Use `pathlib`, open files as UTF-8, and never hard-code backslashes.
15. **Contract drift.** Generate TypeScript types from FastAPI's `openapi.json` (`openapi-typescript`) and validate every file in `mock/` against the Pydantic models in CI.
16. **Non-deterministic GPU tests.** Seed the search and compare with tolerances, never exact equality.
17. **Implant stress units.** Use newtons and millimetres so stress comes out in MPa; take the largest absolute stress over the slice outline (compression counts); evaluate it at the polygon vertices, which avoids choosing principal axes.
18. **Slicing too finely.** Cap at 200 slices; trimesh sections are slow at 1,000.
19. **Boolean mesh operations.** They need extra libraries and fail on messy meshes. Do not use them: concatenate zone meshes, with solid regions overlapping the lattice by a small margin; slicers merge overlaps.

## Task list for the coding agent

Build in this order. Tasks T0 to T11 are the single-request product and must work before any implant task starts. Each task is one pull request with the test listed.

| # | Task | Main files | Done when |
| --- | --- | --- | --- |
| T0 | Environment check | `scripts/check_env.py` | Reports Python 3.11, NumPy below 2, PyTorch and CUDA status, and each model file as OK, missing or Git LFS pointer. A test with a fake pointer file reports `pointer` |
| T1 | Engine wrapper around the existing search | `core/engine.py` | `Engine.run(request, on_progress, should_stop)` returns the same structure as `--out` in `search_design.py` (material, rounds, infeasible, candidates). GPU test: stiffness 0.465, 0.496, 0.402 GPa and strength 2.22, 2.65, 2.19 MPa at density 0.05 in titanium (the request behind `sample_3.json`), with the request echoed in the result, matches in round 1 with error under 10% |
| T2 | Units and request validation | `server/units.py`, `server/schemas.py` | Round-trip tests for stiffness, strength and mass; titanium ratio 129.5; schema rejects strength with yield strength together, a mass limit with a density, and all-null targets |
| T3 | Dataset picker | `scripts/build_reach_table.py`, `core/reach.py` | The seven tests in the picker section pass; the table builds in under a minute |
| T4 | Server skeleton and mock mode | `server/app.py`, `mock/` | `MOCK=1` serves `/api/health`, `/api/materials`, `/api/limits`, `/api/reach` and a job that walks through the four stages and returns the real candidates copied from `sample_*.json`. Every file in `mock/` validates against the Pydantic models |
| T5 | Job runner | `server/jobs.py`, `server/store.py` | One job at a time, queue position, progress events with a heartbeat, cancellation, saved jobs that survive a restart. While a job runs, `/api/health` answers in under 100 ms |
| T6 | Real pipeline | `server/app.py`, `core/engine.py` | Picker check first, then the engine, then mass and printability warnings added. The same request twice returns the cached result. The response passes the `allow_nan=False` test |
| T7 | Frontend skeleton and types | `web/` | Types generated from `openapi.json`; the app runs against the mock; routing and the job id in the URL work after a refresh |
| T8 | Design form with picker hints | `web/src/pages/` | Fields, modes, "fill example"; the limits and the level badge update as the user types; Accept applies the suggestion only when clicked |
| T9 | Progress, results and detail pages | `web/src/pages/` | Stage bar fed by events with the polling fallback; ranked cards; target / predicted / verified table; "closest, not a match" labelling and the shortfall |
| T10 | 3D viewer and STL export | `web/src/lib/`, `LatticeViewer` | The periodic-density test passes for the seven samples; one cell tiles seamlessly 1 to 5 per side; the exported STL opens and slices in a slicer |
| T11 | Demo safety net | `server/`, `scripts/` | Five pre-run demo targets stored; one command starts server and web; the README has the steps; a recorded video exists |
| T12 | Test stem and zoning | `scripts/make_test_stem.py`, `core/zoning.py` | The generated stem produces 3 to 5 zones; stress per slice matches a hand calculation for a straight bar within 2%; the failure rows for bad STL, units and axis work |
| T13 | Implant defaults and zone table API | `core/profiles/implant.py`, `server/` | Targets come from the placeholder bone table and load case and are snapped by the picker; each default records its source; solid zones are flagged with the reason |
| T14 | Zone editor and zone results screens | `web/` | Dragging a plane re-zones; edited targets are saved; one tab of ranked candidates per lattice zone |
| T15 | Zone searches, tiling and assembly | `core/tiling.py`, `core/assemble.py` | Whole-cell tiling per zone on one global grid; one connected lattice per zone; fragments under 1% removed; interface layers added; no boolean operations |
| T16 | Whole-part check and export | `core/check.py`, `core/export.py` | Stiffness along the length against the target is plotted; server-side STL of the assembled part; the report downloads |
| T17 | Description parsing | `server/` | Free text becomes the structured fields (implant type, body weight, activity, special rules) and never produces stiffness or strength numbers; the user confirms before use |

Order rules: T3 can run in parallel with T1 and T2. T7 to T9 can start as soon as T4 serves the mock. T12 to T17 start only after the T11 demo works end to end. If time runs out, stop after T11 and show the implant story as a roadmap, with T12 and T13 as the proof of concept.

### What the agent needs from Aryan

1. The labels file `labels_300k_x3.csv` locally, to build the reach table once (the table itself is then committed with Git LFS).
2. The GPU laptop for the `-m gpu` tests; everything else runs on any machine with the mock.
3. A decision on the bone and load placeholders, with citations, before T13.
4. One real implant-like STL if available; otherwise T12 generates a test stem.

## Work split

Four people, four areas that meet only at the API contract and one drawing component, so nobody waits on anyone after the first day. Names are placeholders: fill in who takes A, B and C.

| Who | Owns | First deliverables, in order | Hands off to |
| --- | --- | --- | --- |
| **Aryan** (lead) | ML pipeline, search, solver verification (`core/`), integration | 1. Predictor finished and checked. 2. Search plus round-trip test. 3. The engine wrapper and the dataset picker (tasks T1 and T3 in the task list). 4. Five real sample results for `mock/`. 5. Comparison against the paper's own search. | A: `core/` functions. B and C: real sample JSON |
| **A: Backend** | `server/`: FastAPI app, schemas, units, jobs, SQLite, progress events, `MOCK=1` mode, start script, tunnel | 1. App skeleton, `/api/health`, `/api/materials`. 2. Pydantic schemas copied from this contract. 3. Mock job that walks through all four stages. 4. Unit conversion with tests. 5. Real pipeline wired to `core/`, plus the pre-run demo cache | B: running mock server by end of the first phase |
| **B: Frontend app** | `web/`: design form, progress, results list, detail page, API client and types | 1. Vite + React skeleton, router, API client against the mock. 2. Design form with validation and "fill example". 3. Progress screen with live events. 4. Results cards and the target / predicted / verified table. 5. Polish, errors, empty states, phone layout | C: embeds `<LatticeViewer>` in results and detail |
| **C: 3D, export and demo** | `LatticeViewer`, tiling, clipping, STL export, printability warning; then pitch deck, demo script, recorded backup video | 1. Viewer that draws a hard-coded cubic lattice. 2. Viewer fed from `mock/job_done.json`, tile count control. 3. `clip.ts` and `stl.ts`, tested by opening the STL in a slicer. 4. Colour by axis; clip plane if time. 5. Slides and demo script | B: `<LatticeViewer lattice tiles />` component |

**Working rules**

- One repository with folders `core/`, `server/`, `web/`, `mock/` and `docs/`. Everyone works on a branch and opens a pull request; Aryan merges.
- The API contract is frozen at the end of the first phase. A change needs a message in the group chat and an update to this doc and to `schemas.py` in the same pull request.
- A 15-minute stand-up each day: what is done, what is blocked, what is next.
- Anything not in the contract (extra fields, new endpoints) is a stretch item and does not block others.

## Timeline

&#91;embedded content: roadmap · 4 phases, 4 people, 3 gates\]

Each gate is a check the whole team runs together: Gate 0 is a mock run from form to 3D view with the contract frozen, Gate 1 is the first real solver-verified designs on screen, and Gate 2 is the feature freeze with an STL that slices cleanly. Tell me the event's start date and I will pin the phases to calendar dates.

## Risks and fallbacks

The biggest risk is the AI search, and the plan is built so a weak search costs result quality but never correctness: the solver checks every design that reaches the screen.

| Risk | What happens | Fallback |
| --- | --- | --- |
| Predictor or search not accurate enough | Candidates miss the target by more than the tolerance | Flow A: run the paper's own stiffness search at several nearby targets, solve every candidate, keep the closest |
| Target is impossible or out of range | No candidate within tolerance | Show the closest five with their errors; the form warns when a target is outside the trained range |
| GPU problem on demo day (driver, memory) | Search is slow or crashes | Pre-run demo targets stored in the cache; CPU mode (slower); recorded backup video |
| Solver is linear (first yield, Euler buckling) | Real parts could fail differently | Label values "solver estimate"; optional nonlinear spot check on a few lattices; say so in the pitch |
| Contract changes late | Frontend and backend stop matching | Freeze at the end of the first phase; changes go through a pull request that also updates `schemas.py` |
| STL not printable | Struts too thin or the lattice disconnected | Minimum-diameter warning; open an STL in a slicer by the end of the first phase, not on the last day |
| Different laptops, different Python packages | "Works on my machine" | Pinned `requirements.txt` and `package-lock.json`; one machine is the demo server |
| Venue Wi-Fi unreliable | Tunnel link fails | Run everything on localhost on the demo laptop; the tunnel is only for sharing |
| Integration left to the last day | Bugs found with no time to fix | Three gates (see timeline) and a mock server so each part is testable alone |

## Definition of done and demo script

We are done when a stranger can type a target, get solver-verified designs, look at one in 3D and download a printable file, and we can show evidence that the search works.

**Done checklist**

- [ ] The form returns five ranked designs for a target, each with a solver-verified result
- [ ] At least three demo targets land within the tolerance
- [ ] The 3D viewer shows any candidate, tiled from 1 to 5 per side
- [ ] A downloaded STL opens in a slicer and slices cleanly
- [ ] Round-trip result on a slide: targets taken from solver values of lattices the model never saw, and the share of them the search recovers
- [ ] Comparison on a slide: our search against random starts and against the paper's own search
- [ ] Backups ready: stored demo results and a recorded video
- [ ] One command starts everything, and the README says how

**Demo script (about 5 minutes)**

1. State the problem in one sentence: designing a lattice for a given stiffness, strength and weight is slow trial and error.
2. Load the example target in the form and press Design.
3. Narrate the progress stages as they move: the AI proposes, the solver checks.
4. On the results screen, point at predicted against verified numbers and the match error.
5. Open the best design, rotate it, and change the tile count.
6. Download the STL and show it in the slicer.
7. Show the evidence slides: the round-trip result and the comparison.
8. Close with what is next: more materials, nonlinear checks and printed samples.
