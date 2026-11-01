import type {
  Candidate,
  CreateDesignResponse,
  DesignRequest,
  HealthResponse,
  Job,
  Material,
  ReachResponse,
} from '@/api/types'
import { apiClient } from '@/api/client'
import {
  candidateSchema,
  createDesignResponseSchema,
  healthSchema,
  jobSchema,
  materialsListSchema,
  reachResponseSchema,
  parseResponse,
} from '@/api/schemas'

export async function getHealth(): Promise<HealthResponse> {
  const { data } = await apiClient.get('/api/health')
  return parseResponse(healthSchema, data, 'GET /api/health')
}

export async function getMaterials(): Promise<Material[]> {
  const { data } = await apiClient.get('/api/materials')
  return parseResponse(materialsListSchema, data, 'GET /api/materials')
}

// extractLimits handles whatever comes back
export async function getLimits(material: string): Promise<unknown> {
  const { data } = await apiClient.get(`/api/limits`, { params: { material } })
  return data
}

export async function checkReach(request: DesignRequest): Promise<ReachResponse> {
  const { data } = await apiClient.post('/api/reach', request)
  return parseResponse(reachResponseSchema, data, 'POST /api/reach') as unknown as ReachResponse
}

export async function createDesign(request: DesignRequest): Promise<CreateDesignResponse> {
  const { data } = await apiClient.post('/api/designs', request)
  return parseResponse(createDesignResponseSchema, data, 'POST /api/designs')
}

export async function getJob(jobId: string): Promise<Job> {
  const { data } = await apiClient.get(`/api/jobs/${jobId}`)
  return parseResponse(jobSchema, data, `GET /api/jobs/${jobId}`) as unknown as Job
}

export async function getDesign(designId: string): Promise<Candidate> {
  const { data } = await apiClient.get(`/api/designs/${designId}`)
  return parseResponse(candidateSchema, data, `GET /api/designs/${designId}`) as unknown as Candidate
}

export interface CancelResponse {
  job_id: string
  status: string
  message?: string | null
}

/** Stop a job: a queued one at once, a running one after its current search round. Idempotent. */
export async function cancelJob(jobId: string): Promise<CancelResponse> {
  const { data } = await apiClient.post(`/api/jobs/${jobId}/cancel`)
  return data as CancelResponse
}
