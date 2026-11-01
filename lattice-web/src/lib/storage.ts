import type { DesignRequest } from '@/api/types'

const STORAGE_PREFIX = 'lattice:'

/** Save a design request keyed by job ID with optional frontend metadata */
export function saveRequest(
  jobId: string,
  request: DesignRequest,
  metadata?: { adjustedFields?: string[] },
): void {
  try {
    const payload = metadata ? { ...request, _metadata: metadata } : request
    localStorage.setItem(`${STORAGE_PREFIX}request:${jobId}`, JSON.stringify(payload))
  } catch {
    // Storage full or unavailable
  }
}

/** Load a saved design request by job ID */
export function loadRequest(
  jobId: string,
): (DesignRequest & { _metadata?: { adjustedFields?: string[] } }) | null {
  try {
    const raw = localStorage.getItem(`${STORAGE_PREFIX}request:${jobId}`)
    if (!raw) return null
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export interface RecentRun {
  jobId: string
  material: string
  summary: string
  timestamp: number
}

const RECENT_KEY = `${STORAGE_PREFIX}recent-runs`
const MAX_RECENT = 8

/** Add a run to the recent runs list */
export function addRecentRun(run: RecentRun): void {
  try {
    const runs = getRecentRuns()
    const filtered = runs.filter((r) => r.jobId !== run.jobId)
    filtered.unshift(run)
    localStorage.setItem(RECENT_KEY, JSON.stringify(filtered.slice(0, MAX_RECENT)))
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('lattice:recent-runs-change'))
    }
  } catch {
    // Ignore
  }
}

/** Get all recent runs */
export function getRecentRuns(): RecentRun[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    if (!raw) return []
    return JSON.parse(raw) as RecentRun[]
  } catch {
    return []
  }
}

/** Clear all mock data from localStorage */
export function clearMockData(): void {
  try {
    const keys: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key?.startsWith('mock:')) keys.push(key)
    }
    keys.forEach((k) => localStorage.removeItem(k))
  } catch {
    // Ignore
  }
}

/** Get/set mock scenario */
export function getMockScenario(): string {
  try {
    return localStorage.getItem('mock:scenario') ?? 'success'
  } catch {
    return 'success'
  }
}

export function setMockScenario(scenario: string): void {
  try {
    localStorage.setItem('mock:scenario', scenario)
  } catch {
    // Ignore
  }
}
