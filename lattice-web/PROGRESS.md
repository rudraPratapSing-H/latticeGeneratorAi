# Lattice Designer — Progress

## Overall Status
- **Project State:** (b) Earlier generated app refactored & updated strictly to brief specification.
- **Single-Request Product (Phase A):** Complete & verified.
- **Implant Workflow (Phase B):** Complete & verified.
- **Typecheck:** ✅ Passes cleanly (`tsc -b --noEmit` -> 0 errors)
- **Lint:** ✅ Passes cleanly (`eslint .` -> 0 errors, 13 non-blocking compiler/refresh warnings)
- **Vitest:** ✅ 87 tests passing across 17 test suites (100% pass rate)
- **3D Lattice Viewer:** ✅ Full 3D interactive WebGL viewer with OrbitControls, continuous auto-rotate motion toggle, 1–5 tile lattice replication, and solid/wireframe rendering.
- **Production Build:** ✅ Passes cleanly (`tsc -b && vite build` in 2.07s)

---

## Phase 0: Audit and Config
- [x] Read all source files, package.json, configs
- [x] Determined state (b)
- [x] Dependencies verified (lockfile clean, typescript ~5.9.3)
- [x] Verified `../mock/` does not exist
- [x] Env files updated (`.env`, `.env.example`, `.env.production` with `VITE_ENABLE_IMPLANT=true`)
- [x] Created `web/scripts/sync-mocks.mjs` and added `sync:mocks` script to package.json
- [x] Fixed `src/vite-env.d.ts`

## Phase 1: Types, Schemas, API Client, Events, Mock Layer
- [x] `api/types.ts`: complete with `matches_targets`, `ReachLevel`, `ReachResponse`, `RoundInfo`, `force`, `cancelled`, optional `governing_failure`
- [x] `api/schemas.ts`: matching all types, `.passthrough()`, dev error / prod warn
- [x] `api/implantTypes.ts`: provisional types created
- [x] `api/endpoints.ts`: added `getLimits`, `checkReach`
- [x] `api/queryKeys.ts`: keys for health, materials, limits, reach, job, design, implant, etc.
- [x] `api/client.ts`: normalised error handling (`ApiError`), mock adapter pre-loaded synchronously
- [x] `config/env.ts`: `API_BASE`, `USE_MOCK`, `ENABLE_IMPLANT`
- [x] `config/constants.ts`: `AXES`, `STAGES`, `DATASET_DENSITIES`, `AT_LEAST_STRENGTH_SLACK`, `MAX_VIEWER_TILES`, `MAX_STL_TILES`
- [x] `config/limits.ts`: reference Ti-6Al-4V tables, material scaling, `extractLimits`
- [x] `mocks/adapter.ts`: `/api/health`, `/api/materials`, `/api/limits`, `/api/reach`, `/api/designs`, `/api/jobs/:id`, `/api/designs/:id`, all 12 scenarios
- [x] `mocks/jobSim.ts`: rounds progression, multi_round, slow, queued_long, restart_fail, cancelled, fail, success
- [x] `mocks/generate.ts`: deterministic generator, `matches_targets`, predicted without `governing_failure`
- [x] `components/ui/source-tag.tsx`: Requested, Adjusted, Predicted, Verified, Estimate, Automatic
- [x] `hooks/useLimits.ts`, `hooks/useReach.ts`

## Phase 2: UI Primitives, App Shell, Router
- [x] Design system verified (tokens in index.css, dark mode default, no flash)
- [x] `BackendStatusPill`: Online / Degraded / Offline / Mock data
- [x] `Header`: Single design, Implant (beta) (gated by `ENABLE_IMPLANT`), theme toggle, mobile dropdown
- [x] `Footer`: "AI Manthan 2.0 · Problem Statement 10" and "AI proposes, the solver verifies."

## Phase 3: Design Form + Reach UI
- [x] `ReachBadge`: Covered, Extended, Outside, Infeasible with explanations
- [x] `ClosestAchievable`: Shows nearest vs requested with Accept / Undo, marks Adjusted fields
- [x] `DesignForm`:
  - `useReach` debounced (400ms)
  - `createFormSchema(materials)` validation: stiffness > E_s error with GPa/MPa hint, strength > yield error
  - Mass implying ρ < 0.05 amber warning; ρ > 0.25 amber warning
  - Non-dataset density warning under Advanced
  - Infeasible targets offer "Run anyway" dialog submitting with `force: true`
  - Scroll & focus first error on submit
  - Saves request with `metadata: { adjustedFields }`

## Phase 4: Progress (Job Page while running)
- [x] `StageStepper`: Search → Repair → Verify ("Solver-verified" badge) → Rank
- [x] Monotonic progress combining events and polling
- [x] `RoundsTimeline`: table showing rounds, K, best error %, matched status, time
- [x] Cancelled & failed states, queue position indicator

## Phase 5: Results
- [x] `ResultsBanner`: solver verification counts, shortfall breakdown for rank #1, strength estimate disclaimer
- [x] Filter "Only designs meeting all targets" based strictly on server's `matches_targets`
- [x] `CandidateCard`: rank badge, ribbon only if `matches_targets`, "Closest, not a match" badge, governing failure on verified, mass (Estimate)
- [x] `ComparisonMatrix`: status, error, mass, ρ, inline bars with target markers, highlighted best values

## Phase 6: Detail
- [x] `PropertyTable`: grouped rows, sub-rows yield/buckling, governing failure only on verified, surrogate accuracy footer (median and max error)
- [x] `PrintabilityNotice`: uses `checkPrintability` (tested worked example)
- [x] `DownloadMenu`: STL download with loading state, design JSON, copy ID
- [x] `MetricGrid`: with Nodes/Edges count and mass (Estimate)

## Phase 7: 3D Viewer & STL Export
- [x] `LatticeViewer`: Full interactive 3D WebGL Canvas (`@react-three/fiber` + `@react-three/drei` + Three.js) with OrbitControls (drag to rotate, scroll to zoom, pan)
- [x] 3D Motion: Continuous auto-rotation motion with play/pause toggle in the 3D viewport
- [x] Multi-Cell Tiling: Rebuilds full $[-1, 1]^3$ unit cell from octant and replicates seamlessly from 1 to 5 tiles with automatic camera re-centering
- [x] Dual Render Modes: 3D metallic volumetric cylinders + spherical node joints (solid) & glowing wireframe
- [x] Colour by Axis: Dominant axis highlighting (X=rose, Y=emerald, Z=cyan)
- [x] Graceful Fallback: Seamless fallback to `LatticePlaceholder` in headless/test environments or on WebGL error
- [x] `src/lib/stl.ts`: STUB with ownership header

## Phase 8: Phase A Tests and Verification
- [x] Unit and integration tests for single-request product
- [x] Typecheck clean
- [x] Lint clean

## Phase 9: Phase B Implant Workflow
- [x] `lib/meshStore.ts` (IndexedDB for raw user STLs, zero runtime dependencies)
- [x] `lib/meshTransform.ts` (Pure geometry transform: units, long axis, flip)
- [x] `mocks/stemProfile.ts` (Procedural curved femoral stem geometry)
- [x] `mocks/implantMock.ts` (Implant pipeline simulation with zones and assembly)
- [x] `hooks/useImplant.ts` (Full mutation and query hooks for implant lifecycle)
- [x] `features/implant/ImplantBanner.tsx` (Clinical disclaimer & research prototype warning)
- [x] `features/implant/ZoneStrip.tsx` (Interactive 1D schematic, draggable sliders, keyboard arrow keys)
- [x] `features/implant/ZoneTable.tsx` (Zone properties, snapped targets, jump warnings > 3×, kind selector)
- [x] `features/implant/StiffnessProfile.tsx` (Hand-rolled SVG profile chart, vertical zone guides, accessible table)
- [x] Step 1: `/implant` Upload & describe + confirm card (`UploadStep.tsx`, `ConfirmStep.tsx`, `ImplantPage.tsx`)
- [x] Step 2: `/implant/:id/zones` Zone editor (`ImplantZonesPage.tsx`)
- [x] Step 3: `/implant/:id/results` Zone candidates & per-zone progress (`ImplantResultsPage.tsx`)
- [x] Step 4: `/implant/:id/result` Assembled implant & Continuous Stiffness Profile (`ImplantFinalPage.tsx`)
- [x] Registered routes in router, gated by `ENABLE_IMPLANT`
- [x] Unit & integration tests in `ImplantWorkflow.test.tsx`
