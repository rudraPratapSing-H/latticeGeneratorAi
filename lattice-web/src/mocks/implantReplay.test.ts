import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DEMO_LATTICE_ZONES, STRESS_SCALE, replay } from '@/mocks/implantReplay'

describe('implant demo replay', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    replay.editZones([
      { id: 'z1', range_mm: [0, 82.5] },
      { id: 'z2', range_mm: [82.5, 137.5] },
    ])
  })
  afterEach(() => vi.useRealTimers())

  it('has three zones: two lattice stem zones and a solid neck and taper on top', () => {
    const t = replay.zones('i_x')
    expect(t.zones.map((z) => z.kind)).toEqual(['lattice', 'lattice', 'solid'])
    expect(t.zones.map((z) => z.name)).toEqual(['distal stem', 'proximal body', 'neck and taper'])
    expect(t.zones[0].range_mm[0]).toBe(0)
    expect(t.zones[0].range_mm[1]).toBe(t.zones[1].range_mm[0])
    expect(t.zones[1].range_mm[1]).toBe(t.zones[2].range_mm[0])
    expect(t.zones[2].range_mm[1]).toBe(t.length_mm)
    expect(t.zones[2].reason).toContain('femoral head')
  })

  it('says openly that the load case is scaled for the demo', () => {
    const t = replay.zones('i_x')
    expect(t.warnings.join(' ')).toContain('Demo load case')
    expect(
      t.load.assumptions.some((a) => a.name === 'demo stress scaling' && a.value === STRESS_SCALE),
    ).toBe(true)
  })

  it('every lattice zone target is met by the candidates offered for it', () => {
    for (const id of DEMO_LATTICE_ZONES) {
      const z = replay.zones('i_x').zones.find((x) => x.id === id)!
      const c = replay.candidates(id)
      expect(c.candidates.length).toBeGreaterThan(0)
      for (const cand of c.candidates) {
        expect(cand.verified.strength_mpa.z).toBeGreaterThanOrEqual(z.stress_mpa)
        expect(Math.abs(cand.verified.stiffness_gpa.z / 10 - 1)).toBeLessThanOrEqual(0.1)
      }
    }
  })

  it('the solid neck has no candidates and explains why', () => {
    const c = replay.candidates('z3')
    expect(c.kind).toBe('solid')
    expect(c.candidates).toEqual([])
    expect(c.reason).toContain('femoral head')
  })

  it('candidate ids are unique across zones', () => {
    const ids = replay.allCandidates().map((c) => c.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('moving a boundary snaps to the cell grid and keeps three cells in every zone', () => {
    replay.editZones([
      { id: 'z1', range_mm: [0, 40] },
      { id: 'z2', range_mm: [40, 137.5] },
    ])
    let t = replay.zones('i_x')
    expect(t.zones[0].range_mm[1]).toBeCloseTo(38.5, 6)
    expect(t.notes.join(' ')).toContain('moved from 40.0 to 38.5')
    replay.editZones([
      { id: 'z1', range_mm: [0, 5] },
      { id: 'z2', range_mm: [5, 200] },
    ])
    t = replay.zones('i_x')
    expect(t.zones.map((z) => z.cells).every((c) => c >= 3)).toBe(true)
    expect(t.zones[2].range_mm[1]).toBe(t.length_mm)
  })

  it('searches run one after another for the lattice zones and finish', () => {
    vi.setSystemTime(0)
    replay.startSearch()
    expect(replay.candidates('z1').job?.status).toBe('running')
    expect(replay.candidates('z2').job?.status).toBe('queued')
    expect(replay.candidates('z1').candidates).toEqual([])
    vi.setSystemTime(5_500)
    expect(replay.candidates('z1').candidates.length).toBeGreaterThan(0)
    expect(replay.candidates('z2').job?.status).toBe('running')
    vi.setSystemTime(11_000)
    expect(replay.candidates('z2').candidates.length).toBeGreaterThan(0)
  })

  it('assembly steps through tile, assemble, check, export and then is done', () => {
    vi.setSystemTime(0)
    replay.assembleStart()
    const stages = new Set<string | null>()
    for (let ms = 1_000; ms < 9_000; ms += 1_000) {
      vi.setSystemTime(ms)
      stages.add(replay.assembleJob('i_x').stage)
    }
    expect([...stages]).toEqual(['tile', 'assemble', 'check', 'export'])
    vi.setSystemTime(9_500)
    expect(replay.assembleJob('i_x').status).toBe('done')
  })

  it('the assembled implant has two lattice parts, a solid neck and two joints', () => {
    const r = replay.result('i_x')
    expect(r.zones.map((z) => z.kind)).toEqual(['lattice', 'lattice', 'solid'])
    expect(
      r.zones.filter((z) => z.kind === 'lattice').every((z) => z.candidate_id && z.verified),
    ).toBe(true)
    expect(r.zones[2].candidate_id).toBeNull()
    expect(r.parts.map((p) => p.kind).sort()).toEqual([
      'interface',
      'interface',
      'lattice',
      'lattice',
      'solid',
    ])
    expect(r.summary.lattice_share_pct).toBeGreaterThan(30)
    expect(r.summary.lattice_share_pct).toBeLessThan(95)
    const md = replay.report()
    expect(md).toContain('neck and taper')
    expect(md).toContain('demo stress scaling')
  })
})
