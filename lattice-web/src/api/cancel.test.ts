import { describe, expect, it } from 'vitest'
import { apiClient } from '@/api/client'
import { cancelJob, createDesign, getJob } from '@/api/endpoints'
import type { DesignRequest } from '@/api/types'

const REQUEST: DesignRequest = {
  material: 'ti64',
  part: { size_mm: [40, 40, 40], cell_mm: 10 },
  target: { stiffness_gpa: { x: 0.465, y: 0.496, z: 0.402 }, strength_mpa: { x: 2.22, y: 2.65, z: 2.19 }, rel_density: 0.05 },
  modes: { stiffness: 'about', strength: 'at_least', weight: 'about' },
  tolerance_pct: 10,
  n_results: 5,
}

describe('cancelJob', () => {
  it('POSTs /api/jobs/{id}/cancel and the job then reports cancelled', async () => {
    await import('@/mocks/adapter') // the client loads the mock adapter lazily; make sure it is there
    await new Promise((r) => setTimeout(r, 200))
    const { job_id } = await createDesign(REQUEST)
    const res = await cancelJob(job_id)
    expect(res.job_id).toBe(job_id)
    expect(res.status).toBe('cancelled')
    const job = await getJob(job_id)
    expect(job.status).toBe('cancelled')
    expect(apiClient.defaults.baseURL).toBeDefined()
  })
})
