// Contract test: everything the REAL backend sends must pass the frontend's zod schemas.
// Fixtures come from `python scripts/export_contract_fixtures.py` (backend serializers) and the repo's demo/ and mock/
// folders (real solver output). Nothing here is typed by hand.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { z } from 'zod/v4'
import {
  candidateSchema,
  createDesignResponseSchema,
  healthSchema,
  jobEventSchema,
  jobSchema,
  materialsListSchema,
  reachResponseSchema,
} from '@/api/schemas'
import { extractLimits } from '@/config/limits'

const here = path.dirname(fileURLToPath(import.meta.url))
const FIX = path.resolve(here, '../test/fixtures/backend')
const REPO = path.resolve(here, '../../..')

const read = (name: string): unknown => JSON.parse(fs.readFileSync(path.join(FIX, `${name}.json`), 'utf8'))

function ok(schema: z.ZodType, data: unknown, label: string) {
  const r = schema.safeParse(data)
  if (!r.success) throw new Error(`${label} does not match the schema:\n${z.prettifyError(r.error)}`)
  return r.data
}

describe('backend responses pass the frontend schemas', () => {
  it('GET /api/health', () => {
    const h = ok(healthSchema, read('health'), 'health') as Record<string, unknown>
    expect(h).toHaveProperty('solver_workers')
    expect(h).toHaveProperty('reason')
  })
  it('GET /api/materials', () => void ok(materialsListSchema, read('materials'), 'materials'))
  it('POST /api/reach (covered and infeasible)', () => {
    ok(reachResponseSchema, read('reach_covered'), 'reach_covered')
    ok(reachResponseSchema, read('reach_infeasible'), 'reach_infeasible')
  })
  it('POST /api/designs', () => void ok(createDesignResponseSchema, read('create_design'), 'create_design'))
  it.each(['job_queued', 'job_running', 'job_done', 'job_cancelled', 'job_failed', 'job_no_match'])(
    'GET /api/jobs/{id} (%s)',
    (name) => void ok(jobSchema, read(name), name),
  )
  it('GET /api/designs/{id}', () => void ok(candidateSchema, read('design'), 'design'))
})

describe('error bodies use {error: {code, message}}', () => {
  it.each([
    ['error_422_infeasible', 'bad_target'],
    ['error_422_schema', 'bad_target'],
    ['error_422_unit_hint', 'bad_target'],
    ['error_422_unknown_material', 'unknown_material'],
    ['error_404', 'not_found'],
    ['error_429', 'queue_full'],
  ])('%s', (name, code) => {
    const body = read(name) as { error: { code: string; message: string } }
    expect(body.error.code).toBe(code)
    expect(typeof body.error.message).toBe('string')
  })
  it('the infeasible 422 carries the picker result the form needs', () => {
    const body = read('error_422_infeasible') as { error: { reach: unknown } }
    ok(reachResponseSchema, body.error.reach, 'error.reach')
  })
})

describe('GET /api/limits', () => {
  it('extractLimits reads the real shape: three densities keyed 0.05/0.15/0.25 and the real maxima', () => {
    const ex = extractLimits(read('limits'))
    expect(ex).toBeTruthy()
    expect(Object.keys(ex!.densities)).toEqual(['0.05', '0.15', '0.25'])
    expect(ex!.strength_max_mpa).toBeCloseTo(76.1, 1)
    expect(ex!.stiffness_sum_max_gpa).toBeCloseTo(28.5, 1)
    expect(ex!.densities['0.25'].stiffness_gpa.max).toBeCloseTo(13.15, 1)
  })
})

describe('server-sent events', () => {
  const text = fs.readFileSync(path.join(FIX, 'sse_transcript.txt'), 'utf8')
  const blocks = text.split(/\r?\n\r?\n/).filter(Boolean)
  it('ping comments are ignorable and every data frame is a valid event', () => {
    const data = blocks.filter((b) => b.startsWith('data:'))
    expect(data.length).toBeGreaterThan(2)
    expect(blocks.some((b) => b.startsWith(': ping'))).toBe(true)
    for (const b of data) ok(jobEventSchema, JSON.parse(b.slice(5).trim()), `SSE frame ${b.slice(0, 60)}`)
  })
  it('ends with a named close event carrying the final status', () => {
    const close = blocks.find((b) => b.startsWith('event: close'))
    expect(close).toBeTruthy()
    expect(JSON.parse(close!.split('\n').find((l) => l.startsWith('data:'))!.slice(5)).status).toBe('done')
  })
})

describe('stored real results (demo/ and mock/)', () => {
  const demo = path.join(REPO, 'demo')
  const jobs = fs.existsSync(path.join(demo, 'jobs')) ? fs.readdirSync(path.join(demo, 'jobs')) : []
  it('five demo jobs exist', () => expect(jobs.length).toBe(5))
  it.each(jobs)('demo %s results are valid candidates', (id) => {
    const cands = JSON.parse(fs.readFileSync(path.join(demo, 'jobs', id, 'results.json'), 'utf8')) as unknown[]
    expect(cands.length).toBeGreaterThan(0)
    cands.forEach((c, i) => ok(candidateSchema, c, `${id}[${i}]`))
  })
  it('mock/job_done.json is a valid job', () => {
    ok(jobSchema, JSON.parse(fs.readFileSync(path.join(REPO, 'mock', 'job_done.json'), 'utf8')), 'mock/job_done.json')
  })
})
