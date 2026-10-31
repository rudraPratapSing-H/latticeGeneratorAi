# Review of Phase A against docs/BUILD_PLAN.md

Everything below was run on 2026-10-31 on the RTX 3050 laptop unless it says otherwise. "Test" names are in `tests/` (backend)
or `lattice-web/src/` (frontend). Screenshots (real backend, real models) are in this folder.

Status words: **pass** = already correct and covered, **fixed** = was wrong or missing, fixed in this review, **gap** = still open.

## Re-runs

| Command | Result |
|---|---|
| `pytest -q` | 197 passed, 2 skipped, 7 deselected (the 2 skipped need the frontend, which is untracked) |
| `pytest -q -m gpu` | 7 passed in 4 of 5 final runs (engine on `sample_3`, picker on 10 unseen lattices, real server over HTTP, dev.ps1 real mode, stored-lattice fallback, clean exit). **One run failed `test_real_job_over_http`**; I did not capture the message and could not reproduce it in 4 repeats. It is the test that asserts health under 100 ms, so treat the health figure below as "usually", not "always" |
| Fresh `git clone` + `scripts/check_env.py` + `pytest -q` | every line `[OK]`; 195 passed, 4 skipped (the frontend is untracked, see questions) |
| `npm ci` / `typecheck` / `lint` / `test:run` / `build` | all pass; lint 0 errors, **13 warnings** (12 `react-refresh/only-export-components`, 1 `react-hooks/incompatible-library` for react-hook-form's `watch()`); 145 tests; build 1.3 s, one chunk (`LatticeViewer`, 943 kB) above 500 kB |

## Task list (Done when)

| T | Done when | Status | Proof |
|---|---|---|---|
| T0 | check_env reports versions and each file OK / missing / pointer | pass | `test_check_env.py` (fake pointer file), fresh-clone run |
| T1 | `Engine.run` returns the `--out` structure; sample_3 matches in round 1 under 10% | pass | `test_engine.py::test_gpu_sample3_request_matches_in_round_one` |
| T2 | round trips, ratio 129.5, rejects strength+yield, mass+density, all-null | pass | `test_t2_units.py` |
| T3 | seven picker tests; table builds in under a minute | pass (test 2 differs from the plan, see below) | `test_reach.py` (14), 19.5 s build, GPU test 7 |
| T4 | MOCK serves health, materials, limits, reach, a four-stage job with real candidates; mock files validate | pass | `test_mock_files.py` |
| T5 | one job at a time, queue position, heartbeat, cancel, restart, health under 100 ms | pass | `test_runner.py`; real-server latency below |
| T6 | picker first, then engine, then warnings; cache; `allow_nan=False` | pass | `test_pipeline.py` |
| T7 | types generated from `openapi.json`; routing and job id in the URL after refresh | **gap** (types) / pass (routing) | refresh of `/job/j_...` verified in the browser (05); generation needs a new npm dev dependency, see questions. `openapi.json` is exported to `lattice-web/src/test/fixtures/backend/` and a contract test pins the shapes instead |
| T8 | hints as the user types; Accept applies only when clicked | **fixed** / pass | form had no default material so hints never ran when typing (fixed: `DesignPage.test.tsx`); badge verified live (09); Accept leaves numbers "Requested" until clicked (02) |
| T9 | stage bar from events with polling fallback; "closest, not a match" and the shortfall | pass, one **fixed** | verified live (04, 05, 10); cancelled jobs were polled forever (fixed, `cancel.test.ts`); no Cancel button existed (fixed) |
| T10 | periodic-density test on the seven samples; seamless tiling 1-5; STL that opens | **fixed** | `lib/stl.ts` was a stub that threw ("being finished by the viewer module"). Now `stl.test.ts`: periodic density within 0.1% on all 35 candidates, tiling 1-5, closed outward-oriented shells; the file downloaded through the UI validates with `scripts/validate_stl.py`. Not opened in a real slicer (none installed here) |
| T11 | five stored targets; one command starts server and web; README; video | pass / **fixed** / user | `test_demo.py`, `test_dev_script.py` (dev.ps1 now starts both and waits for `model_loaded`); the video is yours, click path in `docs/DEMO.md` |

## Failure cases (single-part product)

| Case | Status | Proof |
|---|---|---|
| No target / zero, negative, NaN, text | pass | `test_hardening.py`, `test_t2_units.py` |
| Above the material (unit mistake) with a hint | pass | `test_pipeline.py::test_value_above_the_material_is_422_with_unit_hint`, Bruno E14 |
| Infeasible -> 422 with bound; `force: true` runs | pass | `test_pipeline.py::test_infeasible_target...`, live (02-05) |
| Far from the data -> run with a warning and the nearest target | pass | picker `outside` warning in `preflight.py`, `test_reach_api.py` |
| Stiff but weak: name the conflicting value | **fixed** | `test_review_gaps.py::test_reach_names_the_conflicting_value...` (`conflict` in `/api/reach`) |
| Mass limit below 0.05 -> 422 with the lightest mass; above 0.25 -> use 0.25 and say so | pass | `test_pipeline.py` (two tests) |
| Cell larger than the part / not a whole number of cells | pass | `test_hardening.py`, `test_pipeline.py::test_part_that_is_not_a_whole_number...` |
| Different material changes the limits | pass (only Ti-6Al-4V exists in the backend) | `test_reach.py::test_softer_material...` |
| No design in tolerance: closest labelled, shortfall shown | pass | `test_escalation.py` replay of a real miss; frontend shows per-axis shortfall (05) |
| Zero candidates: nearest stored lattices, solver-verified | **fixed** | `test_fallbacks.py` (4 tests) + GPU `test_gpu_far_outside_target_with_empty_search...` |
| Solver NaN / floppy lattice: skip and count | **fixed** | `test_review_gaps.py` (`skipped_invalid`, job warning). The search already dropped non-finite results; the 1.05 x density x E_s check is new |
| Near duplicates | pass | the 1% signature rule inside `search_design.py` |
| GPU out of memory: smaller K, then CPU | **fixed** | `test_fallbacks.py` (retry, CPU move, give up, other errors not retried). Simulated with fakes: a real CUDA OOM was not provoked |
| Last round takes minutes: time budget | pass, with a limit | the budget is checked before each next round using the last round's time; a single running round cannot be interrupted (the first round is always allowed) |
| Cancel | pass | `test_runner.py`; real engine stop between rounds is only unit-tested with a fake search (`test_engine.py`) |
| Restart marks jobs failed with reason | pass | `test_runner.py::test_saved_jobs_survive...` |
| Several users: queue position, 429 | pass | `test_runner.py` |
| Same request again: cache, cleared when a model changes | pass | `test_pipeline.py` (3 tests), live: second POST returned the stored job |
| Model files missing / LFS pointer: reason in health | pass | `test_engine.py`, `test_demo.py::test_health_reports_why...` |
| NumPy 2 / CPU torch | pass | `check_env.py` |
| Windows pool: spawn, no torch in workers | **fixed** | `test_review_gaps.py::test_solver_workers_do_not_import_torch`; pool shutdown error at exit fixed (`test_gpu_interpreter_exit_is_clean...`) |
| Proxy drops the stream: heartbeat 15 s, polling fallback | pass | `test_runner.py::test_event_stream_sends_heartbeat...`, contract test of the SSE transcript; `useJob` polls every 1.5 s |
| Strut too thin: warning with the smallest cell | pass | `test_pipeline.py::test_thin_struts...`, `printability.test.ts` |
| Mass is an estimate | pass | `mass_estimate`, "ESTIMATE" tag in the UI |
| 50 tiles: clamp 1-5 viewer, up to 8 STL with a warning | pass | `geometry.test.ts`, `stl.test.ts` |
| STL too large: warn, 12 -> 8 sides | **fixed** | `stl.test.ts::drops 12 sides to 8...`, toast in `DownloadMenu` |
| WebGL context lost | pass (code), not driven | listener in `LatticeCanvas.tsx`; falls back to the placeholder |
| NaN in a response | pass | `test_pipeline.py::test_api_responses_never_contain_nan_or_numpy` |

## Bug watchlist (19)

1 periodic density **fixed** (`stl.test.ts`, 35 candidates within 0.1%; naive count is 5% to 140% too high) · 2 stiffness is 1/S11 **pass** (`test_reach.py::test_stiffness_is_inverse_normal_block...`) · 3 buckling relative to E **pass** (`test_t2_units.py`) · 4 strength+yield, mass+density **pass** · 5 axis/unit confusion **fixed** for STL (`stl.test.ts::x, y and z are not swapped`; STL is built in solver coordinates, no swap) · 6 float equality on density **pass** (picker uses the nearest index) · 7 search on the event loop **pass** (`test_runner.py`, real measurement below) · 8 NaN/NumPy **pass** · 9 Pydantic 2 **pass** · 10 cache key **pass** · 11 SQLite WAL, connection per call **fixed** (test added) · 12 SSE **pass** · 13 StrictMode double submit **pass** (submit from a handler; `main.tsx` uses StrictMode; one POST per click seen in the browser) · 14 paths and encodings **pass** (pathlib, UTF-8) · 15 contract drift **fixed** in part (contract test against the real backend; generated types need the npm dependency) · 16 seeded GPU tests **pass** · 17-19 implant: not started (Phase B).

## Measured numbers

**`/api/health` during a real search** (`scripts/bench_health.py`, K=300 round, 13 s job, server in its own process):

| | n | min | median | p95 | max |
|---|---|---|---|---|---|
| idle | 10 | 1.4 ms | 15.9 ms | 23.5 ms | 23.5 ms |
| during the search | 30 | 1.2 ms | 1.7 ms | 24.2 ms | 27.0 ms |

The 179 ms seen once earlier was not reproduced in the later real runs (`test_gpu_api.py` about 10 times, the bench, the browser), except that one unexplained GPU-suite failure above. Probable
cause: 16 solver workers at normal priority competing with the server; the workers now run below normal priority and one core
is left free. An A/B run did not show a speed difference between the two settings (median 3.9 s old vs 4.2 s new per round).

**Search time and tuning** (`scripts/bench_search.py`, requests from lattices the predictor never trained on, pool = trained lattices only,
weight "at most" so the density is free, one round of K starts):

| n_grid | K | requests | matched | median s | mean s | max s | worst error |
|---|---|---|---|---|---|---|---|
| 9 (default) | 100 | 10 | 8 | 4.2 | 3.8 | 5.1 | 13.2% |
| 5 | 100 | 10 | 8 | 3.2 | 3.0 | 4.0 | 13.2% |
| 3 | 100 | 10 | 8 | 2.7 | 2.6 | 3.2 | 15.3% |
| 9 | 50 | 10 | 7 | 2.8 | 2.7 | 3.4 | 13.2% |
| 5 | 50 | 10 | 7 | 2.4 | 2.2 | 2.7 | 13.2% |
| 9 | 100 | 40 | **34** | 4.4 | 4.0 | 6.4 | 13.2% |
| 5 | 100 | 40 | **33** | 3.5 | 3.2 | 4.1 | 13.2% |

n_grid 5 saved 20% to 25% but lost one match in 40, and K=50 lost one in 10, so **nothing was changed** (rule: only if the match
rate does not drop). The "30-38 s per job" in the first report was not reproduced: a round takes 3 to 6 s here (the five demo
jobs 6 to 16 s including preflight). The earlier figure was probably contention with other processes on the machine (an
unrelated backend was also holding port 8000); the demo store was rebuilt, so its recorded times are the current ones.
Round-1 match rate on unseen requests is **85%** (34 of 40), not the 90% quoted earlier.

## Plan versus code (where I chose)

* Picker test 2 (x1.5 targets are "about 50% and outside"): false in the interior of the data (73% of 120 sampled rows stayed covered); test pins what holds.
* The plan's own example, 8/8/12 GPa at 60 g, is infeasible (sum 28 GPa > 1.05 x 0.15 x 114 = 17.9 at the densities a 60 g limit allows). It is now a 422, and the demo uses it as the "infeasible" step.
* Dedupe: engine ids hash adjacency and node positions, so ranking dedupes by id + density; the older edge-only rule dropped real designs.
* Unknown material: 422 up front, not a failed job.
* The "nearest achievable target" came from the stored dataset (solver values) but the UI tagged it "Predicted"; now "Stored lattice".
* The frontend mock invented numbers (`generate.ts` "TEMPORARY") and listed three materials the backend rejects; it now replays real backend output.

## What I could not verify

A real CUDA out-of-memory (simulated), a real slicer opening the STL (validated structurally instead), the queued and 429 states in
the browser (covered by the contract fixtures and tests), WebGL context loss, the implant screens (backend does not exist: they
work only against the frontend's mock and are hidden in real mode), the recorded video.
