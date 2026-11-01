# Lattice Designer: web app

React + TypeScript + Vite + react-three-fiber. Talks to the FastAPI backend in the repo root (`server/`).

## Run it

From the repo root (starts the API, waits for it to be ready, then starts this app):

```
.\scripts\dev.ps1            # real models, GPU laptop
.\scripts\dev.ps1 -Mock      # no GPU: the API replays stored real runs and the five stored demo targets
```

By hand: `npm ci`, then `npm run dev` (real backend at `VITE_API_URL`, default `http://localhost:8000`) or
`npm run dev:mock` (no backend: the app replays stored real backend output in the browser).

**Real mode is the default** (`.env`: `VITE_USE_MOCK=false`). The implant tab is hidden in real mode
(`VITE_ENABLE_IMPLANT=false`) because the implant backend does not exist yet; it only works in `dev:mock`.

## Checks

```
npm run typecheck   # tsc -b --noEmit
npm run lint        # eslint (13 warnings: react-refresh exports and React Compiler on react-hook-form's watch())
npm run test:run    # vitest, mock layer
npm run build
```

## Contract with the backend

The backend's real responses are exported by `python scripts/export_contract_fixtures.py` (run from the repo root) into
`src/test/fixtures/backend/` and `src/mocks/fixtures/real/`. `src/api/contract.test.ts` feeds every one of them, plus
`demo/` and `mock/` from the repo root, through the zod schemas in `src/api/schemas.ts`. Mock mode replays the files in
`src/mocks/fixtures/real/`: never edit them by hand, regenerate them. Regenerate after any backend schema change.

Known shape rules (the backend sends `null` for "not set"; the schemas turn it into `undefined`):
`stage`, `round`, `k`, `queue_position`, `reach`, `request`, `rounds[].best_error_pct`, `message`, `matches_targets`.

## 3D on the results page

Every ranked candidate is shown rotating in its card. The cards share ONE WebGL renderer (`src/components/LatticeViewer/thumbRenderer.ts`)
that draws each visible design and copies the frame into the card's own canvas, so a page with 20 designs never hits the browser's
WebGL-context limit; designs that are off screen, or a hidden tab, cost nothing. Hover or focus speeds the rotation up. With
`prefers-reduced-motion` the part is drawn once and does not move. Opening a card gives the full orbit / zoom viewer.

## Layout

`src/api` client, schemas, events (SSE with polling fallback) · `src/features` design form, job, results, detail ·
`src/components/LatticeViewer` 3D viewer and tiling · `src/lib/stl.ts` binary STL export (periodic merge, clipped to the block,
8/12-sided struts, solver radius exactly) · `src/mocks` mock layer.

Validate an exported STL: `python scripts/validate_stl.py design.stl --expect-size-mm 40 40 40 --size-tol-mm 3.5`
(from the repo root).
