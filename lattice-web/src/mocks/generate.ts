// Mock candidates are REAL backend output: the five stored demo searches and one real search that missed its target
// (copied by `python scripts/export_contract_fixtures.py` into fixtures/real/replay.json). Nothing here is invented.
import type { Candidate, DesignRequest } from '@/api/types'
import replayJson from '@/mocks/fixtures/real/replay.json'

interface ReplaySet {
  label: string
  request: DesignRequest
  candidates: Candidate[]
}

const SETS = replayJson as unknown as ReplaySet[]

function targets(request: DesignRequest): number[] {
  const t = request.target as unknown as Record<string, Record<string, number | null> | undefined>
  const out: number[] = []
  for (const group of ['stiffness_gpa', 'strength_mpa', 'yield_strength_mpa']) {
    for (const a of ['x', 'y', 'z']) {
      const v = t[group]?.[a]
      if (typeof v === 'number' && v > 0) out.push(v)
    }
  }
  return out
}

/** Largest log-ratio between the request and the stored set's best design, over the requested values. */
function distance(request: DesignRequest, set: ReplaySet): number {
  const best = set.candidates[0]?.verified as unknown as Record<string, Record<string, number>> | undefined
  const t = request.target as unknown as Record<string, Record<string, number | null> | undefined>
  let worst = 0
  for (const group of ['stiffness_gpa', 'strength_mpa']) {
    for (const a of ['x', 'y', 'z']) {
      const want = t[group]?.[a]
      const got = best?.[group]?.[a]
      if (typeof want === 'number' && want > 0 && typeof got === 'number' && got > 0) {
        worst = Math.max(worst, Math.abs(Math.log(got / want)))
      }
    }
  }
  return targets(request).length ? worst : 0
}

/** Replay the stored real search nearest to the request (or the real near-miss for the no_match scenario). */
export function generateCandidates(jobId: string, request: DesignRequest, scenario: string): Candidate[] {
  if (scenario === 'empty') return []
  const pool = scenario === 'no_match' ? SETS.filter((s) => s.label === 'no_match') : SETS.filter((s) => s.label !== 'no_match')
  const set = pool.reduce((best, s) => (distance(request, s) < distance(request, best) ? s : best), pool[0])
  return set.candidates.slice(0, request.n_results).map((c) => ({
    ...c,
    id: `${jobId}_${c.id.slice(c.id.indexOf('_d_') + 1)}`,
  }))
}
