# LatticeViewer — Interface Agreement

**Owner:** Teammate C

## Contract

The frontend always imports `LatticeViewer` through:

```tsx
const LatticeViewer = React.lazy(() => import('@/components/LatticeViewer'))
```

This keeps `three.js` out of the main bundle until the viewer is needed.

## Props

See `types.ts` for the full `LatticeViewerProps` interface.

- **`lattice`**: The exact API contract shape (`octant27` format): 27 nodes in [0,1]³ plus edge list.
- **`tiles`**: Number of cells per side (1–5), default 1.
- **`variant`**: `'thumbnail'` (non-interactive, cheap, many mount at once) or `'full'` (orbit, zoom).
- **`renderMode`**: `'solid'` (default) or `'wireframe'`.
- **`colorByAxis`**: When true, colour struts by dominant axis direction (x=rose, y=green, z=blue).
- **`className`**: The parent sizes the container; the viewer fills 100% width/height.
- **`onError`**: Callback to report WebGL context loss (`webglcontextlost`) or rendering failure.

## Implementation Guidelines for Teammate C

1. **Cell Rebuilding**: Rebuild the full cell [-1,1]³ by mirroring about x=0, y=0, z=0. Merge identical struts. Tile by shifting 2 units per axis. The cell spans 2 units = `cell_size_mm`. Face struts appear on both faces for drawing.
2. **Strut Radius**: `strut_radius_mm` is already in millimeters.
3. **Thumbnail Performance**: Thumbnails must be cheap since many mount simultaneously in the results grid. Avoid one heavy WebGL context per card (e.g. use lightweight canvas/SVG or shared renderer).
4. **WebGL Context Loss**: Handle `webglcontextlost` events and trigger the `onError` prop so the UI can gracefully fallback to the placeholder.
5. **Coordinate System**: STL export is Z-up while three.js is Y-up (rotate once, on export only).
