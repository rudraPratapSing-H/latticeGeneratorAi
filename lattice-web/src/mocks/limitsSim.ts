/** Mock /api/limits: the real backend response for Ti-6Al-4V (the only material the backend has). */
import limits from '@/mocks/fixtures/real/limits.json'

export function mockLimits(): unknown {
  return limits
}
