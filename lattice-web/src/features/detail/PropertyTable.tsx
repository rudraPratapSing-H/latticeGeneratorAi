import type { Candidate, DesignRequest } from '@/api/types'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { InfoTip } from '@/components/ui/info-tip'
import { SourceTag } from '@/components/ui/source-tag'
import { AXES, AXIS_LABELS } from '@/config/constants'
import {
  evaluateAxis,
  signedDeltaPct,
  strengthSource,
  strengthValue,
  surrogateErrorPct,
} from '@/lib/compare'
import { cn } from '@/lib/cn'
import { Check, X, Minus } from 'lucide-react'

interface PropertyTableProps {
  candidate: Candidate
  request: (DesignRequest & { _metadata?: { adjustedFields?: string[] } }) | null
  tolerance: number
}

function fmtSigned(n: number | null): string {
  return n === null ? '\u2014' : `${n > 0 ? '+' : ''}${n.toFixed(1)}%`
}

function fmtErr(n: number | null): string {
  return n === null ? '\u2014' : `${n.toFixed(1)}%`
}

export function PropertyTable({ candidate, request, tolerance }: PropertyTableProps) {
  const adjusted = new Set(request?._metadata?.adjustedFields ?? [])
  const strengthInfo = strengthSource(request?.target)

  // Calculate surrogate errors across the 6 effective properties:
  // Stiffness X, Y, Z and Strength X, Y, Z
  const surrogateErrors: number[] = []

  AXES.forEach((axis) => {
    const stiffErr = surrogateErrorPct(
      candidate.predicted.stiffness_gpa[axis],
      candidate.verified.stiffness_gpa[axis],
    )
    if (stiffErr !== null) surrogateErrors.push(stiffErr)

    const strErr = surrogateErrorPct(
      strengthValue(candidate.predicted, strengthInfo.kind, axis),
      strengthValue(candidate.verified, strengthInfo.kind, axis),
    )
    if (strErr !== null) surrogateErrors.push(strErr)
  })

  surrogateErrors.sort((a, b) => a - b)
  const medianErr =
    surrogateErrors.length > 0
      ? surrogateErrors.length % 2 === 0
        ? (surrogateErrors[surrogateErrors.length / 2 - 1] +
            surrogateErrors[surrogateErrors.length / 2]) /
          2
        : surrogateErrors[Math.floor(surrogateErrors.length / 2)]
      : 0
  const maxErr = surrogateErrors.length > 0 ? Math.max(...surrogateErrors) : 0

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-text text-sm font-semibold">Properties & Solver Verification</h2>
            <InfoTip content="Strength is a solver estimate: first-order, linear-elastic analysis. Buckling assumes pinned ends, axis-aligned loads only." />
          </div>
          <span className="text-xs text-muted">AI proposes · Solver verifies</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead>
              <tr className="border-b border-line text-muted">
                <th scope="col" className="py-2 pr-3 font-medium">Property</th>
                {request && <th scope="col" className="px-2 py-2 text-right font-medium">Target</th>}
                <th scope="col" className="px-2 py-2 text-right font-medium">
                  <div className="flex items-center justify-end gap-1">
                    <span>Predicted</span>
                    <SourceTag source="predicted" />
                  </div>
                </th>
                <th scope="col" className="px-2 py-2 text-right font-medium">
                  <div className="flex items-center justify-end gap-1">
                    <span>Verified</span>
                    <SourceTag source="verified" />
                  </div>
                </th>
                <th scope="col" className="px-2 py-2 text-right font-medium">&Delta; Target</th>
                <th scope="col" className="px-2 py-2 text-right font-medium">Surrogate Err</th>
                <th scope="col" className="px-2 py-2 text-center font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line/40">
              {/* Stiffness Rows */}
              {AXES.map((axis) => {
                const target = request?.target.stiffness_gpa[axis] ?? null
                const predicted = candidate.predicted.stiffness_gpa[axis]
                const verified = candidate.verified.stiffness_gpa[axis]
                const fieldKey = `stiffness${axis.toUpperCase()}`
                const isAdjusted = adjusted.has(fieldKey)

                const result = evaluateAxis({
                  target,
                  value: verified,
                  mode: request?.modes.stiffness ?? 'about',
                  tolerancePct: tolerance,
                })
                const surrogateErr = surrogateErrorPct(predicted, verified)

                return (
                  <tr key={`stiff-${axis}`} className="hover:bg-surface-2/30">
                    <td className="py-2 pr-3 font-medium">
                      Stiffness{' '}
                      <span className={cn('font-semibold', `text-axis-${axis}`)}>
                        {AXIS_LABELS[axis]}
                      </span>
                      <span className="text-faint ml-1 font-normal font-mono">(GPa)</span>
                    </td>
                    {request && (
                      <td className="px-2 py-2 text-right font-mono tabular-nums">
                        {target !== null ? (
                          <div className="flex items-center justify-end gap-1">
                            <span>{target.toFixed(2)}</span>
                            <SourceTag source={isAdjusted ? 'adjusted' : 'requested'} />
                          </div>
                        ) : (
                          <span className="text-faint">&mdash;</span>
                        )}
                      </td>
                    )}
                    <td className="text-muted px-2 py-2 text-right font-mono tabular-nums">
                      {predicted.toFixed(2)}
                    </td>
                    <td className="px-2 py-2 text-right font-mono font-medium text-text tabular-nums">
                      {verified.toFixed(2)}
                    </td>
                    <td className="px-2 py-2 text-right font-mono tabular-nums">
                      {target !== null ? (
                        <span className={result.status === 'pass' ? 'text-success' : 'text-danger'}>
                          {fmtSigned(signedDeltaPct(verified, target))}
                        </span>
                      ) : (
                        <span className="text-faint">&mdash;</span>
                      )}
                    </td>
                    <td className="text-muted px-2 py-2 text-right font-mono tabular-nums">
                      {fmtErr(surrogateErr)}
                    </td>
                    <td className="px-2 py-2 text-center">
                      <StatusIcon status={result.status} />
                    </td>
                  </tr>
                )
              })}

              {/* Strength Rows (Effective) */}
              {AXES.map((axis) => {
                const target = strengthInfo.targets?.[axis] ?? null
                const predicted = strengthValue(candidate.predicted, strengthInfo.kind, axis)
                const verified = strengthValue(candidate.verified, strengthInfo.kind, axis)
                const fieldKey = `strength${axis.toUpperCase()}`
                const isAdjusted = adjusted.has(fieldKey)

                const result = evaluateAxis({
                  target,
                  value: verified,
                  mode: request?.modes.strength ?? 'at_least',
                  tolerancePct: tolerance,
                })
                const surrogateErr = surrogateErrorPct(predicted, verified)

                const failureMode = candidate.verified.governing_failure?.[axis]

                return (
                  <tr key={`str-${axis}`} className="hover:bg-surface-2/30">
                    <td className="py-2 pr-3 font-medium">
                      Strength{' '}
                      <span className={cn('font-semibold', `text-axis-${axis}`)}>
                        {AXIS_LABELS[axis]}
                      </span>
                      {failureMode && (
                        <span className="text-[10px] text-faint ml-1 font-normal font-sans">
                          ({failureMode})
                        </span>
                      )}
                      <span className="text-faint ml-1 font-normal font-mono">(MPa)</span>
                    </td>
                    {request && (
                      <td className="px-2 py-2 text-right font-mono tabular-nums">
                        {target !== null ? (
                          <div className="flex items-center justify-end gap-1">
                            <span>{target.toFixed(1)}</span>
                            <SourceTag source={isAdjusted ? 'adjusted' : 'requested'} />
                          </div>
                        ) : (
                          <span className="text-faint">&mdash;</span>
                        )}
                      </td>
                    )}
                    <td className="text-muted px-2 py-2 text-right font-mono tabular-nums">
                      {predicted.toFixed(1)}
                    </td>
                    <td className="px-2 py-2 text-right font-mono font-medium text-text tabular-nums">
                      {verified.toFixed(1)}
                    </td>
                    <td className="px-2 py-2 text-right font-mono tabular-nums">
                      {target !== null ? (
                        <span className={result.status === 'pass' ? 'text-success' : 'text-danger'}>
                          {fmtSigned(signedDeltaPct(verified, target))}
                        </span>
                      ) : (
                        <span className="text-faint">&mdash;</span>
                      )}
                    </td>
                    <td className="text-muted px-2 py-2 text-right font-mono tabular-nums">
                      {fmtErr(surrogateErr)}
                    </td>
                    <td className="px-2 py-2 text-center">
                      <StatusIcon status={result.status} />
                    </td>
                  </tr>
                )
              })}

              {/* Sub-rows: Detailed Yield and Buckling breakdown */}
              {AXES.map((axis) => {
                const yieldVal = candidate.verified.yield_strength_mpa[axis]
                const buckVal = candidate.verified.buckling_strength_mpa[axis]
                const gov = candidate.verified.governing_failure?.[axis] ?? 'yield'

                return (
                  <tr key={`sub-${axis}`} className="bg-surface-2/20 text-muted">
                    <td className="py-1.5 pr-3 pl-4 text-[11px]" colSpan={request ? 2 : 1}>
                      <span className={cn('font-medium', `text-axis-${axis}`)}>
                        {AXIS_LABELS[axis]}
                      </span>{' '}
                      Yield {yieldVal.toFixed(1)} MPa &middot; Buckling {buckVal.toFixed(1)} MPa &middot;{' '}
                      <span className="font-medium text-text">Governs: {gov}</span>
                    </td>
                    <td colSpan={5} className="py-1.5 text-right pr-2 text-[11px] text-faint">
                      Verified only (no failure mode on prediction)
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* Footer: Surrogate accuracy metrics */}
        <div className="rounded-lg border border-line bg-surface-2/60 p-3 text-xs text-muted flex flex-wrap items-center justify-between gap-2">
          <div>
            <span className="font-medium text-text">Surrogate Accuracy: </span>
            <span>
              Median error: <strong className="text-accent font-mono">{medianErr.toFixed(1)}%</strong> &middot; Max error: <strong className="text-accent font-mono">{maxErr.toFixed(1)}%</strong>
            </span>
          </div>
          <span className="text-[11px] text-faint">
            Measures how far the AI proposal was from physics solver verification
          </span>
        </div>
      </CardContent>
    </Card>
  )
}

function StatusIcon({ status }: { status: 'pass' | 'fail' | 'ignored' }) {
  if (status === 'pass') {
    return (
      <span className="inline-flex items-center text-success" title="Within target">
        <Check className="h-3.5 w-3.5" />
      </span>
    )
  }
  if (status === 'fail') {
    return (
      <span className="inline-flex items-center text-danger" title="Outside target">
        <X className="h-3.5 w-3.5" />
      </span>
    )
  }
  return (
    <span className="inline-flex items-center text-faint" title="Not targeted">
      <Minus className="h-3.5 w-3.5" />
    </span>
  )
}
