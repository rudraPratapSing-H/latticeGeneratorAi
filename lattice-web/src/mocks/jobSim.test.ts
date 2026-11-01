import { describe, it, expect } from 'vitest'
import { simulateJob } from '@/mocks/jobSim'

describe('simulateJob', () => {
  it('returns queued state during first second', () => {
    const state = simulateJob(0.5, 'success')
    expect(state.status).toBe('queued')
    expect(state.progress).toBe(0)
    expect(state.message).toBe('Waiting in queue')
  })

  it('progresses through search, repair, verify, and rank stages monotonically', () => {
    const s1 = simulateJob(2, 'success')
    const s2 = simulateJob(6, 'success')
    const s3 = simulateJob(9, 'success')
    const s4 = simulateJob(11.5, 'success')
    const s5 = simulateJob(13, 'success')

    expect(s1.status).toBe('running')
    expect(s1.stage).toBe('search')

    expect(s2.status).toBe('running')
    expect(s2.stage).toBe('repair')

    expect(s3.status).toBe('running')
    expect(s3.stage).toBe('verify')

    expect(s4.status).toBe('running')
    expect(s4.stage).toBe('rank')

    expect(s5.status).toBe('done')
    expect(s5.progress).toBe(1)

    // Monotonic progress
    expect(s2.progress).toBeGreaterThan(s1.progress)
    expect(s3.progress).toBeGreaterThan(s2.progress)
    expect(s4.progress).toBeGreaterThan(s3.progress)
    expect(s5.progress).toBeGreaterThanOrEqual(s4.progress)
  })

  it('handles fail scenario at verify stage', () => {
    const state = simulateJob(8, 'fail')
    expect(state.status).toBe('failed')
    expect(state.stage).toBe('verify')
    expect(state.message).toContain('Solver crashed on candidate 212')
  })

  it('handles cancelled scenario', () => {
    const state = simulateJob(3, 'cancelled')
    expect(state.status).toBe('cancelled')
    expect(state.message).toContain('cancelled')
  })

  it('handles queued_long with queue_position', () => {
    const state = simulateJob(5, 'queued_long')
    expect(state.status).toBe('queued')
    expect(state.queue_position).toBeDefined()
    expect(state.queue_position).toBeGreaterThan(0)
  })

  it('handles restart_fail scenario', () => {
    const state = simulateJob(3, 'restart_fail')
    expect(state.status).toBe('failed')
    expect(state.message).toBe('restart')
  })

  it('multi_round fills in rounds as search iterates', () => {
    const stateRunning = simulateJob(20, 'multi_round')
    expect(stateRunning.status).toBe('running')
    expect(stateRunning.round).toBeGreaterThanOrEqual(1)

    const stateDone = simulateJob(50, 'multi_round')
    expect(stateDone.status).toBe('done')
    expect(stateDone.rounds).toBeDefined()
    expect(stateDone.rounds!.length).toBeGreaterThanOrEqual(2)
    expect(stateDone.rounds![0].round).toBe(1)
    expect(stateDone.rounds![1].round).toBe(2)
  })
})
