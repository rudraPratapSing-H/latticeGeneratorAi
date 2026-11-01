import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import type { DesignRequest, Job } from '@/api/types'
import { getMockScenario } from '@/lib/storage'
import { simulateJob } from '@/mocks/jobSim'
import { generateCandidates } from '@/mocks/generate'
import { mockReach } from '@/mocks/reachSim'
import { mockLimits } from '@/mocks/limitsSim'
import { replay, MOCK_ASSEMBLE_JOB_ID } from '@/mocks/implantReplay'
import materialsFixture from '@/mocks/fixtures/real/materials.json'

/** Artificial latency in ms */
const LATENCY_MIN = 200
const LATENCY_MAX = 500

function delay(): Promise<void> {
  const ms = LATENCY_MIN + Math.random() * (LATENCY_MAX - LATENCY_MIN)
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function makeResponse<T>(data: T, status = 200): AxiosResponse<T> {
  return {
    data,
    status,
    statusText: status === 200 ? 'OK' : status === 202 ? 'Accepted' : 'Error',
    headers: {},
    config: {} as InternalAxiosRequestConfig,
  }
}

function makeErrorResponse(status: number, code: string, message: string): never {
  const error = new Error(message) as Error & {
    response: AxiosResponse
    isAxiosError: boolean
  }
  error.response = makeResponse({ error: { code, message } }, status)
  error.isAxiosError = true
  throw error
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

function generateJobId(): string {
  return 'j_' + Math.random().toString(36).slice(2, 8)
}

/** Custom axios adapter for mock mode */
export async function mockAdapter(config: InternalAxiosRequestConfig): Promise<AxiosResponse> {
  const scenario = getMockScenario()

  // Simulate offline
  if (scenario === 'offline') {
    await delay()
    const error = new Error('Can\u2019t reach the Lattice Designer service.') as Error & {
      isAxiosError: boolean
      response: undefined
    }
    error.isAxiosError = true
    error.response = undefined
    throw error
  }

  // queue_full scenario for POST /api/designs
  if (scenario === 'queue_full') {
    const url = config.url ?? ''
    const method = (config.method ?? 'get').toLowerCase()
    if (method === 'post' && /\/api\/designs$/.test(url)) {
      await delay()
      makeErrorResponse(429, 'queue_full', 'The queue is full. Try again in a minute.')
    }
  }

  await delay()

  const url = config.url ?? ''
  const method = (config.method ?? 'get').toLowerCase()

  // GET /api/health
  if (method === 'get' && /\/api\/health$/.test(url)) {
    return makeResponse({ status: 'ok', model_loaded: true, gpu: true })
  }

  // GET /api/materials
  if (method === 'get' && /\/api\/materials$/.test(url)) {
    return makeResponse(materialsFixture)
  }

  // GET /api/limits
  if (method === 'get' && /\/api\/limits/.test(url)) {
    const params = config.params as Record<string, string> | undefined
    const materialId = params?.material ?? 'ti64'
    if (!(materialsFixture as Array<{ id: string }>).some((m) => m.id === materialId)) {
      makeErrorResponse(422, 'unknown_material', `unknown material '${materialId}'`)
    }
    return makeResponse(mockLimits())
  }

  // POST /api/reach
  if (method === 'post' && /\/api\/reach$/.test(url)) {
    const request = parseBody<DesignRequest>(config)
    const material = (materialsFixture as Array<{ id: string; E_gpa: number; yield_mpa: number; density_g_cm3: number }>)
      .find((m) => m.id === request.material)
    const result = mockReach(request, material ?? { E_gpa: 114, yield_mpa: 880, density_g_cm3: 4.43 })
    if (result.error) {
      makeErrorResponse(result.error.status, result.error.code, result.error.message)
    }
    return makeResponse(result.response)
  }

  // POST /api/designs
  if (method === 'post' && /\/api\/designs$/.test(url)) {
    if (scenario === 'bad_target') {
      makeErrorResponse(
        422,
        'bad_target',
        'Target stiffness is above the physical bound for this density.',
      )
    }

    const request = parseBody<DesignRequest>(config)
    const jobId = generateJobId()

    try {
      localStorage.setItem(
        `mock:job:${jobId}`,
        JSON.stringify({ createdAt: Date.now(), request, scenario }),
      )
    } catch {
      // Ignore
    }

    return makeResponse({ job_id: jobId }, 202)
  }

  // POST /api/jobs/:id/cancel
  const cancelMatch = url.match(/\/api\/jobs\/([^/]+)\/cancel$/)
  if (method === 'post' && cancelMatch) {
    const jobId = cancelMatch[1]
    const stored = getStoredJob(jobId)
    try {
      localStorage.setItem(
        `mock:job:${jobId}`,
        JSON.stringify({ ...stored, scenario: 'cancelled', cancelledAt: Date.now() }),
      )
    } catch {
      // Ignore
    }
    await delay()
    return makeResponse({ job_id: jobId, status: 'cancelled', message: 'Cancelled.' })
  }

  // GET /api/jobs/:id
  const jobMatch = url.match(/\/api\/jobs\/([^/]+)$/)
  if (method === 'get' && jobMatch && jobMatch[1] === MOCK_ASSEMBLE_JOB_ID) {
    return makeResponse(replay.assembleJob('i_mock'))
  }
  if (method === 'get' && jobMatch) {
    const jobId = jobMatch[1]
    const stored = getStoredJob(jobId)
    const jobScenario = stored.scenario ?? scenario

    const elapsed = (Date.now() - stored.createdAt) / 1000
    const state = stored.cancelledAt
      ? { ...simulateJob(elapsed, 'cancelled'), status: 'cancelled' as const, message: 'Cancelled.' }
      : simulateJob(elapsed, jobScenario)

    const candidates =
      state.status === 'done'
        ? generateCandidates(jobId, stored.request, jobScenario)
        : []

    const job: Job = {
      job_id: jobId,
      status: state.status,
      stage: state.stage,
      round: state.round,
      k: state.k,
      progress: state.progress,
      message: state.message,
      rounds: state.rounds,
      infeasible: false,
      warnings: state.warnings,
      reach: state.reach,
      candidates,
      queue_position: state.queue_position,
      request: stored.request,
    }

    return makeResponse(job)
  }

  // GET /api/jobs/:id/events — not handled by adapter (SSE uses the mock emitter)
  if (method === 'get' && /\/api\/jobs\/[^/]+\/events$/.test(url)) {
    return makeResponse({ message: 'Use SSE' })
  }

  // GET /api/designs/:id
  const designMatch = url.match(/\/api\/designs\/([^/]+)$/)
  if (method === 'get' && designMatch) {
    const designId = designMatch[1]
    const candidate = findCandidate(designId)
    if (!candidate) {
      makeErrorResponse(404, 'not_found', 'Design not found')
    }
    return makeResponse(candidate)
  }

  // --- Implant API (replays real backend output; see mocks/implantReplay.ts) ---
  if (method === 'post' && /\/api\/implants$/.test(url)) {
    await sleep(1800) // reading the file and analysing the mesh
    return makeResponse(replay.create(), 201)
  }
  const implantUrl = url.match(/\/api\/implants\/([^/]+)(\/.*)?$/)
  if (implantUrl) {
    const id = implantUrl[1]
    const rest = implantUrl[2] ?? ''
    if (method === 'post' && rest === '/confirm') {
      await sleep(1400) // zoning the stem and computing the design stress
      return makeResponse(replay.zones(id))
    }
    if (rest === '/zones' && method === 'put') {
      await sleep(400)
      replay.editZones(parseBody<{ zones: { id: string; range_mm?: number[] | null }[] }>(config).zones)
    }
    if (rest === '/zones' && (method === 'get' || method === 'put')) return makeResponse(replay.zones(id))
    if (method === 'post' && rest === '/search') {
      await sleep(800)
      replay.startSearch()
      return makeResponse(replay.searchJobs())
    }
    if (method === 'post' && rest === '/parse') {
      await sleep(1000)
      const c = replay.create()
      return makeResponse({ fields: c.fields, parsed_by: c.parsed_by, parse_notes: c.parse_notes, gemini_configured: false })
    }
    const cand = rest.match(/^\/zones\/([^/]+)\/candidates$/)
    if (method === 'get' && cand) return makeResponse(replay.candidates(cand[1]))
    if (method === 'post' && rest === '/assemble') {
      await sleep(600)
      return makeResponse(replay.assembleStart(), 202)
    }
    if (method === 'get' && rest === '/result') {
      await sleep(900)
      return makeResponse(replay.result(id))
    }
    if (method === 'get' && rest === '/report') return makeResponse(replay.report())
    if (method === 'get' && rest === '/export.stl') {
      return makeErrorResponse(404, 'not_found', 'The STL file is only available with the real backend (this is replayed data).')
    }
  }

  makeErrorResponse(404, 'not_found', 'Not found')
}

function parseBody<T>(config: InternalAxiosRequestConfig): T {
  return (typeof config.data === 'string' ? JSON.parse(config.data) : config.data) as T
}

interface StoredJob {
  createdAt: number
  request: DesignRequest
  scenario?: string
  cancelledAt?: number
}

function getStoredJob(jobId: string): StoredJob {
  try {
    const raw = localStorage.getItem(`mock:job:${jobId}`)
    if (raw) {
      return JSON.parse(raw) as StoredJob
    }
  } catch {
    // Ignore
  }

  // Fallback: create a default job
  const fallback: StoredJob = {
    createdAt: Date.now() - 15000,
    request: {
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
    },
  }

  try {
    localStorage.setItem(`mock:job:${jobId}`, JSON.stringify(fallback))
  } catch {
    // Ignore
  }

  return fallback
}

function findCandidate(designId: string) {
  const scenario = getMockScenario()

  // 1. Check all stored mock jobs
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i)
    if (!key?.startsWith('mock:job:')) continue
    const jobId = key.replace('mock:job:', '')
    const stored = getStoredJob(jobId)
    const candidates = generateCandidates(jobId, stored.request, stored.scenario ?? scenario)
    const found = candidates.find((c) => c.id === designId)
    if (found) return found
  }

  // 2. Candidates of the replayed implant zone search
  const zoneFound = replay.findCandidate(designId)
  if (zoneFound) return zoneFound

  // 3. Fallback: generate deterministic candidate for the requested design ID so it never 404s
  const fallbackReq: DesignRequest = {
    material: 'ti64',
    part: { size_mm: [30, 30, 30], cell_mm: 5 },
    target: {
      stiffness_gpa: { x: 8, y: 8, z: 12 },
      strength_mpa: { x: 80, y: 80, z: 100 },
      rel_density: 0.15,
    },
    modes: { stiffness: 'about', strength: 'at_least', weight: 'at_most' },
    tolerance_pct: 10,
    n_results: 5,
  }
  const fallbackCandidates = generateCandidates(designId, fallbackReq, 'success')
  const matched = fallbackCandidates[0]
  if (matched) {
    return { ...matched, id: designId }
  }

  return null
}
