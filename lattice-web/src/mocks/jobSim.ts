import type { JobStage, JobStatus, ReachLevel, RoundInfo } from '@/api/types'
import { getMockScenario } from '@/lib/storage'

interface SimState {
  status: JobStatus
  stage: JobStage | undefined
  progress: number
  message: string
  round?: number
  k?: number
  rounds?: RoundInfo[]
  warnings?: string[]
  reach?: { level: ReachLevel; distance_pct: number }
  queue_position?: number
}

/**
 * Compute job state purely from elapsed seconds since creation.
 * Deterministic and survives page refresh.
 */
export function simulateJob(elapsedSec: number, scenarioOverride?: string): SimState {
  const scenario = scenarioOverride ?? getMockScenario()

  // --- Offline ---
  if (scenario === 'offline') {
    return { status: 'running', stage: 'search', progress: 0, message: 'Connecting…' }
  }

  // --- Cancelled ---
  if (scenario === 'cancelled') {
    if (elapsedSec < 1) {
      return { status: 'queued', stage: undefined, progress: 0, message: 'Waiting in queue' }
    }
    return { status: 'cancelled', stage: 'search', progress: 0.2, message: 'This run was cancelled.' }
  }

  // --- Queued long ---
  if (scenario === 'queued_long') {
    if (elapsedSec < 30) {
      const pos = Math.max(1, 3 - Math.floor(elapsedSec / 10))
      return {
        status: 'queued',
        stage: undefined,
        progress: 0,
        message: 'Waiting in queue',
        queue_position: pos,
      }
    }
    // After 30s, run as success
    return simulateJob(elapsedSec - 30, 'success')
  }

  // --- Fail ---
  if (scenario === 'fail') {
    if (elapsedSec < 1) {
      return { status: 'queued', stage: undefined, progress: 0, message: 'Waiting in queue' }
    }
    if (elapsedSec < 5) {
      const p = ((elapsedSec - 1) / 4) * 0.4
      return {
        status: 'running',
        stage: 'search',
        progress: p,
        round: 1,
        k: 100,
        message: `Round 1 of up to 3: checking ${Math.floor(p * 400)} of 400 designs`,
      }
    }
    if (elapsedSec < 7) {
      const p = 0.4 + ((elapsedSec - 5) / 2) * 0.18
      return {
        status: 'running',
        stage: 'repair',
        progress: p,
        round: 1,
        k: 100,
        rounds: [buildRound(1, 100, 11.8, false, 240, 4)],
        message: `Repairing invalid lattices (${Math.floor(((elapsedSec - 5) / 2) * 48)} of 48)`,
      }
    }
    return {
      status: 'failed',
      stage: 'verify',
      progress: 0.58,
      round: 1,
      k: 100,
      rounds: [buildRound(1, 100, 11.8, false, 240, 4)],
      message: 'Solver crashed on candidate 212',
    }
  }

  // --- Restart fail ---
  if (scenario === 'restart_fail') {
    if (elapsedSec < 1) {
      return { status: 'queued', stage: undefined, progress: 0, message: 'Waiting in queue' }
    }
    return {
      status: 'failed',
      stage: 'search',
      progress: 0.1,
      message: 'restart',
    }
  }

  // --- Success / No match / Empty / Multi-round / Slow ---
  const isMultiRound = scenario === 'multi_round'
  const isSlow = scenario === 'slow'
  const totalTime = isSlow ? 35 : isMultiRound ? 45 : 12

  // Queue phase
  if (elapsedSec < 1) {
    return { status: 'queued', stage: undefined, progress: 0, message: 'Waiting in queue' }
  }

  // Done
  if (elapsedSec >= totalTime) {
    const rounds: RoundInfo[] = [buildRound(1, 100, 8.2, !isMultiRound, 240, 10.1)]
    if (isMultiRound || isSlow) {
      rounds.push(buildRound(2, 300, 4.1, !isSlow, 180, 30))
    }
    if (isSlow) {
      rounds.push(buildRound(3, 1000, 2.9, true, 420, 90))
    }

    return {
      status: 'done',
      stage: 'rank',
      progress: 1,
      message: 'Completed',
      rounds,
      reach: { level: 'covered', distance_pct: 3.2 },
      warnings: [],
    }
  }

  // Running — compute current phase
  const runTime = elapsedSec - 1
  const runTotal = totalTime - 1

  // Multi-round: split into rounds
  if (isMultiRound || isSlow) {
    return simulateMultiRound(runTime, runTotal, isMultiRound ? 2 : 3)
  }

  // Single round
  return simulateSingleRound(runTime, runTotal)
}

function simulateSingleRound(runTime: number, runTotal: number): SimState {
  const frac = runTime / runTotal
  const rounds: RoundInfo[] = []

  if (frac < 0.45) {
    const count = Math.floor((frac / 0.45) * 400)
    return {
      status: 'running',
      stage: 'search',
      progress: frac,
      round: 1,
      k: 100,
      message: `Round 1 of up to 3: checking ${count} of 400 designs`,
    }
  }

  rounds.push(buildRound(1, 100, 8.2, false, 240, runTotal * 0.45))

  if (frac < 0.58) {
    const count = Math.floor(((frac - 0.45) / 0.13) * 48)
    return {
      status: 'running',
      stage: 'repair',
      progress: frac,
      round: 1,
      k: 100,
      rounds,
      message: `Repairing invalid lattices (${count} of 48)`,
    }
  }

  if (frac < 0.92) {
    const count = Math.floor(((frac - 0.58) / 0.34) * 400)
    return {
      status: 'running',
      stage: 'verify',
      progress: frac,
      round: 1,
      k: 100,
      rounds,
      message: `Verified ${count} of 400 candidates`,
    }
  }

  return {
    status: 'running',
    stage: 'rank',
    progress: frac,
    round: 1,
    k: 100,
    rounds,
    message: 'Ranking by match error',
  }
}

function simulateMultiRound(runTime: number, runTotal: number, maxRounds: number): SimState {
  const roundDurations = maxRounds === 2 ? [0.35, 0.65] : [0.2, 0.4, 0.4]
  const rounds: RoundInfo[] = []
  const kValues = [100, 300, 1000]
  let elapsed = 0

  for (let r = 0; r < maxRounds; r++) {
    const roundLen = runTotal * roundDurations[r]
    const roundStart = elapsed
    const roundEnd = elapsed + roundLen

    if (runTime < roundEnd) {
      const localFrac = (runTime - roundStart) / roundLen
      // Within this round
      if (localFrac < 0.45) {
        const count = Math.floor((localFrac / 0.45) * (kValues[r] * 4))
        return {
          status: 'running',
          stage: 'search',
          progress: runTime / runTotal,
          round: r + 1,
          k: kValues[r],
          rounds: rounds.length > 0 ? rounds : undefined,
          message: `Round ${r + 1} of up to ${maxRounds}: checking ${count} of ${kValues[r] * 4} designs`,
        }
      }
      if (localFrac < 0.58) {
        const count = Math.floor(((localFrac - 0.45) / 0.13) * 48)
        return {
          status: 'running',
          stage: 'repair',
          progress: runTime / runTotal,
          round: r + 1,
          k: kValues[r],
          rounds: rounds.length > 0 ? rounds : undefined,
          message: `Repairing invalid lattices (${count} of 48)`,
        }
      }
      if (localFrac < 0.92) {
        const count = Math.floor(((localFrac - 0.58) / 0.34) * (kValues[r] * 4))
        return {
          status: 'running',
          stage: 'verify',
          progress: runTime / runTotal,
          round: r + 1,
          k: kValues[r],
          rounds: rounds.length > 0 ? rounds : undefined,
          message: `Verified ${count} of ${kValues[r] * 4} candidates`,
        }
      }
      return {
        status: 'running',
        stage: 'rank',
        progress: runTime / runTotal,
        round: r + 1,
        k: kValues[r],
        rounds: rounds.length > 0 ? rounds : undefined,
        message: 'Ranking by match error',
      }
    }

    rounds.push(buildRound(r + 1, kValues[r], 8 - r * 3, false, 240 + r * 60, roundLen))
    elapsed = roundEnd
  }

  // Past all rounds
  return {
    status: 'running',
    stage: 'rank',
    progress: 0.98,
    round: maxRounds,
    k: kValues[maxRounds - 1],
    rounds,
    message: 'Finalising results',
  }
}

function buildRound(
  round: number,
  k: number,
  bestErr: number,
  matched: boolean,
  nCandidates: number,
  seconds: number,
): RoundInfo {
  return {
    round,
    k,
    best_error_pct: bestErr,
    matched,
    n_candidates: nCandidates,
    round_seconds: Math.round(seconds * 10) / 10,
    elapsed_seconds: Math.round(seconds * 10) / 10,
  }
}
