# Demo guide (one page)

The five stored demo targets are real solver-verified searches (`demo/`, made by `scripts/build_demo.py` on the GPU laptop).
Sending one of them returns the stored job at once, with or without the GPU. Every number on screen is solver-verified.

## Start (PowerShell, repo root)

```
.\scripts\dev.ps1            # real models. Waits for "API ready ... model_loaded: True" (about 20 s), then starts the web app
.\scripts\dev.ps1 -Mock      # no GPU: stored demo targets + replay of stored real runs. Use this as the safe default on stage
```
Web app: http://127.0.0.1:5173 · API docs: http://127.0.0.1:8000/docs · Logs: `runs\dev\`. Ctrl+C stops everything.
Check first: `python scripts/check_env.py` (every line `[OK]`). Port busy? `dev.ps1` says which process holds it.

## The five targets (stiffness x/y/z in GPa, strength x/y/z in MPa; weight limit in g, part 40 mm cube, 10 mm cells)

| # | Target | Stiffness | Strength | Max mass | Best design: density | mass | error | meet all targets | Search time (round 1) |
|---|--------|-----------|----------|----------|------|------|-------|------|------|
| D1 | light, nearly isotropic | 0.328/0.351/0.335 | 3.83/3.07/3.45 | 14.5 | 0.050 | 14.2 g | 2.53% | 5 of 5 | 14 s |
| D2 | medium, nearly isotropic | 1.15/1.24/1.24 | 8.1/8.81/8.23 | 43.4 | 0.151 | 42.8 g | 0.56% | 5 of 5 | 6 s |
| D3 | dense, nearly isotropic | 1.9/2.38/2.42 | 12.5/15.8/13.4 | 72.3 | 0.246 | 69.7 g | 0.84% | 5 of 5 | 14 s |
| D4 | medium, much stiffer in z | 0.578/0.595/1.64 | 3.41/2.31/11.5 | 43.4 | 0.100 | 28.3 g | 5.12% | 2 of 5 | 16 s |
| D5 | medium, much stiffer in x | 1.62/0.306/0.509 | 7.51/2.06/2.93 | 43.4 | 0.150 | 42.5 g | 0.79% | 5 of 5 | 12 s |

Modes everywhere: stiffness **about** (±10%), strength **at least**, weight **at most**. The search times are what the
live search needed on the RTX 3050 laptop; the stored result appears instantly. A new target of your own takes about
4 to 6 s per search round (median 4.4 s over 40 unseen targets, benchmark `scripts/bench_search.py`) and up to three rounds
if it does not match at once. Mass is an estimate (density x volume x material density).

The same requests are in Bruno (`bruno/dataset/D1`-`D5`) and in `bruno/dataset_requests.json`.

## Click path for the recorded video (about 3 minutes)

1. Open the app. Point at the **Online** pill (top right) and the footer: "AI proposes, the solver verifies."
2. Material is Ti-6Al-4V. Open **Stiffness targets**: type D2's numbers (1.15 / 1.24 / 1.24 GPa), strength 8.1 / 8.81 / 8.23 MPa,
   max mass 43.4 g. Watch the **Dataset reach** badge turn *Covered* while you type: "a stored lattice is within 10%".
3. Press **Design**. The run page shows the four stages (Search, Repair, Verify, Rank); say what each does.
4. Results: five cards, ranked. Open the table: **target / predicted / verified** side by side and the match error. Point out that
   the numbers tagged *Verified* come from the physics solver, not the AI.
5. Open the best design. Rotate it, change **Tiles** 1 to 5, switch Solid / Wire, tick **Colour by axis**.
6. **Download > STL**. Open it in your slicer (strut diameter is checked against a 0.4 mm nozzle).
7. Show the infeasible case: type stiffness 8 / 8 / 12 GPa with 60 g (the plan's example). The badge says *Infeasible*
   (stiffnesses add up to more than density x E_s), the app offers **Accept nearest** and **Run anyway**. Accept nearest keeps your
   numbers until you click; Run anyway sends `force: true` and returns the closest designs, labelled "Closest, not a match".
8. Close: more materials, nonlinear checks, printed samples. The implant workflow below is a second, optional demo.

## Implant demo path (optional, about 2 minutes, real backend)

A design demo, not a medical device: bone and load numbers are placeholders (`source: TODO` in `core/profiles/implant.py`).
Needs the real backend (`.\scripts\dev.ps1`); in `-WebMock` mode the web app replays the recorded run (`mock/implant/`) instead.

1. Open **Implant**. Upload `docs/review/test_stem.stl` (a generated 160 mm stem; `python scripts/make_test_stem.py` makes more).
   Type: *Right femoral hip stem for a 45 kg sedentary patient. Keep the neck solid.* Press **Upload & Analyze Mesh**.
2. The mesh report says: closed, 1 body, 59 x 30 x 160 mm, units mm. The fields (45 kg, sedentary, "keep the neck solid") are read
   from the text: by Gemini when `GEMINI_API_KEY` is set (model: `GEMINI_MODEL`), otherwise by simple rules. Press **Confirm**.
3. Zones: tip, mid stem 1, mid stem 2, neck. Three are solid with the reason ("needs 169 MPa, above the most any lattice reaches,
   76.1 MPa"); mid stem 2 is lattice (stress 41 MPa, 5.5 mm cell, covered by the dataset). Open *Load used for the design stress*:
   every assumption names its source.
4. **Search lattices for all zones**: one ordinary design job per lattice zone. Pick candidate #1, press **Assemble Implant**.
5. Result: 4 zones, 393 g, 73,588 triangles, 3.7 MB STL. Each number carries a label: *Solver-verified (infinite lattice)* for the
   chosen cell, *Beam-model estimate* for the finite block (12.4 GPa, 124% of the infinite lattice), *Geometry only* for mass.
   **Download STL** and **Download report**. Check the STL: `python scripts/validate_implant_stl.py runs/implants/<id>/assemblies/<job>/implant.stl`
   (expected: `"ok": true`, 2112 closed shells).

Timings on the RTX 3050 6 GB laptop (first, cold run): upload and parse 0.7 s, confirm and zone table 1.4 s, zone search 20.4 s
(one lattice zone), assembly with check and STL 1.1 s, download 0.05 s. A second identical run answers the search from the cache.
With only a CPU the search takes minutes per zone; use `-Mock`/`-WebMock` and say the screens replay a recorded run.

## If the GPU misbehaves

* **Models not loaded / out of memory**: `/api/health` shows the reason (`reason` field). The engine retries once with half the
  starts, then moves to the CPU (slower, health shows `gpu: false`). Nothing to do.
* **Still failing**: close everything and run `.\scripts\dev.ps1 -Mock`. The five targets above answer from the store; other
  targets replay the nearest stored real run (the message says so).
* **Last resort**: the recorded video, and Bruno (`bruno/`) against `-Mock`.
* Port already used (an old server on :8000): `dev.ps1` refuses to start and names the process; use `-Port 8001`.

## What not to claim

Strength is static (no fatigue). The solver is a linear beam model (first yield, Euler buckling); label it "solver estimate".
The AI proposes; only designs the solver confirms count as matches. Round-1 match rate on unseen requests is 85% (34 of 40),
not 100%. Printing and mechanical tests are needed before any real use.
