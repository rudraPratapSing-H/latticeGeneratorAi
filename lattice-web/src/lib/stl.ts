import type { Lattice } from '@/api/types'
import { buildTiledLattice, modelRadius, normalizeTiles } from '@/components/LatticeViewer/geometry'
import { MAX_STL_TILES } from '@/config/constants'

export interface StlOptions {
  tiles: [number, number, number]
  filename?: string
  sides?: 8 | 12
}

export interface StlResult {
  buffer: ArrayBuffer
  triangles: number
  sides: 8 | 12
  struts: number
  sizeMm: [number, number, number]
  /** Set when the file would have exceeded ~1 million triangles and was built with 8 sides instead of 12. */
  reducedSides: boolean
}

type V3 = [number, number, number]

export const MAX_TRIANGLES_BEFORE_REDUCING = 1_000_000

/** Triangles per strut: a closed prism with flat end caps has 4 x sides. */
export const trianglesPerStrut = (sides: number) => 4 * sides

/**
 * Clip the segment a-b to the axis-aligned box [lo, hi] (Liang-Barsky). Returns null when nothing is inside.
 * Struts are clipped to the block so none sticks out of its faces.
 */
export function clipSegmentToBox(a: V3, b: V3, lo: V3, hi: V3): [V3, V3] | null {
  let t0 = 0
  let t1 = 1
  for (let i = 0; i < 3; i++) {
    const d = b[i] - a[i]
    if (Math.abs(d) < 1e-12) {
      if (a[i] < lo[i] - 1e-9 || a[i] > hi[i] + 1e-9) return null
      continue
    }
    let ta = (lo[i] - a[i]) / d
    let tb = (hi[i] - a[i]) / d
    if (ta > tb) [ta, tb] = [tb, ta]
    t0 = Math.max(t0, ta)
    t1 = Math.min(t1, tb)
    if (t0 > t1) return null
  }
  const at = (t: number): V3 => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]
  return [at(t0), at(t1)]
}

const sub = (p: V3, q: V3): V3 => [p[0] - q[0], p[1] - q[1], p[2] - q[2]]
const cross = (p: V3, q: V3): V3 => [
  p[1] * q[2] - p[2] * q[1],
  p[2] * q[0] - p[0] * q[2],
  p[0] * q[1] - p[1] * q[0],
]
const norm = (p: V3): V3 => {
  const l = Math.hypot(p[0], p[1], p[2]) || 1
  return [p[0] / l, p[1] / l, p[2] / l]
}

/** Push the triangles of a closed prism (flat caps, outward normals) from a to b with radius r. */
function pushPrism(out: number[], a: V3, b: V3, r: number, sides: number): void {
  const d = norm(sub(b, a))
  const helper: V3 = Math.abs(d[0]) < 0.9 ? [1, 0, 0] : [0, 1, 0]
  const u = norm(cross(helper, d))
  const v = cross(d, u) // (u, v, d) is right-handed
  const ring = (c: V3): V3[] =>
    Array.from({ length: sides }, (_, i) => {
      const th = (2 * Math.PI * i) / sides
      const cs = Math.cos(th) * r
      const sn = Math.sin(th) * r
      return [c[0] + cs * u[0] + sn * v[0], c[1] + cs * u[1] + sn * v[1], c[2] + cs * u[2] + sn * v[2]] as V3
    })
  const ra = ring(a)
  const rb = ring(b)
  const tri = (p: V3, q: V3, s: V3) => out.push(...p, ...q, ...s)
  for (let i = 0; i < sides; i++) {
    const j = (i + 1) % sides
    tri(ra[i], ra[j], rb[j]) // side, outward
    tri(ra[i], rb[j], rb[i])
    tri(rb[i], rb[j], b) // top cap, normal +d
    tri(ra[j], ra[i], a) // bottom cap, normal -d
  }
}

/** Binary STL (little endian, millimetres, Z up) of the tiled lattice block. */
export function buildStlBuffer(lattice: Lattice, options: StlOptions): StlResult {
  const tiles = normalizeTiles(options.tiles, MAX_STL_TILES)
  const cell = buildTiledLattice(lattice, tiles, MAX_STL_TILES)
  const unit = lattice.cell_size_mm / 2 // one model unit in mm; the cell side is 2 units
  const radiusMm = modelRadius(lattice) * unit // = lattice.strut_radius_mm, exactly as the solver set it
  const lo: V3 = [-tiles[0], -tiles[1], -tiles[2]]
  const hi: V3 = [tiles[0], tiles[1], tiles[2]]
  const segs: [V3, V3][] = []
  for (const s of cell.struts) {
    const c = clipSegmentToBox(s.start, s.end, lo, hi)
    if (c && Math.hypot(...sub(c[1], c[0])) > 1e-6) segs.push(c)
  }
  let sides: 8 | 12 = options.sides ?? 12
  let reduced = false
  if (sides === 12 && segs.length * trianglesPerStrut(12) > MAX_TRIANGLES_BEFORE_REDUCING) {
    sides = 8
    reduced = true
  }
  // block corner at the origin, millimetres. x, y, z stay the solver's x, y, z: no axis swap here.
  const toMm = (p: V3): V3 => [(p[0] + tiles[0]) * unit, (p[1] + tiles[1]) * unit, (p[2] + tiles[2]) * unit]
  const flat: number[] = []
  for (const [a, b] of segs) pushPrism(flat, toMm(a), toMm(b), radiusMm, sides)

  const n = flat.length / 9
  const buffer = new ArrayBuffer(84 + n * 50)
  const dv = new DataView(buffer)
  const header = `Lattice Designer ${options.filename ?? ''} mm, Z up`.slice(0, 79)
  for (let i = 0; i < header.length; i++) dv.setUint8(i, header.charCodeAt(i) & 0x7f)
  dv.setUint32(80, n, true)
  let o = 84
  for (let t = 0; t < n; t++) {
    const p = flat.slice(t * 9, t * 9 + 9)
    const nm = norm(cross(sub([p[3], p[4], p[5]], [p[0], p[1], p[2]]), sub([p[6], p[7], p[8]], [p[0], p[1], p[2]])))
    for (const x of nm) { dv.setFloat32(o, x, true); o += 4 }
    for (const x of p) { dv.setFloat32(o, x, true); o += 4 }
    dv.setUint16(o, 0, true); o += 2
  }
  return {
    buffer,
    triangles: n,
    sides,
    struts: segs.length,
    sizeMm: [2 * tiles[0] * unit, 2 * tiles[1] * unit, 2 * tiles[2] * unit],
    reducedSides: reduced,
  }
}

/** Build an STL blob from a lattice definition (octant27: mirror, merge, tile, clip, cylinders). */
export async function buildStl(lattice: Lattice, options: StlOptions): Promise<Blob> {
  const r = buildStlBuffer(lattice, options)
  return new Blob([r.buffer], { type: 'model/stl' })
}
