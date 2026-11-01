import { useSyncExternalStore } from 'react'
import type { RecentRun } from '@/lib/storage'

let listeners: Array<() => void> = []

function subscribe(listener: () => void): () => void {
  listeners.push(listener)
  const handleStorage = (e: StorageEvent) => {
    if (e.key === 'lattice:recent-runs') {
      listener()
    }
  }
  const handleCustom = () => {
    listener()
  }
  window.addEventListener('storage', handleStorage)
  window.addEventListener('lattice:recent-runs-change', handleCustom)
  return () => {
    listeners = listeners.filter((l) => l !== listener)
    window.removeEventListener('storage', handleStorage)
    window.removeEventListener('lattice:recent-runs-change', handleCustom)
  }
}

/** Notify subscribers when recent runs change */
export function notifyRecentRuns(): void {
  listeners.forEach((l) => l())
}

const EMPTY_RUNS: RecentRun[] = []
let lastRaw: string | null = null
let lastParsed: RecentRun[] = EMPTY_RUNS

function getSnapshot(): RecentRun[] {
  if (typeof window === 'undefined') return EMPTY_RUNS
  try {
    const raw = localStorage.getItem('lattice:recent-runs')
    if (raw === lastRaw) {
      return lastParsed
    }
    lastRaw = raw
    lastParsed = raw ? (JSON.parse(raw) as RecentRun[]) : EMPTY_RUNS
    return lastParsed
  } catch {
    return EMPTY_RUNS
  }
}

function getServerSnapshot(): RecentRun[] {
  return EMPTY_RUNS
}

export function useRecentRuns(): RecentRun[] {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
}
