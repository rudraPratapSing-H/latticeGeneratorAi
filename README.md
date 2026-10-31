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

`server/` serves the API in the build plan; `core/` connects it to `search_design.py` (set `MOCK=1` for canned results).

```
uvicorn server.app:app --host 0.0.0.0 --port 8000      # real models, loaded at startup (~17 s)
MOCK=1 uvicorn server.app:app --port 8000               # canned results, no GPU needed
pytest                                                   # runs against the mock core
```
A job runs adaptive rounds of K = 100, 300, 1000 starting lattices and stops as soon as the solver confirms a design
matching every target (escalation also stops after `TIME_BUDGET_S`, default 120 s). Each round verifies the unsteered
start, the early snapshot and the steered end point of every candidate and merges lattices with the same verified behaviour.
Env: `MOCK`, `MODEL_DIR`, `DEVICE`, `PREDICTOR` (default `q1.pt`), `WORKERS`, `TIME_BUDGET_S`.

## API tests

Needs Python 3.11+. `pytest` runs the 44 tests against the canned core (no GPU). To try the API by hand, open the `bruno/` folder as a collection in Bruno (see `bruno/README.md`).
