// Contract test for the implant endpoints: real backend output (recorded by scripts/run_implant_case.py with the real
// solver) must pass the zod schemas, and must not contain NaN or non-finite numbers anywhere.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { z } from 'zod/v4'
import {
  assembleJobSchema,
  createImplantSchema,
  implantResultSchema,
  zoneCandidatesSchema,
  zoneTableSchema,
} from '@/api/implantSchemas'

const here = path.dirname(fileURLToPath(import.meta.url))
const FIX = path.resolve(here, '../mocks/fixtures/real/implant')
const read = (name: string): unknown => JSON.parse(fs.readFileSync(path.join(FIX, `${name}.json`), 'utf8'))

function ok<T extends z.ZodType>(schema: T, data: unknown, label: string): z.infer<T> {
  const r = schema.safeParse(data)
  if (!r.success) throw new Error(`${label} does not match the schema:\n${z.prettifyError(r.error)}`)
  return r.data
}

function allFinite(x: unknown): boolean {
  if (typeof x === 'number') return Number.isFinite(x)
  if (Array.isArray(x)) return x.every(allFinite)
  if (x && typeof x === 'object') return Object.values(x).every(allFinite)
  return true
}

describe('implant responses from the real backend pass the frontend schemas', () => {
  it('POST /api/implants', () => void ok(createImplantSchema, read('create'), 'create'))

  it('zone table (confirm, GET and PUT /zones)', () => {
    const t = ok(zoneTableSchema, read('zones'), 'zones')
    expect(t.zones.length).toBeGreaterThanOrEqual(2)
    expect(t.zones.some((x) => x.kind === 'lattice')).toBe(true)
    expect(t.zones.every((x) => x.kind !== 'solid' || !!x.reason)).toBe(true)
  })

  it('zone candidates: a lattice zone with solver-verified candidates, and a solid zone with none', () => {
    const lat = ok(zoneCandidatesSchema, read('candidates_z3'), 'candidates_z3')
    expect(lat.candidates.length).toBeGreaterThan(0)
    expect(lat.job?.status).toBe('done')
    const solid = ok(zoneCandidatesSchema, read('candidates_solid'), 'candidates_solid')
    expect(solid.candidates).toEqual([])
    expect(solid.reason).toBeTruthy()
  })

  it('assemble job', () => void ok(assembleJobSchema, read('assemble_job'), 'assemble_job'))

  it('result: every number is labelled and the mass is geometry only', () => {
    const r = ok(implantResultSchema, read('result'), 'result')
    expect(r.zones.some((x) => x.verified && x.check)).toBe(true)
    expect(r.parts.every((p) => p.watertight)).toBe(true)
  })

  it('no fixture contains a non-finite number', () => {
    for (const n of ['create', 'zones', 'candidates_z3', 'candidates_solid', 'assemble_job', 'result']) {
      expect(allFinite(read(n)), n).toBe(true)
    }
  })

  it('no fixture makes a clinical claim', () => {
    const text = ['create', 'zones', 'result'].map((n) => JSON.stringify(read(n))).join(' ').toLowerCase()
    for (const bad of ['fda', 'ce mark', 'clinically proven', 'safe for patients', 'approved for']) expect(text).not.toContain(bad)
  })
})
