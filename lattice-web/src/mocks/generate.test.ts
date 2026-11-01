import { describe, it, expect } from 'vitest'
import { generateCandidates } from '@/mocks/generate'
import type { DesignRequest } from '@/api/types'

const MOCK_REQUEST: DesignRequest = {
  material: 'ti64',
  part: { size_mm: [40, 40, 40], cell_mm: 10 },
  target: {
    stiffness_gpa: { x: 8, y: 8, z: 12 },
    strength_mpa: { x: 90, y: 90, z: null },
    max_mass_g: 60,
  },
  modes: { stiffness: 'about', strength: 'at_least', weight: 'at_most' },
  tolerance_pct: 10,
  n_results: 5,
}

describe('generateCandidates', () => {
  it('returns the requested number of candidates', () => {
    const candidates = generateCandidates('j_test1', MOCK_REQUEST, 'happy')
    expect(candidates).toHaveLength(5)
  })

  it('returns empty array for empty scenario', () => {
    const candidates = generateCandidates('j_test2', MOCK_REQUEST, 'empty')
    expect(candidates).toHaveLength(0)
  })

  it('generates deterministic results for same seed', () => {
    const a = generateCandidates('j_seed1', MOCK_REQUEST, 'happy')
    const b = generateCandidates('j_seed1', MOCK_REQUEST, 'happy')
    expect(a.map((c) => c.id)).toEqual(b.map((c) => c.id))
    expect(a.map((c) => c.verified.stiffness_gpa.x)).toEqual(
      b.map((c) => c.verified.stiffness_gpa.x),
    )
  })

  it('replays real solver output: ids are re-keyed to the job, numbers are the stored ones', () => {
    const a = generateCandidates('j_abc', MOCK_REQUEST, 'happy')
    const b = generateCandidates('j_xyz', MOCK_REQUEST, 'happy')
    expect(a.every((c) => c.id.startsWith('j_abc_d_'))).toBe(true)
    expect(a.map((c) => c.verified)).toEqual(b.map((c) => c.verified))
    expect(a.every((c) => c.mass_g > 0 && typeof c.matches_targets === 'boolean')).toBe(true)
  })

  it('the no_match scenario replays a real search that missed: not a match, with a shortfall', () => {
    const c = generateCandidates('j_nm', MOCK_REQUEST, 'no_match')
    expect(c.length).toBeGreaterThan(0)
    expect(c.every((x) => x.matches_targets === false)).toBe(true)
  })

  it('picks the stored search nearest to the request', () => {
    const near = { ...MOCK_REQUEST, target: { stiffness_gpa: { x: 0.328, y: 0.351, z: 0.335 }, strength_mpa: { x: 3.83, y: 3.07, z: 3.45 }, max_mass_g: 14.5 } }
    const c = generateCandidates('j_near', near as typeof MOCK_REQUEST, 'happy')
    expect(c[0].rel_density).toBeCloseTo(0.05, 2)
  })

  it('candidates have monotonically increasing rank', () => {
    const candidates = generateCandidates('j_rank', MOCK_REQUEST, 'happy')
    for (let i = 1; i < candidates.length; i++) {
      expect(candidates[i].rank).toBe(candidates[i - 1].rank + 1)
    }
  })

  it('candidates have valid lattice data', () => {
    const candidates = generateCandidates('j_lattice', MOCK_REQUEST, 'happy')
    candidates.forEach((c) => {
      expect(c.lattice.format).toBe('octant27')
      expect(c.lattice.nodes.length).toBeGreaterThan(0)
      expect(c.lattice.edges.length).toBeGreaterThan(0)
      expect(c.lattice.strut_radius_mm).toBeGreaterThan(0)
    })
  })
})
