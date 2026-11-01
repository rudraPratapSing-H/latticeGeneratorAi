import type { Lattice } from '@/api/types'

export interface Strut3D {
  start: [number, number, number]
  end: [number, number, number]
  midpoint: [number, number, number]
  length: number
  direction: [number, number, number]
  dominantAxis: 'x' | 'y' | 'z'
}

export interface Node3D {
  position: [number, number, number]
}

export interface RebuiltLattice3D {
  struts: Strut3D[]
  nodes: Node3D[]
  bounds: {
    min: [number, number, number]
    max: [number, number, number]
    size: [number, number, number]
  }
  strutRadius: number
}

/**
 * Quantize a coordinate for deduplication keying
 */
function q(val: number): string {
  return val.toFixed(4)
}

/**
 * Deduplication key for an undirected strut between p1 and p2
 */
function strutKey(
  p1: [number, number, number],
  p2: [number, number, number],
): string {
  const k1 = `${q(p1[0])},${q(p1[1])},${q(p1[2])}`
  const k2 = `${q(p2[0])},${q(p2[1])},${q(p2[2])}`
  return k1 < k2 ? `${k1}_${k2}` : `${k2}_${k1}`
}

function nodeKey(p: [number, number, number]): string {
  return `${q(p[0])},${q(p[1])},${q(p[2])}`
}

/**
 * Rebuild full unit cell [-1, 1]³ from octant [0, 1]³ by mirroring across x=0, y=0, z=0,
 * and tile across N x N x N cells, deduplicating struts on symmetry planes and shared faces.
 */
export type Tiles = number | [number, number, number]

export function normalizeTiles(tiles: Tiles, max = 5): [number, number, number] {
  const t = Array.isArray(tiles) ? tiles : [tiles, tiles, tiles]
  const c = (v: number) => Math.max(1, Math.min(max, Math.floor(v)))
  return [c(t[0]), c(t[1]), c(t[2])]
}

export function buildTiledLattice(
  lattice: Lattice,
  tiles: Tiles = 1,
  maxTiles = 5,
): RebuiltLattice3D {
  const [tilesX, tilesY, tilesZ] = normalizeTiles(tiles, maxTiles)
  const octantNodes = lattice.nodes
  const octantEdges = lattice.edges

  // Octant signs (8 combinations)
  const signs: Array<[number, number, number]> = [
    [1, 1, 1],
    [1, 1, -1],
    [1, -1, 1],
    [1, -1, -1],
    [-1, 1, 1],
    [-1, 1, -1],
    [-1, -1, 1],
    [-1, -1, -1],
  ]

  const seenStruts = new Set<string>()
  const seenNodes = new Map<string, [number, number, number]>()
  const struts: Strut3D[] = []

  // Unit cell size in model units is 2 (spans [-1, 1])
  // Tiling offset step = 2
  // We center the whole assembly by subtracting (clampedTiles - 1)
  for (let tx = 0; tx < tilesX; tx++) {
    for (let ty = 0; ty < tilesY; ty++) {
      for (let tz = 0; tz < tilesZ; tz++) {
        const shiftX = 2 * tx - (tilesX - 1)
        const shiftY = 2 * ty - (tilesY - 1)
        const shiftZ = 2 * tz - (tilesZ - 1)

        // For each of the 8 octants
        for (const [sx, sy, sz] of signs) {
          for (const [i1, i2] of octantEdges) {
            const n1 = octantNodes[i1]
            const n2 = octantNodes[i2]
            if (!n1 || !n2) continue

            const p1: [number, number, number] = [
              sx * n1[0] + shiftX,
              sy * n1[1] + shiftY,
              sz * n1[2] + shiftZ,
            ]
            const p2: [number, number, number] = [
              sx * n2[0] + shiftX,
              sy * n2[1] + shiftY,
              sz * n2[2] + shiftZ,
            ]

            const key = strutKey(p1, p2)
            if (seenStruts.has(key)) continue
            seenStruts.add(key)

            // Register nodes
            const nk1 = nodeKey(p1)
            const nk2 = nodeKey(p2)
            if (!seenNodes.has(nk1)) seenNodes.set(nk1, p1)
            if (!seenNodes.has(nk2)) seenNodes.set(nk2, p2)

            // Calculate geometry
            const dx = p2[0] - p1[0]
            const dy = p2[1] - p1[1]
            const dz = p2[2] - p1[2]
            const length = Math.sqrt(dx * dx + dy * dy + dz * dz)
            if (length < 1e-5) continue

            const adx = Math.abs(dx)
            const ady = Math.abs(dy)
            const adz = Math.abs(dz)

            let dominantAxis: 'x' | 'y' | 'z' = 'z'
            if (adx >= ady && adx >= adz) dominantAxis = 'x'
            else if (ady >= adx && ady >= adz) dominantAxis = 'y'

            struts.push({
              start: p1,
              end: p2,
              midpoint: [
                (p1[0] + p2[0]) / 2,
                (p1[1] + p2[1]) / 2,
                (p1[2] + p2[2]) / 2,
              ],
              length,
              direction: [dx / length, dy / length, dz / length],
              dominantAxis,
            })
          }
        }
      }
    }
  }

  const nodes: Node3D[] = Array.from(seenNodes.values()).map((position) => ({
    position,
  }))

  // Model-normalized strut radius, exactly as the solver set it (never recomputed or clamped):
  // 1 model unit corresponds to cell_size_mm / 2, so radius_model = strut_radius_mm / (cell_size_mm / 2)
  const strutRadius = modelRadius(lattice)

  return {
    struts,
    nodes,
    bounds: {
      min: [-tilesX, -tilesY, -tilesZ],
      max: [tilesX, tilesY, tilesZ],
      size: [2 * tilesX, 2 * tilesY, 2 * tilesZ],
    },
    strutRadius,
  }
}



/** Strut radius in model units (the cell side is 2 units): radius_mm / (cell_mm / 2). */
export function modelRadius(lattice: Lattice): number {
  return (2 * lattice.strut_radius_mm) / lattice.cell_size_mm
}

/**
 * Relative density by the PERIODIC count: a strut on the +1 face of the cell is the same strut as on the -1 face
 * and is counted once, so wrap every coordinate of +1 to -1 before de-duplicating. The naive mirror-and-merge
 * count (what the viewer draws for tiling) counts face struts twice and overstates density by 9% to 118%.
 * rho = pi r^2 sum(L) / V  with V = 8 model units cubed and r in model units.
 */
export function periodicRelativeDensity(lattice: Lattice): number {
  const wrap = (v: number) => (Math.abs(v - 1) < 1e-6 ? -1 : v)
  const key = (p: number[]) => p.map((v) => wrap(v).toFixed(5)).join(',')
  const seen = new Set<string>()
  let total = 0
  for (const [i, j] of lattice.edges) {
    const a = lattice.nodes[i]
    const b = lattice.nodes[j]
    if (!a || !b) continue
    for (const sx of [1, -1]) {
      for (const sy of [1, -1]) {
        for (const sz of [1, -1]) {
          const p = [sx * a[0], sy * a[1], sz * a[2]]
          const q = [sx * b[0], sy * b[1], sz * b[2]]
          const len = Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2])
          if (len < 1e-5) continue
          const k = [key(p), key(q)].sort().join('|')
          if (seen.has(k)) continue
          seen.add(k)
          total += len
        }
      }
    }
  }
  const r = modelRadius(lattice)
  return (Math.PI * r * r * total) / 8
}

/** The naive count: mirror and merge identical coordinates only (what tiling draws). For comparison in tests. */
export function naiveRelativeDensity(lattice: Lattice): number {
  const cell = buildTiledLattice(lattice, 1)
  const total = cell.struts.reduce((sum, s) => sum + s.length, 0)
  const r = modelRadius(lattice)
  return (Math.PI * r * r * total) / 8
}
