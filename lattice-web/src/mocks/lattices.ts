/** 27-node grid: {0, 0.5, 1}^3 */
export const GRID_27: number[][] = []

// Generate the 27 nodes programmatically
for (let z = 0; z <= 2; z++) {
  for (let y = 0; y <= 2; y++) {
    for (let x = 0; x <= 2; x++) {
      GRID_27.push([x * 0.5, y * 0.5, z * 0.5])
    }
  }
}

/** Helper: index in the 3×3×3 grid for (ix, iy, iz) each 0..2 */
function idx(ix: number, iy: number, iz: number): number {
  return iz * 9 + iy * 3 + ix
}

/** Simple cubic: edges along axes only (12 edges per layer × 3 layers + vertical) */
const SIMPLE_CUBIC: number[][] = [
  // bottom face (z=0)
  [idx(0, 0, 0), idx(1, 0, 0)],
  [idx(1, 0, 0), idx(2, 0, 0)],
  [idx(0, 1, 0), idx(1, 1, 0)],
  [idx(1, 1, 0), idx(2, 1, 0)],
  [idx(0, 2, 0), idx(1, 2, 0)],
  [idx(1, 2, 0), idx(2, 2, 0)],
  [idx(0, 0, 0), idx(0, 1, 0)],
  [idx(0, 1, 0), idx(0, 2, 0)],
  [idx(1, 0, 0), idx(1, 1, 0)],
  [idx(1, 1, 0), idx(1, 2, 0)],
  [idx(2, 0, 0), idx(2, 1, 0)],
  [idx(2, 1, 0), idx(2, 2, 0)],
  // middle face (z=1)
  [idx(0, 0, 1), idx(1, 0, 1)],
  [idx(1, 0, 1), idx(2, 0, 1)],
  [idx(0, 1, 1), idx(1, 1, 1)],
  [idx(1, 1, 1), idx(2, 1, 1)],
  [idx(0, 2, 1), idx(1, 2, 1)],
  [idx(1, 2, 1), idx(2, 2, 1)],
  [idx(0, 0, 1), idx(0, 1, 1)],
  [idx(0, 1, 1), idx(0, 2, 1)],
  [idx(1, 0, 1), idx(1, 1, 1)],
  [idx(1, 1, 1), idx(1, 2, 1)],
  [idx(2, 0, 1), idx(2, 1, 1)],
  [idx(2, 1, 1), idx(2, 2, 1)],
  // top face (z=2)
  [idx(0, 0, 2), idx(1, 0, 2)],
  [idx(1, 0, 2), idx(2, 0, 2)],
  [idx(0, 1, 2), idx(1, 1, 2)],
  [idx(1, 1, 2), idx(2, 1, 2)],
  [idx(0, 2, 2), idx(1, 2, 2)],
  [idx(1, 2, 2), idx(2, 2, 2)],
  [idx(0, 0, 2), idx(0, 1, 2)],
  [idx(0, 1, 2), idx(0, 2, 2)],
  [idx(1, 0, 2), idx(1, 1, 2)],
  [idx(1, 1, 2), idx(1, 2, 2)],
  [idx(2, 0, 2), idx(2, 1, 2)],
  [idx(2, 1, 2), idx(2, 2, 2)],
  // verticals
  [idx(0, 0, 0), idx(0, 0, 1)],
  [idx(0, 0, 1), idx(0, 0, 2)],
  [idx(1, 0, 0), idx(1, 0, 1)],
  [idx(1, 0, 1), idx(1, 0, 2)],
  [idx(2, 0, 0), idx(2, 0, 1)],
  [idx(2, 0, 1), idx(2, 0, 2)],
  [idx(0, 1, 0), idx(0, 1, 1)],
  [idx(0, 1, 1), idx(0, 1, 2)],
  [idx(1, 1, 0), idx(1, 1, 1)],
  [idx(1, 1, 1), idx(1, 1, 2)],
  [idx(2, 1, 0), idx(2, 1, 1)],
  [idx(2, 1, 1), idx(2, 1, 2)],
  [idx(0, 2, 0), idx(0, 2, 1)],
  [idx(0, 2, 1), idx(0, 2, 2)],
  [idx(1, 2, 0), idx(1, 2, 1)],
  [idx(1, 2, 1), idx(1, 2, 2)],
  [idx(2, 2, 0), idx(2, 2, 1)],
  [idx(2, 2, 1), idx(2, 2, 2)],
]

/** BCC-like: corners to centre of each sub-cube */
const BCC_LIKE: number[][] = [
  // Connect corners to body centres (centre of octant sub-cubes)
  [idx(0, 0, 0), idx(1, 1, 1)],
  [idx(2, 0, 0), idx(1, 1, 1)],
  [idx(0, 2, 0), idx(1, 1, 1)],
  [idx(2, 2, 0), idx(1, 1, 1)],
  [idx(0, 0, 2), idx(1, 1, 1)],
  [idx(2, 0, 2), idx(1, 1, 1)],
  [idx(0, 2, 2), idx(1, 1, 1)],
  [idx(2, 2, 2), idx(1, 1, 1)],
  // Plus axis edges for stability
  [idx(0, 0, 0), idx(1, 0, 0)],
  [idx(1, 0, 0), idx(2, 0, 0)],
  [idx(0, 0, 0), idx(0, 1, 0)],
  [idx(0, 1, 0), idx(0, 2, 0)],
  [idx(0, 0, 0), idx(0, 0, 1)],
  [idx(0, 0, 1), idx(0, 0, 2)],
  [idx(2, 2, 2), idx(1, 2, 2)],
  [idx(1, 2, 2), idx(0, 2, 2)],
  [idx(2, 2, 2), idx(2, 1, 2)],
  [idx(2, 1, 2), idx(2, 0, 2)],
  [idx(2, 2, 2), idx(2, 2, 1)],
  [idx(2, 2, 1), idx(2, 2, 0)],
]

/** Face-diagonal: SC + face diagonals */
const FACE_DIAGONAL: number[][] = [
  ...SIMPLE_CUBIC.slice(0, 12), // bottom face
  // bottom face diagonals
  [idx(0, 0, 0), idx(1, 1, 0)],
  [idx(1, 1, 0), idx(2, 2, 0)],
  [idx(2, 0, 0), idx(1, 1, 0)],
  [idx(1, 1, 0), idx(0, 2, 0)],
  // verticals
  [idx(0, 0, 0), idx(0, 0, 1)],
  [idx(0, 0, 1), idx(0, 0, 2)],
  [idx(2, 0, 0), idx(2, 0, 1)],
  [idx(2, 0, 1), idx(2, 0, 2)],
  [idx(0, 2, 0), idx(0, 2, 1)],
  [idx(0, 2, 1), idx(0, 2, 2)],
  [idx(2, 2, 0), idx(2, 2, 1)],
  [idx(2, 2, 1), idx(2, 2, 2)],
  [idx(1, 1, 0), idx(1, 1, 1)],
  [idx(1, 1, 1), idx(1, 1, 2)],
  // top face
  ...SIMPLE_CUBIC.slice(24, 36),
  [idx(0, 0, 2), idx(1, 1, 2)],
  [idx(1, 1, 2), idx(2, 2, 2)],
  [idx(2, 0, 2), idx(1, 1, 2)],
  [idx(1, 1, 2), idx(0, 2, 2)],
]

/** Mixed: SC + some body diagonals */
const MIXED: number[][] = [
  ...SIMPLE_CUBIC.slice(0, 18), // bottom + middle faces horizontal
  ...SIMPLE_CUBIC.slice(36), // verticals
  // body diagonals
  [idx(0, 0, 0), idx(1, 1, 1)],
  [idx(2, 2, 0), idx(1, 1, 1)],
  [idx(0, 2, 0), idx(1, 1, 1)],
  [idx(2, 0, 0), idx(1, 1, 1)],
  [idx(1, 1, 1), idx(0, 0, 2)],
  [idx(1, 1, 1), idx(2, 2, 2)],
]

/** Sparse: minimal connectivity */
const SPARSE: number[][] = [
  // Outer edges only
  [idx(0, 0, 0), idx(2, 0, 0)],
  [idx(0, 0, 0), idx(0, 2, 0)],
  [idx(0, 0, 0), idx(0, 0, 2)],
  [idx(2, 2, 2), idx(0, 2, 2)],
  [idx(2, 2, 2), idx(2, 0, 2)],
  [idx(2, 2, 2), idx(2, 2, 0)],
  [idx(2, 0, 0), idx(2, 2, 0)],
  [idx(2, 0, 0), idx(2, 0, 2)],
  [idx(0, 2, 0), idx(2, 2, 0)],
  [idx(0, 2, 0), idx(0, 2, 2)],
  [idx(0, 0, 2), idx(2, 0, 2)],
  [idx(0, 0, 2), idx(0, 2, 2)],
  // Internal bracing
  [idx(0, 0, 0), idx(1, 1, 1)],
  [idx(2, 2, 2), idx(1, 1, 1)],
  [idx(1, 0, 0), idx(1, 1, 1)],
  [idx(0, 1, 0), idx(1, 1, 1)],
  [idx(0, 0, 1), idx(1, 1, 1)],
  [idx(1, 1, 1), idx(2, 1, 2)],
]

/** Five distinct edge sets */
export const EDGE_SETS: number[][][] = [SIMPLE_CUBIC, BCC_LIKE, FACE_DIAGONAL, MIXED, SPARSE]
