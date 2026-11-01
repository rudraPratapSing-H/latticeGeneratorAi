/**
 * Geometry of the assembled implant for the 3D preview: the outer shape of the stem (an elliptical section whose
 * area follows each zone's recorded cross-section, along a gently curved axis) and the lattice struts that fill
 * the lattice zones. Pure functions, no three.js, so they are unit tested.
 *
 * World axes: Y runs along the stem (tip at 0, neck at the top), X is the sideways bend, Z is depth. A lattice
 * cell's own z axis (the stiffness z / strength z the zone was designed for) is laid along the stem.
 */
import type { Lattice } from '@/api/types'
import { buildTiledLattice } from '@/components/LatticeViewer/geometry'

export interface ShapeZone {
  id: string
  name: string
  kind: string
  startMm: number
  endMm: number
  areaMm2: number
}

export interface Section {
  cx: number
  rx: number
  ry: number
}

/** The section is a little wider sideways than deep, like a real stem; its area is unchanged. */
const ASPECT = 1.1
const BEND_MM = 15
/** Safety cap on struts drawn for one zone. */
export const MAX_STRUTS_PER_ZONE = 150_000

export function stemCenterX(y: number, lengthMm: number): number {
  return Math.sin((y / lengthMm) * Math.PI * 0.7) * BEND_MM
}

/** Radius of the circle with the zone's area, at the middle of each zone and linear in between. */
export function stemRadiusAt(zones: ShapeZone[], y: number): number {
  const pts = zones.map((z) => ({
    y: (z.startMm + z.endMm) / 2,
    r: Math.sqrt(z.areaMm2 / Math.PI),
  }))
  if (pts.length === 0) return 10
  if (y <= pts[0].y) return pts[0].r
  for (let i = 1; i < pts.length; i++) {
    if (y <= pts[i].y) {
      const a = pts[i - 1]
      const b = pts[i]
      return a.r + ((b.r - a.r) * (y - a.y)) / (b.y - a.y)
    }
  }
  return pts[pts.length - 1].r
}

export function sectionAt(zones: ShapeZone[], y: number, lengthMm: number): Section {
  const r = stemRadiusAt(zones, y)
  return { cx: stemCenterX(y, lengthMm), rx: r * ASPECT, ry: r / ASPECT }
}

export interface ShellData {
  positions: Float32Array
  indices: Uint32Array
}

/** The outer skin of the stem between y0 and y1, as indexed triangles. Caps only where asked. */
export function buildShell(
  zones: ShapeZone[],
  y0: number,
  y1: number,
  lengthMm: number,
  opts: {
    segments?: number
    stepMm?: number
    capStart?: boolean
    capEnd?: boolean
  } = {},
): ShellData {
  const segments = opts.segments ?? 40
  const steps = Math.max(1, Math.ceil((y1 - y0) / (opts.stepMm ?? 2)))
  const rings = steps + 1
  const positions: number[] = []
  for (let i = 0; i < rings; i++) {
    const y = y0 + ((y1 - y0) * i) / steps
    const s = sectionAt(zones, y, lengthMm)
    for (let j = 0; j < segments; j++) {
      const a = (j / segments) * Math.PI * 2
      positions.push(s.cx + Math.cos(a) * s.rx, y, Math.sin(a) * s.ry)
    }
  }
  const indices: number[] = []
  for (let i = 0; i < steps; i++) {
    for (let j = 0; j < segments; j++) {
      const a = i * segments + j
      const b = i * segments + ((j + 1) % segments)
      const c = (i + 1) * segments + j
      const d = (i + 1) * segments + ((j + 1) % segments)
      indices.push(a, c, b, b, c, d)
    }
  }
  const cap = (ring: number, flip: boolean) => {
    const sec = sectionAt(zones, y0 + ((y1 - y0) * ring) / steps, lengthMm)
    const centre = positions.length / 3
    positions.push(sec.cx, y0 + ((y1 - y0) * ring) / steps, 0)
    for (let j = 0; j < segments; j++) {
      const a = ring * segments + j
      const b = ring * segments + ((j + 1) % segments)
      indices.push(centre, flip ? b : a, flip ? a : b)
    }
  }
  if (opts.capStart) cap(0, false)
  if (opts.capEnd) cap(steps, true)
  return {
    positions: new Float32Array(positions),
    indices: new Uint32Array(indices),
  }
}

/**
 * The struts of one lattice zone: the chosen cell tiled in whole layers along the stem and kept where it lies inside
 * the stem's outline. Returns six numbers per strut (start xyz, end xyz) in mm.
 */
export function buildZoneStruts(
  lattice: Lattice,
  zones: ShapeZone[],
  zone: ShapeZone,
  lengthMm: number,
): Float32Array {
  const cs = lattice.cell_size_mm
  const length = zone.endMm - zone.startMm
  const layers = Math.max(1, Math.floor(length / cs + 1e-6))
  const layerH = length / layers
  const stretch = layerH / cs
  const half = cs / 2
  const cell = buildTiledLattice(lattice, 1).struts
  const inside = (x: number, y: number, z: number) => {
    const s = sectionAt(zones, y, lengthMm)
    return ((x - s.cx) / s.rx) ** 2 + (z / s.ry) ** 2 <= 1
  }
  const q = (v: number) => Math.round(v * 50)
  const seen = new Set<string>()
  const out: number[] = []

  for (let k = 0; k < layers; k++) {
    const yc = zone.startMm + (k + 0.5) * layerH
    const sec = sectionAt(zones, yc, lengthMm)
    const nx = Math.ceil(sec.rx / cs) + 1
    const nz = Math.ceil(sec.ry / cs) + 1
    for (let ix = -nx; ix <= nx; ix++) {
      for (let iz = -nz; iz <= nz; iz++) {
        for (const st of cell) {
          const ax = sec.cx + ix * cs + half * st.start[0]
          const az = iz * cs + half * st.start[1]
          const ay = yc + half * stretch * st.start[2]
          const bx = sec.cx + ix * cs + half * st.end[0]
          const bz = iz * cs + half * st.end[1]
          const by = yc + half * stretch * st.end[2]
          if (!inside(ax, ay, az) || !inside(bx, by, bz)) continue
          const ka = `${q(ax)},${q(ay)},${q(az)}`
          const kb = `${q(bx)},${q(by)},${q(bz)}`
          const key = ka < kb ? `${ka}|${kb}` : `${kb}|${ka}`
          if (seen.has(key)) continue
          seen.add(key)
          out.push(ax, ay, az, bx, by, bz)
          if (out.length / 6 >= MAX_STRUTS_PER_ZONE) return new Float32Array(out)
        }
      }
    }
  }
  return new Float32Array(out)
}
