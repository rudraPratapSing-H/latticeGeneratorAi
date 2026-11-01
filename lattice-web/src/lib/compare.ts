import type { Axis, PerAxis, TargetMode } from '@/api/types'

export type EvalStatus = 'pass' | 'fail' | 'ignored'

export interface EvalResult {
  status: EvalStatus
  errorPct: number
}

/**
 * The solver counts an "at least" or "at most" limit as met when it is missed by no more than 0.5%
 * (search_design.solver_errors). Using the same slack here keeps the rows, cards and banner in step
 * with the backend's `matches_targets`.
 */
export const MATCH_SLACK = 0.005

/**
 * Evaluate whether a verified value meets a target under the given mode.
 * - about: |value - target| / target x 100 <= tolerancePct
 * - at_least: value >= target x (1 - slack)
 * - at_most: value <= target x (1 + slack)
 * - null target: ignored
 * `slack` defaults to MATCH_SLACK for at_least / at_most and 0 for about.
 */
export function evaluateAxis(params: {
  target: number | null
  value: number
  mode: TargetMode
  tolerancePct: number
  slack?: number
}): EvalResult {
  const { target, value, mode, tolerancePct } = params
  const slack = params.slack ?? (mode === 'about' ? 0 : MATCH_SLACK)

  if (target === null || target === undefined) {
    return { status: 'ignored', errorPct: 0 }
  }

  const errorPct =
    target === 0 ? (value === 0 ? 0 : 100) : (Math.abs(value - target) / target) * 100

  switch (mode) {
    case 'about':
      return { status: errorPct <= tolerancePct ? 'pass' : 'fail', errorPct }
    case 'at_least':
      return { status: value >= target * (1 - slack) ? 'pass' : 'fail', errorPct }
    case 'at_most':
      return { status: value <= target * (1 + slack) ? 'pass' : 'fail', errorPct }
    default:
      return { status: 'ignored', errorPct }
  }
}

/** Check if ALL targeted axes pass */
export function allTargetsMet(results: EvalResult[]): boolean {
  return results.every((r) => r.status === 'pass' || r.status === 'ignored')
}

/** (value - target) / target in percent, with its sign; null when there is no usable target. */
export function signedDeltaPct(value: number, target: number | null | undefined): number | null {
  if (target === null || target === undefined || target === 0) return null
  return ((value - target) / target) * 100
}

/** |predicted - verified| / verified in percent; null when the verified value is not positive. */
export function surrogateErrorPct(predicted: number, verified: number): number | null {
  return verified > 0 ? (Math.abs(predicted - verified) / verified) * 100 : null
}

type AxisTargetsLike = Partial<Record<Axis, number | null>> | null | undefined

/**
 * Which strength the request asked for. The backend echoes BOTH `strength_mpa` and
 * `yield_strength_mpa` (one of them null), so the key cannot be tested with `in`.
 */
export function strengthSource(
  target: { strength_mpa?: AxisTargetsLike; yield_strength_mpa?: AxisTargetsLike } | null | undefined,
): { kind: 'effective' | 'yield'; targets: AxisTargetsLike } {
  const has = (t: AxisTargetsLike) => !!t && Object.values(t).some((v) => v !== null && v !== undefined)
  if (has(target?.strength_mpa)) return { kind: 'effective', targets: target?.strength_mpa }
  if (has(target?.yield_strength_mpa)) return { kind: 'yield', targets: target?.yield_strength_mpa }
  return { kind: 'effective', targets: null }
}

/** The strength figure to compare with a target of the given kind: effective = min(yield, buckling). */
export function strengthValue(
  side: { strength_mpa: PerAxis<number>; yield_strength_mpa: PerAxis<number> },
  kind: 'effective' | 'yield',
  axis: Axis,
): number {
  return kind === 'yield' ? side.yield_strength_mpa[axis] : side.strength_mpa[axis]
}
