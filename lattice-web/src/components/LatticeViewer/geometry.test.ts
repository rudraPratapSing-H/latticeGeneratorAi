import { describe, it, expect } from 'vitest'
import { buildTiledLattice } from '@/components/LatticeViewer/geometry'
import type { Lattice } from '@/api/types'

describe('LatticeViewer geometry builder', () => {
  const simpleLattice: Lattice = {
    format: 'octant27',
    nodes: [
      [0, 0, 0],
      [1, 0, 0],
      [0, 1, 0],
      [0, 0, 1],
    ],
    edges: [
      [0, 1],
      [0, 2],
      [0, 3],
    ],
    cell_size_mm: 10,
    strut_radius_mm: 0.3,
  }

  it('rebuilds unit cell and mirrors across 8 octants with deduplication', () => {
    const singleCell = buildTiledLattice(simpleLattice, 1)

    // Origin (0,0,0) edges along axes:
    // [0,0,0] to [1,0,0] mirrored to s_x = +1 and -1 creates [-1,0,0] to [0,0,0] and [0,0,0] to [1,0,0]
    // Across 3 axes, there should be 6 axis struts meeting at the center!
    expect(singleCell.struts.length).toBe(6)
    expect(singleCell.nodes.length).toBe(7) // center + 6 tips
    expect(singleCell.strutRadius).toBeCloseTo(0.06, 3)
  })

  it('tiles across N x N x N cells and centers the block', () => {
    const tiled2 = buildTiledLattice(simpleLattice, 2)

    // With 2x2x2 = 8 cells, size is 4x4x4 model units centered at 0
    expect(tiled2.bounds.size).toEqual([4, 4, 4])
    expect(tiled2.bounds.min).toEqual([-2, -2, -2])
    expect(tiled2.bounds.max).toEqual([2, 2, 2])
    expect(tiled2.struts.length).toBeGreaterThan(singleCellExpectedStruts(simpleLattice))
  })

  it('clamps tiles to 1..5', () => {
    const clampedUnder = buildTiledLattice(simpleLattice, 0)
    expect(clampedUnder.bounds.size).toEqual([2, 2, 2])

    const clampedOver = buildTiledLattice(simpleLattice, 10)
    expect(clampedOver.bounds.size).toEqual([10, 10, 10])
  })
})

function singleCellExpectedStruts(lattice: Lattice): number {
  return buildTiledLattice(lattice, 1).struts.length
}

