import type { JobEvent } from '@/api/types'
import { API_BASE, USE_MOCK } from '@/config/env'
import { jobEventSchema, parseResponse } from '@/api/schemas'

interface JobEventHandlers {
  onEvent: (event: JobEvent) => void
  onError?: (error: Error) => void
}

/** Opens an SSE connection (real) or a mock emitter. Returns an unsubscribe function. */
export function openJobEvents(jobId: string, handlers: JobEventHandlers): () => void {
  if (USE_MOCK) {
    return openMockEvents(jobId, handlers)
  }
  return openSseEvents(jobId, handlers)
}

function openSseEvents(jobId: string, handlers: JobEventHandlers): () => void {
  const url = `${API_BASE}/api/jobs/${jobId}/events`
  const source = new EventSource(url)

  source.onmessage = (event) => {
    try {
      const raw = JSON.parse(event.data as string) as unknown
      const parsed = parseResponse(jobEventSchema, raw, 'SSE event')
      handlers.onEvent(parsed as unknown as JobEvent)
    } catch {
      // Ignore malformed events
    }
  }

  source.onerror = () => {
    source.close()
    handlers.onError?.(new Error('SSE connection lost'))
  }

  return () => source.close()
}

function openMockEvents(jobId: string, handlers: JobEventHandlers): () => void {
  let cancelled = false
  let interval: ReturnType<typeof setInterval> | null = null

  // Lazy import to avoid bundling mock code in production
  import('@/mocks/jobSim').then(({ simulateJob }) => {
    if (cancelled) return

    const startTime = getMockJobStart(jobId)
    const scenario = getMockJobScenario(jobId)
    interval = setInterval(() => {
      if (cancelled) {
        if (interval) clearInterval(interval)
        return
      }
      const elapsed = (Date.now() - startTime) / 1000
      const state = simulateJob(elapsed, scenario)
      handlers.onEvent({
        stage: state.stage,
        progress: state.progress,
        message: state.message,
      })
      if (
        state.status === 'done' ||
        state.status === 'failed' ||
        state.status === 'cancelled'
      ) {
        if (interval) clearInterval(interval)
      }
    }, 500)
  })

  return () => {
    cancelled = true
    if (interval) clearInterval(interval)
  }
}

function getMockJobStart(jobId: string): number {
  try {
    const raw = localStorage.getItem(`mock:job:${jobId}`)
    if (raw) {
      const parsed = JSON.parse(raw) as { createdAt?: number }
      if (parsed.createdAt) return parsed.createdAt
    }
  } catch {
    // Ignore
  }
  return Date.now()
}

function getMockJobScenario(jobId: string): string | undefined {
  try {
    const raw = localStorage.getItem(`mock:job:${jobId}`)
    if (raw) {
      const parsed = JSON.parse(raw) as { scenario?: string }
      return parsed.scenario
    }
  } catch {
    // Ignore
  }
  return undefined
}
