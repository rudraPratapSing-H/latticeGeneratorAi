import { describe, it, expect } from 'vitest'
import {
  evaluateAxis,
  allTargetsMet,
  signedDeltaPct,
  strengthSource,
  strengthValue,
  surrogateErrorPct,
} from '@/lib/compare'

describe('evaluateAxis', () => {
  it('returns "ignored" when target is null', () => {
    const result = evaluateAxis({ target: null, value: 10, mode: 'about', tolerancePct: 10 })
    expect(result.status).toBe('ignored')
    expect(result.errorPct).toBe(0)
  })

  it('passes "about" mode when within tolerance', () => {
    const result = evaluateAxis({ target: 10, value: 10.5, mode: 'about', tolerancePct: 10 })
    expect(result.status).toBe('pass')
    expect(result.errorPct).toBeCloseTo(5, 0)
  })

  it('fails "about" mode when outside tolerance', () => {
    const result = evaluateAxis({ target: 10, value: 12, mode: 'about', tolerancePct: 10 })
    expect(result.status).toBe('fail')
    expect(result.errorPct).toBeCloseTo(20, 0)
  })

  it('passes "at_least" mode when value meets target', () => {
    const result = evaluateAxis({ target: 100, value: 105, mode: 'at_least', tolerancePct: 10 })
    expect(result.status).toBe('pass')
  })

  it('fails "at_least" mode when value is too low', () => {
    const result = evaluateAxis({ target: 100, value: 80, mode: 'at_least', tolerancePct: 10 })
    expect(result.status).toBe('fail')
  })

  it('supports strength at_least 0.5% slack: shortfall <= 0.5% is not a miss', () => {
    // 99.6 is 0.4% shortfall (< 0.5% slack)
    const result = evaluateAxis({
      target: 100,
      value: 99.6,
      mode: 'at_least',
      tolerancePct: 10,
      slack: 0.005,
    })
    expect(result.status).toBe('pass')
  })

  it('supports strength at_least 0.5% slack: shortfall > 0.5% is a miss', () => {
    // 99.4 is 0.6% shortfall (> 0.5% slack)
    const result = evaluateAxis({
      target: 100,
      value: 99.4,
      mode: 'at_least',
      tolerancePct: 10,
      slack: 0.005,
    })
    expect(result.status).toBe('fail')
  })

  it('passes "at_most" mode when value is below target', () => {
    const result = evaluateAxis({ target: 50, value: 40, mode: 'at_most', tolerancePct: 10 })
    expect(result.status).toBe('pass')
  })

  it('fails "at_most" mode when value exceeds target', () => {
    const result = evaluateAxis({ target: 50, value: 60, mode: 'at_most', tolerancePct: 10 })
    expect(result.status).toBe('fail')
  })
})

describe('allTargetsMet', () => {
  it('returns true when all results pass or are ignored', () => {
    const results = [
      { status: 'pass' as const, errorPct: 5 },
      { status: 'ignored' as const, errorPct: 0 },
      { status: 'pass' as const, errorPct: 2 },
    ]
    expect(allTargetsMet(results)).toBe(true)
  })

  it('returns false when any result fails', () => {
    const results = [
      { status: 'pass' as const, errorPct: 5 },
      { status: 'fail' as const, errorPct: 25 },
      { status: 'pass' as const, errorPct: 2 },
    ]
    expect(allTargetsMet(results)).toBe(false)
  })

  it('returns true for empty results', () => {
    expect(allTargetsMet([])).toBe(true)
  })
})

describe('backend-matching slack', () => {
  it('gives at_least and at_most a 0.5% slack by default, like the solver', () => {
    expect(evaluateAxis({ target: 100, value: 99.6, mode: 'at_least', tolerancePct: 10 }).status).toBe('pass')
    expect(evaluateAxis({ target: 100, value: 99.4, mode: 'at_least', tolerancePct: 10 }).status).toBe('fail')
    expect(evaluateAxis({ target: 100, value: 100.4, mode: 'at_most', tolerancePct: 10 }).status).toBe('pass')
    expect(evaluateAxis({ target: 100, value: 100.6, mode: 'at_most', tolerancePct: 10 }).status).toBe('fail')
  })

  it('gives "about" no slack', () => {
    expect(evaluateAxis({ target: 100, value: 110.4, mode: 'about', tolerancePct: 10 }).status).toBe('fail')
  })
})

describe('surrogateErrorPct', () => {
  it('is |predicted - verified| / verified in percent', () => {
    expect(surrogateErrorPct(3.5, 2.5)).toBeCloseTo(40, 6)
    expect(surrogateErrorPct(1.8, 2)).toBeCloseTo(10, 6)
  })

  it('is null, not 0, when the verified value is not positive', () => {
    expect(surrogateErrorPct(1, 0)).toBeNull()
  })
})

describe('signedDeltaPct', () => {
  it('keeps the sign', () => {
    expect(signedDeltaPct(110, 100)).toBeCloseTo(10, 6)
    expect(signedDeltaPct(90, 100)).toBeCloseTo(-10, 6)
  })

  it('is null without a usable target', () => {
    expect(signedDeltaPct(5, null)).toBeNull()
    expect(signedDeltaPct(5, 0)).toBeNull()
  })
})

describe('strengthSource', () => {
  const ax = { x: 3, y: 4, z: 5 }

  it('uses effective strength when the backend echoes yield_strength_mpa: null', () => {
    expect(strengthSource({ strength_mpa: ax, yield_strength_mpa: null })).toEqual({ kind: 'effective', targets: ax })
  })

  it('uses the yield target when only that one is set (the backend still echoes strength_mpa: null)', () => {
    expect(strengthSource({ strength_mpa: null, yield_strength_mpa: ax })).toEqual({ kind: 'yield', targets: ax })
  })

  it('has no targets when neither is set', () => {
    expect(strengthSource({ strength_mpa: null, yield_strength_mpa: null }).targets).toBeNull()
    expect(strengthSource(undefined).targets).toBeNull()
  })
})

describe('strengthValue', () => {
  const side = {
    strength_mpa: { x: 1, y: 2, z: 3 },
    yield_strength_mpa: { x: 10, y: 20, z: 30 },
  }

  it('picks yield or effective strength to match the target kind', () => {
    expect(strengthValue(side, 'effective', 'y')).toBe(2)
    expect(strengthValue(side, 'yield', 'y')).toBe(20)
  })
})

