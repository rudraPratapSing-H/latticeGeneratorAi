# AI-generated lattice design and property prediction

Built for AI Manthan 2.0 (Problem Statement 10). Give a target stiffness (x, y, z), strength and relative density
and get back lattice designs ranked by how well a physics solver confirms them.

Built on the VAE and lattice dataset of *Unifying the design space of truss metamaterials* (Zheng et al.,
https://github.com/li-zhengz/UnifyingTrussDesignSpace, MIT licence). See `CITATION.cff`.

## How it works

1. **Encoder** turns a lattice (405 numbers: 378 adjacency + 27 node offsets) into a 48-number code.
2. **Predictor** (`train_predictor.py`, `q1.pt`) maps code + density to stiffness, yield and buckling strength.
3. **Search** (`search_design.py`) scores 300k stored codes, keeps the K best, nudges them by gradient descent so the
   predicted properties move toward the target, then decodes them into lattices.
4. **Solver** (`strength-labels/lattice_strength.py`) computes the real stiffness and strength of every decoded lattice.
   Only designs the solver confirms within 10% are marked as matches. If nothing matches, K grows (100, 300, 1000).

## Results

- Predictor on 200,000 lattices it never trained on: stiffness R2 about 99%, median error 3 to 8%;
  yield error about 9%, buckling about 12%.
- Search on 10 requests taken from lattices outside the predictor's training set: 10 of 10 matched
  (9 in the first round, 10 to 15 s each).

## Setup (for teammates)

```
git lfs install
git clone https://github.com/YOUR-USERNAME/lattice-design-ai.git
cd lattice-design-ai
pip install -r requirements.txt
```
The large model files (autoencoder weights, stored codes) are stored with Git LFS and download during the clone
(about 80 MB). If a file looks like a short text pointer, run `git lfs pull`.
The solver label files used only for tests (`labels_100k_x3.csv`, `labels_300k_x3.csv`) are on the Releases page;
put them in `strength-labels/`. A normal search does not need them.

## Run a search

```
python search_design.py --predictor q1.pt --codes encoded_codes.npz ^
  --E-gpa 114 --yield-mpa 880 --density-g-cc 4.43 ^
  --stiffness 2.0 1.7 2.2 --strength 13 12 13 --rel-density 0.25
```
Results are printed and written to `search_results.json`.

## Tests (need the label files)

```
python search_design.py --predictor q1.pt --labels strength-labels/labels_300k_x3.csv --codes encoded_codes.npz ^
  --E-gpa 114 --yield-mpa 880 --density-g-cc 4.43 --from-test-lattice 0 ^
  --unseen-from strength-labels/labels_100k_x3.csv
python eval_unseen.py --predictor q1.pt --codes encoded_codes.npz ^
  --trained-labels strength-labels/labels_100k_x3.csv --labels strength-labels/labels_300k_x3.csv
```

## Backend (FastAPI)

`server/` is the API from `docs/BUILD_PLAN.md`; `core/engine.py` is the only code that imports torch and `search_design.py`.

**Start it (PowerShell, from the repo root)**

```
python scripts/check_env.py          # Python 3.11, numpy<2, torch + CUDA, every model file OK / missing / Git LFS pointer
.\scripts\dev.ps1                    # real models (GPU laptop, about 20 s to load), API on http://127.0.0.1:8000
.\scripts\dev.ps1 -Mock              # no GPU: replays stored real runs (mock/) and the stored demo targets (demo/)
```
`dev.ps1` also starts the web app (the `web/` or `lattice-web/` folder), and waits until the API reports `model_loaded` first. Do not use `uvicorn --reload` with the real backend: it breaks
the solver process pool on Windows. Interactive docs: `/docs`. Try requests in Bruno: open the `bruno/` folder.

**Demo steps (no GPU needed)**: `.\scripts\dev.ps1 -Mock`, then send one of `bruno/dataset/D1`-`D5` (Bruno, or the web form once
`web/` exists). The five demo targets in `demo/` (real solver-verified results of `bruno/dataset_requests.json` D1-D5) are
answered from the store, instantly.
With the GPU, the same requests are answered from the store when the model files are unchanged, and any other target is searched.

**What a request does**: `POST /api/designs` checks the material, plausibility (stiffness above E_s is a unit mistake), the
weight limit and the dataset picker (`core/reach.py`) first. An infeasible target is a 422 with the bound and the nearest
achievable target unless `force: true`. An identical earlier request (canonical JSON + model-file hash) returns the stored job.
Otherwise the job waits in a queue (one search at a time, 429 when the queue is full) and runs adaptive rounds of
K = 100, 300, 1000 starting lattices; it stops on a match, when a round gains under half a point, at `TIME_BUDGET_S`
(default 120 s) or on `POST /api/jobs/{id}/cancel`. Each round solver-verifies the start, an early snapshot and the steered end
point of every candidate and merges lattices with the same verified behaviour. Mass is density x part volume x material
density (an estimate). Every response goes through `sanitize()`: no NaN, Infinity or NumPy types.

**Endpoints**: `GET /api/health`, `/api/materials`, `/api/limits`, `POST /api/reach`, `POST /api/designs`,
`GET /api/jobs/{id}`, `GET /api/jobs/{id}/events` (SSE with pings), `POST /api/jobs/{id}/cancel` (or `DELETE`), `GET /api/designs/{id}`.
Errors are `{"error": {"code", "message"}}`.

**Env**: `MOCK`, `MODEL_DIR`, `DEVICE`, `PREDICTOR` (default `q1.pt`), `WORKERS`, `TIME_BUDGET_S`, `MAX_QUEUE` (10), `RUNS_DIR`,
`SSE_PING_S` (15), `MOCK_STAGE_DELAY` (0.3 s per stage in mock mode).

**Rebuilding generated files** (each needs the real files, see the script docstrings)

```
python scripts/build_reach_table.py C:\path\to\strength-labels\labels_300k_x3.csv   # core/tables/reach_table.npz (Git LFS)
python scripts/build_demo.py --count 5                                                  # demo/ (GPU laptop)
python scripts/make_mock.py                                                             # mock/ from sample_*.json
```

## Implant workflow (design demo, not a medical device)

`POST /api/implants` (STL + description) -> `/confirm` (units, axis) -> `GET/PUT /zones` -> `POST /search` (one design job per lattice
zone) -> `GET /zones/{z}/candidates` -> `POST /assemble` (queued job: tile, assemble, check, export) -> `GET /result`,
`/export.stl`, `/report`. `POST /parse` reads a description again. The load model, bone targets and safety factor are placeholders
(`core/profiles/implant.py`, every number `source: TODO`); nothing here is a clinical or regulatory claim. Every number in a result
is labelled: `solver_verified_infinite_lattice` (the chosen cell, from the periodic beam solver), `beam_model_estimate` (finite
block, `core/check.py`), `geometry_only` (mass, counts), `not_modelled` (plates, skin).
Description parsing uses Gemini when `GEMINI_API_KEY` is set in the environment (`GEMINI_MODEL` picks the model; the key is sent
in a header, never logged or stored) and falls back to offline rules on any failure. Run one full case on the real solver:
`python scripts/run_implant_case.py`; check an exported STL: `python scripts/validate_implant_stl.py <file.stl>`.
The web types come from the OpenAPI file: `npm run gen:api` in `lattice-web/`. `VITE_ENABLE_IMPLANT=false` removes the implant UI.

## API tests

Needs Python 3.11. `pytest -q` runs the suite against the mock core (no GPU, about a minute). `pytest -q -m gpu` runs the checks
that need the models: the engine on the `sample_3` request, the picker test on 10 unseen lattices (needs the label files; set
`LABELS_DIR` if they are not in `../strength-labels`), and a real server answering a job over HTTP.
