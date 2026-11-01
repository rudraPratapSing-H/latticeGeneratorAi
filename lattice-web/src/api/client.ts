import axios from 'axios'
import type { AxiosAdapter, AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import { API_BASE, ENABLE_IMPLANT, USE_MOCK } from '@/config/env'
import { MOCK_ASSEMBLE_JOB_ID, replay } from '@/mocks/implantReplay'

export class ApiError extends Error {
  code: string
  status?: number

  constructor(code: string, message: string, status?: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

function statusToCode(status: number): string {
  if (status === 404) return 'not_found'
  if (status === 422) return 'bad_target'
  if (status === 429) return 'queue_full'
  return 'unknown'
}

type MockAdapter = AxiosAdapter
let mockAdapterPromise: Promise<MockAdapter> | null = null

function loadMockAdapter(): Promise<MockAdapter> {
  mockAdapterPromise ??= import('@/mocks/adapter').then(
    ({ mockAdapter }) => mockAdapter as unknown as MockAdapter,
  )
  return mockAdapterPromise
}

// The implant demo always runs on the stored implant data, even when the rest of the app talks to the real backend.
const IMPLANT_DESIGN_IDS = new Set<string>(ENABLE_IMPLANT ? replay.allCandidates().map((c) => c.id) : [])

function isImplantDemoRequest(config: InternalAxiosRequestConfig): boolean {
  if (!ENABLE_IMPLANT) return false
  const url = (config.url ?? '').split('?')[0]
  if (/^\/api\/implants(\/|$)/.test(url)) return true
  if (url === `/api/jobs/${MOCK_ASSEMBLE_JOB_ID}`) return true
  const design = url.match(/^\/api\/designs\/([^/]+)$/)
  return !!design && IMPLANT_DESIGN_IDS.has(design[1])
}

function createClient(): AxiosInstance {
  const instance = axios.create({
    baseURL: API_BASE,
    timeout: 15_000,
    headers: { 'Content-Type': 'application/json' },
  })

  // Mock mode sends every request to the mock adapter; in real mode only the implant demo requests go there.
  if (USE_MOCK || ENABLE_IMPLANT) {
    instance.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
      if (USE_MOCK || isImplantDemoRequest(config)) {
        config.adapter = await loadMockAdapter()
      }
      return config
    })
  }

  // Error normalisation interceptor
  instance.interceptors.response.use(
    (response) => response,
    (error) => {
      if (axios.isAxiosError(error)) {
        // Backend structured error
        const body = error.response?.data as
          | { error?: { code?: string; message?: string } }
          | undefined
        if (body?.error?.code && body?.error?.message) {
          throw new ApiError(body.error.code, body.error.message, error.response?.status)
        }

        // No response / timeout / network
        if (!error.response) {
          throw new ApiError(
            'network_error',
            'Can\u2019t reach the Lattice Designer service.',
          )
        }

        // Status-based fallback
        const code = statusToCode(error.response.status)
        throw new ApiError(
          code,
          error.response?.statusText ?? 'An unexpected error occurred.',
          error.response?.status,
        )
      }

      throw new ApiError('unknown', 'An unexpected error occurred.')
    },
  )

  return instance
}

export const apiClient = createClient()
