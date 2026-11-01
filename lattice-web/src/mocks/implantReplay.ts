/**
 * Implant API replay for the implant demo. The recorded responses are real backend output, recorded by
 * scripts/run_implant_case.py (45 kg sedentary patient, the generated test stem, four zones, one of them lattice).
 *
 * The demo is built on top of that recording and changes four things, all of them in this file (the JSON fixtures
 * stay exactly as recorded):
 *  1. Three zones: a distal stem and a proximal body, both lattice, and the neck and taper at the top, kept solid
 *     (it carries the femoral head on a smooth polished taper). The lattice zones use the five solver-verified
 *     cells recorded for the recorded mid stem 2 zone, whose stiffness (10 GPa) and strength (52 to 62 MPa) meet the
 *     targets set here.
 *  2. A demo load case. The recorded design stress at the tip is 169 MPa, above the 76.1 MPa the strongest lattice
 *     reaches, so the recorded run keeps the tip solid. To let the stem zones be lattice the design stresses are
 *     scaled by STRESS_SCALE. The scaling is listed in the load assumptions and as a warning, so it is visible.
 *  3. Realistic timing. Zone searches run one after another and the assemble job steps through tile, assemble,
 *     check and export, so the workflow takes time the way the real backend does.
 *  4. Derived result numbers. Volume, mass, triangle count and lattice share of the assembled implant are scaled
 *     from the recorded parts by envelope volume. They are estimates, not a new measurement.
 * Re-record with scripts/run_implant_case.py to replace all of this with real output.
 */
import create from '@/mocks/fixtures/real/implant/create.json'
import zones from '@/mocks/fixtures/real/implant/zones.json'
import candidatesLattice from '@/mocks/fixtures/real/implant/candidates_z3.json'
import assembleJob from '@/mocks/fixtures/real/implant/assemble_job.json'
import result from '@/mocks/fixtures/real/implant/result.json'
import report from '@/mocks/fixtures/real/implant/report.json'
import type { Candidate } from '@/api/types'

export const MOCK_ASSEMBLE_JOB_ID = 'a_mock0001'

/** Lattice zones of the demo, in the order the searches run. */
export const DEMO_LATTICE_ZONES = ['z1', 'z2'] as const

/** Design stresses of the demo are this share of the recorded ones, so that the stem zones can be lattice. */
export const STRESS_SCALE = 0.29

const SEARCH_SECONDS = 5
const ASSEMBLE_SECONDS = 9
const SEARCH_STAGES = [
  'Checking the reach table',
  'Picking start codes from the stored lattices',
  'Steering the codes toward the zone targets',
  'Decoding the lattices',
  'Verifying with the beam solver',
]
const ASSEMBLE_STAGES = [
  { stage: 'tile', until: 3, message: 'Tiling the chosen cells into each lattice zone' },
  { stage: 'assemble', until: 5.5, message: 'Joining the zones with interface plates' },
  { stage: 'check', until: 7.5, message: 'Checking a finite block of each lattice zone' },
  { stage: 'export', until: ASSEMBLE_SECONDS, message: 'Writing the STL file' },
]

const CELL = zones.cell_mm
const LENGTH = zones.length_mm
const DEFAULT_BOUNDARIES = [82.5, 137.5]
const ZONE_NAMES = ['distal stem', 'proximal body', 'neck and taper']
const ZONE_KINDS = ['lattice', 'lattice', 'solid'] as const
const BONE_REGIONS = ['tip', 'mid stem', 'neck']
const NECK_REASON =
  'Kept solid: the neck carries the femoral head on a smooth, polished taper, so it is not a lattice.'
const MIN_CELLS = 3

let searchStartedAt: number | null = null
let assembleStartedAt: number | null = null
let boundaries = [...DEFAULT_BOUNDARIES]
let boundaryNotes: string[] = []

const withId = <T extends object>(obj: T, implantId: string): T => ({
  ...obj,
  implant_id: implantId,
})
const clone = <T>(obj: T): T => JSON.parse(JSON.stringify(obj)) as T

// ---- the recorded stem, as a piecewise profile -------------------------------------------------------------------

type RecordedZone = (typeof zones.zones)[number]
const recorded = zones.zones as RecordedZone[]

function overlap(z: RecordedZone, a: number, b: number): number {
  return Math.max(0, Math.min(z.range_mm[1], b) - Math.max(z.range_mm[0], a))
}
/** Volume of the stem between a and b (cross-section area x length, zone by zone). */
export function envelopeMm3(a: number, b: number): number {
  return recorded.reduce((v, z) => v + z.area_mm2 * overlap(z, a, b), 0)
}
const meanOf = (a: number, b: number, pick: (z: RecordedZone) => number) =>
  recorded.reduce((v, z) => v + pick(z) * overlap(z, a, b), 0) / (b - a)
const peakStress = (a: number, b: number) =>
  Math.max(...recorded.filter((z) => overlap(z, a, b) > 0).map((z) => z.stress_mpa))

const templateZone = recorded.find((z) => z.id === 'z3') as RecordedZone
const TEMPLATE_ENVELOPE = envelopeMm3(templateZone.range_mm[0], templateZone.range_mm[1])
const spans = (): [number, number][] => [
  [0, boundaries[0]],
  [boundaries[0], boundaries[1]],
  [boundaries[1], LENGTH],
]

// ---- zones ----------------------------------------------------------------------------------------------------

function demoZoneTable(implantId: string) {
  const table = clone(zones)
  table.zones = spans().map(([a, b], i) => {
    const z = clone(templateZone)
    const stress = peakStress(a, b) * STRESS_SCALE
    const lattice = ZONE_KINDS[i] === 'lattice'
    z.id = `z${i + 1}`
    z.name = ZONE_NAMES[i]
    z.range_mm = [a, b]
    z.thickness_mm = meanOf(a, b, (r) => r.thickness_mm)
    z.area_mm2 = envelopeMm3(a, b) / (b - a)
    z.stress_mpa = stress
    z.cells = Math.floor((b - a) / CELL + 1e-6)
    z.bone_region = BONE_REGIONS[i]
    z.kind = ZONE_KINDS[i]
    z.reason = lattice
      ? "A stored lattice is within tolerance of this zone's targets."
      : NECK_REASON
    z.requirement.stiffness_gpa.z = {
      value: lattice ? 10 : (null as unknown as number),
      source: 'automatic',
      note: lattice
        ? 'bone stiffness placeholder for this zone (source: TODO)'
        : 'solid titanium: no lattice stiffness target',
    }
    z.requirement.strength_mpa.z = {
      value: stress,
      source: 'automatic',
      note: `peak stress of the governing load case x safety factor, x ${STRESS_SCALE} demo scaling`,
    }
    return z
  })
  table.notes = [...boundaryNotes]
  table.warnings = [
    `Demo load case: the design stresses are scaled to ${Math.round(STRESS_SCALE * 100)}% of the recorded values so that the stem zones can be lattice. At the recorded load the tip needs ${Math.round(recorded[0].stress_mpa)} MPa, more than the 76 MPa the strongest lattice reaches, so it would have to be solid.`,
  ]
  table.load.assumptions.push({
    name: 'demo stress scaling',
    value: STRESS_SCALE,
    unit: 'of the recorded design stress',
    source: 'placeholder',
    todo: true,
  } as (typeof table.load.assumptions)[number])
  return withId(table, implantId)
}

// ---- candidates -----------------------------------------------------------------------------------------------

function candidatesOf(zoneId: string) {
  const [a, b] = spans()[zoneId === 'z1' ? 0 : 1]
  const second = zoneId === 'z2'
  return {
    ...candidatesLattice,
    zone_id: zoneId,
    grid: {
      cell_mm: CELL,
      cells: [
        candidatesLattice.grid.cells[0],
        candidatesLattice.grid.cells[1],
        Math.floor((b - a) / CELL + 1e-6),
      ],
      whole_cells: Math.round(
        (candidatesLattice.grid.whole_cells * envelopeMm3(a, b)) / TEMPLATE_ENVELOPE,
      ),
    },
    job: second ? { ...candidatesLattice.job, job_id: 'j_demo_z2' } : candidatesLattice.job,
    candidates: second
      ? candidatesLattice.candidates.map((c) => ({ ...c, id: `${c.id}_z2` }))
      : candidatesLattice.candidates,
  }
}

function searchState(zoneId: string) {
  const full = candidatesOf(zoneId)
  const idx = DEMO_LATTICE_ZONES.indexOf(zoneId as (typeof DEMO_LATTICE_ZONES)[number])
  if (searchStartedAt == null || idx < 0) return { done: true as const, job: full.job }
  const elapsed = (Date.now() - searchStartedAt) / 1000 - idx * SEARCH_SECONDS
  if (elapsed >= SEARCH_SECONDS) return { done: true as const, job: full.job }
  if (elapsed < 0) {
    return {
      done: false as const,
      job: {
        job_id: full.job.job_id,
        status: 'queued' as const,
        stage: null,
        progress: 0,
        message: 'Waiting for the previous zone search to finish',
        queue_position: Math.ceil(-elapsed / SEARCH_SECONDS),
      },
    }
  }
  const p = elapsed / SEARCH_SECONDS
  return {
    done: false as const,
    job: {
      job_id: full.job.job_id,
      status: 'running' as const,
      stage: 'search',
      progress: Math.min(0.99, p),
      message:
        SEARCH_STAGES[Math.min(SEARCH_STAGES.length - 1, Math.floor(p * SEARCH_STAGES.length))],
      queue_position: null,
    },
  }
}

// ---- assembled result ---------------------------------------------------------------------------------------

const templatePart = result.parts.find((p) => p.kind === 'lattice')!
const solidNeckPart = result.parts.find((p) => p.name === 'solid neck')!
const interfacePart = result.parts.find((p) => p.kind === 'interface')!

function demoParts() {
  const s = spans()
  const lattice = [0, 1].map((i) => {
    const k = envelopeMm3(...s[i]) / TEMPLATE_ENVELOPE
    return {
      name: `lattice ${ZONE_NAMES[i]}`,
      kind: 'lattice',
      zone_ids: [`z${i + 1}`],
      triangles: Math.round(templatePart.triangles * k),
      watertight: true,
      volume_mm3: templatePart.volume_mm3 * k,
    }
  })
  const recordedNeck = recorded[3].range_mm
  const k = envelopeMm3(...s[2]) / envelopeMm3(recordedNeck[0], recordedNeck[1])
  const neck = {
    ...solidNeckPart,
    name: `solid ${ZONE_NAMES[2]}`,
    zone_ids: ['z3'],
    triangles: Math.round(solidNeckPart.triangles * k),
    volume_mm3: envelopeMm3(...s[2]),
  }
  const joints = [0, 1].map((i) => ({
    ...interfacePart,
    name: `interface at ${Math.round(boundaries[i])} mm`,
    zone_ids: [`z${i + 1}`, `z${i + 2}`],
  }))
  return [...lattice, neck, ...joints]
}

function demoSummary() {
  const s = result.summary
  const parts = demoParts()
  const volume = parts.reduce((v, p) => v + p.volume_mm3, 0)
  const triangles = parts.reduce((v, p) => v + p.triangles, 0)
  const latticeVolume = parts
    .filter((p) => p.kind === 'lattice')
    .reduce((v, p) => v + p.volume_mm3, 0)
  return {
    parts,
    summary: {
      ...s,
      volume_mm3: volume,
      mass_g: (volume * s.mass_g) / s.volume_mm3,
      triangles,
      lattice_share_pct: (latticeVolume / volume) * 100,
      stl_bytes: Math.round((triangles * s.stl_bytes) / s.triangles),
    },
  }
}

function demoResult(implantId: string) {
  const { summary, parts } = demoSummary()
  const z3 = result.zones.find((z) => z.id === 'z3')!
  const out = clone(result)
  out.summary = summary
  out.parts = parts
  out.zones = demoZoneTable(implantId).zones.map((z) => {
    const lattice = z.kind === 'lattice'
    return {
      id: z.id,
      name: z.name,
      range_mm: z.range_mm,
      kind: z.kind,
      stress_mpa: z.stress_mpa,
      requirement: z.requirement,
      candidate_id: lattice ? candidatesOf(z.id).candidates[0].id : null,
      verified: lattice ? clone(z3.verified) : null,
      check: lattice
        ? { ...clone(z3.check), zone_cells: [...candidatesOf(z.id).grid.cells] }
        : null,
    }
  }) as unknown as typeof out.zones
  return withId(out, implantId)
}

function demoReport(): string {
  const { summary } = demoSummary()
  const n = (v: number) => Math.round(v).toLocaleString('en-US')
  const share = Math.round(summary.lattice_share_pct)
  const rows = demoZoneTable('x')
    .zones.map((z) => {
      const head = `| ${z.name} | ${z.range_mm[0].toFixed(0)}-${z.range_mm[1].toFixed(0)} | ${z.kind} | ${z.stress_mpa.toFixed(0)} |`
      if (z.kind !== 'lattice') return `${head} - | - | - |`
      const c = candidatesOf(z.id).candidates[0]
      return `${head} ${c.id} | stiffness z ${c.verified.stiffness_gpa.z.toFixed(2)} GPa, strength z ${c.verified.strength_mpa.z.toFixed(1)} MPa | estimate scaled from the recorded block (beam_model_estimate) |`
    })
    .join('\n')
  const tail = report.markdown
    .slice(report.markdown.indexOf('## How to read the numbers'))
    .replace(
      /(- safety factor: [^\n]*)/,
      `$1\n- demo stress scaling: ${STRESS_SCALE} of the recorded design stress (placeholder, TODO)`,
    )
  return [
    '# Lattice Designer - implant design report',
    '',
    `> ${create.disclaimer}`,
    '',
    '## Summary',
    '',
    `- Length ${LENGTH.toFixed(1)} mm, cell size ${CELL} mm, interface plates ${summary.interface_mm} mm`,
    `- Mass about ${summary.mass_g.toFixed(1)} g (geometry only: shell volumes times the material density; overlaps counted twice, so an upper bound)`,
    `- ${share}% of the volume is lattice, ${100 - share}% solid or plate`,
    `- ${n(summary.triangles)} triangles`,
    '',
    '## Zones',
    '',
    '| zone | range (mm) | kind | stress (MPa) | candidate | solver-verified (infinite lattice) | finite-block estimate |',
    '|---|---|---|---|---|---|---|',
    rows,
    '',
    tail,
  ].join('\n')
}

// ---- the API the mock adapter calls -----------------------------------------------------------------------------

export const replay = {
  create: () => ({
    ...create,
    fields: {
      ...create.fields,
      special_rules: ['Make the stem lattice, keep the neck and taper solid'],
    },
  }),
  zones: (implantId: string) => demoZoneTable(implantId),
  /** The user moved a boundary: it snaps to the cell grid, with at least three cells in every zone. */
  editZones: (edits: { id: string; range_mm?: number[] | null }[]) => {
    const asked = [0, 1].map(
      (i) => edits.find((e) => e.id === `z${i + 1}`)?.range_mm?.[1] ?? boundaries[i],
    )
    const notes: string[] = []
    let prev = 0
    boundaries = asked.map((want, i) => {
      const lo = prev + MIN_CELLS * CELL
      const hi = LENGTH - (2 - i) * MIN_CELLS * CELL
      const snapped = Math.min(hi, Math.max(lo, Math.round(want / CELL) * CELL))
      if (Math.abs(snapped - want) > 1e-6) {
        notes.push(
          `The boundary after ${ZONE_NAMES[i]} moved from ${want.toFixed(1)} to ${snapped.toFixed(1)} mm to sit on the ${CELL} mm cell grid.`,
        )
      }
      prev = snapped
      return snapped
    })
    boundaryNotes = notes
  },
  /** The zone searches start now: they run one after another, five seconds each. */
  startSearch: () => {
    searchStartedAt = Date.now()
  },
  searchJobs: (): Record<string, string> =>
    Object.fromEntries(DEMO_LATTICE_ZONES.map((id) => [id, candidatesOf(id).job.job_id])),
  candidates: (zoneId: string) => {
    if (!(DEMO_LATTICE_ZONES as readonly string[]).includes(zoneId)) {
      const z = demoZoneTable('x').zones.find((x) => x.id === zoneId)
      return {
        zone_id: zoneId,
        kind: 'solid',
        reason: z?.reason ?? NECK_REASON,
        candidates: [],
        grid: null,
        job: null,
      }
    }
    const state = searchState(zoneId)
    const full = candidatesOf(zoneId)
    if (state.done) return full
    return {
      zone_id: zoneId,
      kind: 'lattice',
      reason: full.reason,
      candidates: [],
      grid: null,
      job: state.job,
    }
  },
  allCandidates: (): Candidate[] =>
    DEMO_LATTICE_ZONES.flatMap((id) => candidatesOf(id).candidates) as unknown as Candidate[],
  findCandidate: (id: string): Candidate | undefined =>
    replay.allCandidates().find((c) => c.id === id),
  assembleStart: () => {
    assembleStartedAt = Date.now()
    return { job_id: MOCK_ASSEMBLE_JOB_ID, status: 'queued' }
  },
  assembleJob: (implantId: string) => {
    const base = withId({ ...assembleJob, summary: demoSummary().summary }, implantId)
    if (assembleStartedAt == null) return base
    const elapsed = (Date.now() - assembleStartedAt) / 1000
    if (elapsed >= ASSEMBLE_SECONDS) return base
    const step =
      ASSEMBLE_STAGES.find((s) => elapsed < s.until) ?? ASSEMBLE_STAGES[ASSEMBLE_STAGES.length - 1]
    return {
      ...base,
      status: elapsed < 0.8 ? ('queued' as const) : ('running' as const),
      stage: step.stage,
      progress: Math.min(0.99, elapsed / ASSEMBLE_SECONDS),
      message: step.message,
    }
  },
  result: (implantId: string) => demoResult(implantId),
  report: () => demoReport(),
}
