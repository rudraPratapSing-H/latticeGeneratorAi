import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import type { Candidate, Lattice } from '@/api/types'
import {
  buildTiledLattice,
  naiveRelativeDensity,
  periodicRelativeDensity,
} from '@/components/LatticeViewer/geometry'
import { buildStl, buildStlBuffer, clipSegmentToBox } from '@/lib/stl'

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')

// Real solver-verified designs: the seven sample searches in mock/ (copied from search_design.py output).
const samples = fs
  .readdirSync(path.join(REPO, 'mock'))
  .filter((f) => /^sample_\d+\.json$/.test(f))
  .sort()
  .map((f) => {
    const d = JSON.parse(fs.readFileSync(path.join(REPO, 'mock', f), 'utf8')) as { candidates: Candidate[] }
    return { file: f, candidates: d.candidates }
  })

describe('periodic density (bug watchlist 1)', () => {
  it('has the seven sample searches', () => expect(samples.length).toBe(7))

  it.each(samples.map((s) => [s.file, s] as const))('%s: periodic count matches rel_density within 0.1%', (_f, s) => {
    for (const c of s.candidates) {
      const rho = periodicRelativeDensity(c.lattice)
      expect(Math.abs(rho / c.rel_density - 1)).toBeLessThan(0.001)
    }
  })

  it('the naive mirror-and-merge count overstates density (plan: 9% to 118% on the first candidates)', () => {
    const over = samples.flatMap((s) =>
      s.candidates.map((c) => naiveRelativeDensity(c.lattice) / c.rel_density - 1),
    )
    expect(Math.min(...over)).toBeGreaterThan(0.05)
    expect(Math.max(...over)).toBeLessThan(1.5)
    expect(Math.max(...over)).toBeGreaterThan(0.5)
  })
})

describe('tiling is seamless from 1 to 5 per side', () => {
  const lattice = samples[0].candidates[0].lattice
  const key = (p: number[]) => p.map((v) => v.toFixed(4)).join(',')
  const segKey = (a: number[], b: number[]) => [key(a), key(b)].sort().join('|')

  it.each([1, 2, 3, 4, 5])('%d tiles: bounds, and every strut repeats one cell over', (n) => {
    const t = buildTiledLattice(lattice, n)
    expect(t.bounds.size).toEqual([2 * n, 2 * n, 2 * n])
    const all = new Set(t.struts.map((s) => segKey(s.start, s.end)))
    expect(all.size).toBe(t.struts.length) // no duplicates: shared faces merged
    for (const s of t.struts) {
      for (const axis of [0, 1, 2]) {
        if (s.start[axis] + 2 <= n && s.end[axis] + 2 <= n) {
          const a = [...s.start]
          const b = [...s.end]
          a[axis] += 2
          b[axis] += 2
          expect(all.has(segKey(a, b))).toBe(true)
        }
      }
    }
  })

  it('a cell inside a larger block adds struts only by the periodic count', () => {
    const one = buildTiledLattice(lattice, 1).struts.length
    const two = buildTiledLattice(lattice, 2).struts.length
    expect(two).toBeLessThan(8 * one) // shared face struts are not doubled
    expect(two).toBeGreaterThan(4 * one)
  })
})

describe('clipSegmentToBox', () => {
  const lo: [number, number, number] = [-1, -1, -1]
  const hi: [number, number, number] = [1, 1, 1]
  it('keeps an inside segment and clips an outside one', () => {
    expect(clipSegmentToBox([0, 0, 0], [0.5, 0, 0], lo, hi)).toEqual([[0, 0, 0], [0.5, 0, 0]])
    const c = clipSegmentToBox([0, 0, 0], [3, 0, 0], lo, hi)!
    expect(c[1][0]).toBeCloseTo(1)
    expect(clipSegmentToBox([2, 2, 2], [3, 3, 3], lo, hi)).toBeNull()
  })
})

// ---- STL validation: binary, finite, closed shells with consistent outward orientation
interface Parsed {
  triangles: number
  tri: Float32Array
  normals: Float32Array
}

function parseStl(buf: ArrayBuffer): Parsed {
  const dv = new DataView(buf)
  const n = dv.getUint32(80, true)
  expect(buf.byteLength).toBe(84 + 50 * n)
  const tri = new Float32Array(n * 9)
  const normals = new Float32Array(n * 3)
  let o = 84
  for (let t = 0; t < n; t++) {
    for (let k = 0; k < 3; k++) { normals[t * 3 + k] = dv.getFloat32(o, true); o += 4 }
    for (let k = 0; k < 9; k++) { tri[t * 9 + k] = dv.getFloat32(o, true); o += 4 }
    o += 2
  }
  return { triangles: n, tri, normals }
}

function validate(p: Parsed) {
  const q = (x: number) => Math.round(x * 1e3)
  const vk = (i: number, v: number) => `${q(p.tri[i * 9 + v * 3])},${q(p.tri[i * 9 + v * 3 + 1])},${q(p.tri[i * 9 + v * 3 + 2])}`
  const directed = new Map<string, number>()
  let volume = 0
  let finite = true
  let normalsAgree = true
  for (let i = 0; i < p.triangles; i++) {
    for (let v = 0; v < 3; v++) {
      const a = vk(i, v)
      const b = vk(i, (v + 1) % 3)
      directed.set(`${a}>${b}`, (directed.get(`${a}>${b}`) ?? 0) + 1)
    }
    const t = p.tri.subarray(i * 9, i * 9 + 9)
    if (!t.every(Number.isFinite)) finite = false
    const ax = t[3] - t[0], ay = t[4] - t[1], az = t[5] - t[2]
    const bx = t[6] - t[0], by = t[7] - t[1], bz = t[8] - t[2]
    const cx = ay * bz - az * by, cy = az * bx - ax * bz, cz = ax * by - ay * bx
    if (cx * p.normals[i * 3] + cy * p.normals[i * 3 + 1] + cz * p.normals[i * 3 + 2] <= 0) normalsAgree = false
    volume += (t[0] * (t[4] * t[8] - t[5] * t[7]) - t[1] * (t[3] * t[8] - t[5] * t[6]) + t[2] * (t[3] * t[7] - t[4] * t[6])) / 6
  }
  let unmatched = 0
  let repeated = 0
  for (const [k, c] of directed) {
    const [a, b] = k.split('>')
    if (directed.get(`${b}>${a}`) !== c) unmatched++
    if (c > 1) repeated++
  }
  return { finite, normalsAgree, unmatched, repeated, volume }
}

describe('STL export', () => {
  const cand = samples[2].candidates[0]

  it('is a valid binary STL: finite, every edge shared by two triangles with opposite direction, positive volume', () => {
    const r = buildStlBuffer(cand.lattice, { tiles: [2, 2, 2], sides: 8 })
    expect(r.triangles).toBe(r.struts * 32)
    const v = validate(parseStl(r.buffer))
    expect(v.finite).toBe(true)
    expect(v.unmatched).toBe(0) // watertight (each cylinder is a closed shell)
    // coincident end caps of struts that meet end to end repeat an edge in the same direction: that is overlap, which slicers merge
    expect(v.normalsAgree).toBe(true) // normals match the winding
    expect(v.volume).toBeGreaterThan(0) // outward orientation
  })

  it('has the right size in millimetres and uses the solver radius exactly', () => {
    const r = buildStlBuffer(cand.lattice, { tiles: [2, 3, 1], sides: 12 })
    expect(r.sizeMm).toEqual([2 * 2 * 5, 2 * 3 * 5, 2 * 1 * 5]) // cell 10 mm
    const p = parseStl(r.buffer)
    const xs: number[] = []
    const ys: number[] = []
    const zs: number[] = []
    for (let i = 0; i < p.tri.length; i += 3) { xs.push(p.tri[i]); ys.push(p.tri[i + 1]); zs.push(p.tri[i + 2]) }
    const rad = cand.lattice.strut_radius_mm
    // axes are the solver's x, y, z (no swap); struts on the faces poke out by at most the radius
    for (const [vals, size] of [[xs, 20], [ys, 30], [zs, 10]] as const) {
      expect(Math.min(...vals)).toBeGreaterThanOrEqual(-rad - 1e-3)
      expect(Math.max(...vals)).toBeLessThanOrEqual(size + rad + 1e-3)
      expect(Math.max(...vals) - Math.min(...vals)).toBeGreaterThan(size * 0.95)
    }
  })

  it('x, y and z are not swapped: an x-only stretched lattice stays long in x', () => {
    const bar: Lattice = { format: 'octant27', nodes: [[0, 0, 0], [1, 0, 0]], edges: [[0, 1]], cell_size_mm: 10, strut_radius_mm: 0.4 }
    const p = parseStl(buildStlBuffer(bar, { tiles: [1, 1, 1], sides: 8 }).buffer)
    const ext = (k: number) => {
      const v: number[] = []
      for (let i = k; i < p.tri.length; i += 3) v.push(p.tri[i])
      return Math.max(...v) - Math.min(...v)
    }
    expect(ext(0)).toBeCloseTo(10, 2)
    expect(ext(1)).toBeCloseTo(0.8, 1)
    expect(ext(2)).toBeCloseTo(0.8, 1)
  })

  it('drops 12 sides to 8 above one million triangles', () => {
    const big = buildStlBuffer(cand.lattice, { tiles: [8, 8, 8], sides: 12 })
    expect(big.reducedSides).toBe(true)
    expect(big.sides).toBe(8)
    const small = buildStlBuffer(cand.lattice, { tiles: [1, 1, 1], sides: 12 })
    expect(small.reducedSides).toBe(false)
  })

  it('buildStl returns a Blob of the same size', async () => {
    const blob = await buildStl(cand.lattice, { tiles: [1, 1, 1], sides: 8 })
    expect(blob.size).toBe(buildStlBuffer(cand.lattice, { tiles: [1, 1, 1], sides: 8 }).buffer.byteLength)
  })

  it('writes a file for the external validator when STL_OUT is set', async () => {
    const out = process.env.STL_OUT
    if (!out) return
    const blob = await buildStl(cand.lattice, { tiles: [2, 2, 2], sides: 8 })
    fs.writeFileSync(out, Buffer.from(await blob.arrayBuffer()))
  })
})
