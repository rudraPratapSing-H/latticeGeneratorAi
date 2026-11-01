/** All available mock scenarios. Default is 'success'. */
export const MOCK_SCENARIOS = [
  'success',
  'multi_round',
  'slow',
  'no_match',
  'empty',
  'fail',
  'restart_fail',
  'cancelled',
  'queued_long',
  'bad_target',
  'queue_full',
  'offline',
] as const

export type MockScenario = (typeof MOCK_SCENARIOS)[number]

export const ALL_SCENARIOS = MOCK_SCENARIOS

export const SCENARIO_LABELS: Record<MockScenario, string> = {
  success: 'Success (single round, 12s)',
  multi_round: 'Multi-round (2 rounds, 45s)',
  slow: 'Slow (3 rounds, 35s)',
  no_match: 'No match (closest shown)',
  empty: 'Empty (no candidates)',
  fail: 'Fail (solver crash at 6s)',
  restart_fail: 'Restart error',
  cancelled: 'Cancelled',
  queued_long: 'Long queue wait',
  bad_target: 'Bad target (422)',
  queue_full: 'Queue full (429)',
  offline: 'Offline / Network error',
}
