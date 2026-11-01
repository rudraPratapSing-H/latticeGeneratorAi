// Mock mode must answer in the same shape as the real backend, so the app never works only against its own mock.
import { describe, expect, it } from 'vitest'
import type { InternalAxiosRequestConfig } from 'axios'
import { mockAdapter } from '@/mocks/adapter'
import { createDesignResponseSchema, jobSchema, materialsListSchema, reachResponseSchema } from '@/api/schemas'
import { extractLimits } from '@/config/limits'
import realLimits from '@/mocks/fixtures/real/limits.json'

const call = (method: string, url: string, data?: unknown, params?: unknown) =>
  mockAdapter({ method, url, data: data === undefined ? undefined : JSON.stringify(data), params } as unknown as InternalAxiosRequestConfig)

const REQUEST = {
  material: 'ti64',
  part: { size_mm: [40, 40, 40], cell_mm: 10 },
  target: { stiffness_gpa: { x: 0.465, y: 0.496, z: 0.402 }, strength_mpa: { x: 2.22, y: 2.65, z: 2.19 }, rel_density: 0.05 },
  modes: { stiffness: 'about', strength: 'at_least', weight: 'about' },
  tolerance_pct: 10,
  n_results: 5,
}

describe('mock responses have the real backend shape', () => {
  it('GET /api/materials lists only what the backend has', async () => {
    const r = await call('get', '/api/materials')
    const mats = materialsListSchema.parse(r.data)
    expect(mats.map((m) => m.id)).toEqual(['ti64'])
  })
  it('GET /api/limits is the real response, readable by extractLimits', async () => {
    const r = await call('get', '/api/limits', undefined, { material: 'ti64' })
    expect(r.data).toEqual(realLimits)
    expect(Object.keys(extractLimits(r.data)!.densities)).toEqual(['0.05', '0.15', '0.25'])
  })
  it('POST /api/reach validates against the reach schema', async () => {
    const r = await call('post', '/api/reach', REQUEST)
    reachResponseSchema.parse(r.data)
  })
  it('POST /api/designs then GET /api/jobs/{id} validate against the job schema', async () => {
    const created = await call('post', '/api/designs', REQUEST)
    const { job_id } = createDesignResponseSchema.parse(created.data)
    const job = await call('get', `/api/jobs/${job_id}`)
    const parsed = jobSchema.parse(job.data)
    expect(parsed.job_id).toBe(job_id)
  })
})
