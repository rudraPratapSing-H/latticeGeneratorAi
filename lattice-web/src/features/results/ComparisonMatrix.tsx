import type { Candidate, DesignRequest } from '@/api/types'
import { AXES, AXIS_LABELS, designPath } from '@/config/constants'
import { evaluateAxis, strengthSource, strengthValue } from '@/lib/compare'
import { fmtPct, fmtMass, fmtRelDensity } from '@/lib/format'
import { Check, X, Minus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/cn'

interface ComparisonMatrixProps {
  candidates: Candidate[]
  jobId: string
  request: DesignRequest | null
}

export function ComparisonMatrix({ candidates, jobId, request }: ComparisonMatrixProps) {
  const tolerance = request?.tolerance_pct ?? 10

  // Calculate best values for highlighting
  const minError = Math.min(...candidates.map((c) => c.match_error_pct))
  const minMass = Math.min(...candidates.map((c) => c.mass_g))
  const minRd = Math.min(...candidates.map((c) => c.rel_density))

  return (
    <div className="border border-line overflow-x-auto rounded-lg shadow-sm">
      <table className="w-full text-xs text-left">
        <thead>
          <tr className="border-b border-line bg-surface-2 text-muted">
            <th scope="col" className="bg-surface-2 sticky left-0 z-10 px-3 py-2.5 font-medium">
              Rank
            </th>
            <th scope="col" className="px-3 py-2.5 font-medium">Status</th>
            <th scope="col" className="px-3 py-2.5 font-medium">Error</th>
            <th scope="col" className="px-3 py-2.5 text-right font-medium">Mass</th>
            <th scope="col" className="px-3 py-2.5 text-right font-medium">&rho;</th>
            {AXES.map((axis) => (
              <th scope="col" key={`stiff-${axis}`} className="px-3 py-2.5 text-right font-medium">
                Stiff{' '}
                <span
                  className={cn(
                    'font-semibold',
                    axis === 'x' && 'text-axis-x',
                    axis === 'y' && 'text-axis-y',
                    axis === 'z' && 'text-axis-z',
                  )}
                >
                  {AXIS_LABELS[axis]}
                </span>
                <span className="text-[10px] text-faint ml-0.5">(GPa)</span>
              </th>
            ))}
            {AXES.map((axis) => (
              <th scope="col" key={`str-${axis}`} className="px-3 py-2.5 text-right font-medium">
                Str{' '}
                <span
                  className={cn(
                    'font-semibold',
                    axis === 'x' && 'text-axis-x',
                    axis === 'y' && 'text-axis-y',
                    axis === 'z' && 'text-axis-z',
                  )}
                >
                  {AXIS_LABELS[axis]}
                </span>
                <span className="text-[10px] text-faint ml-0.5">(MPa)</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line/60 bg-surface">
          {candidates.map((c) => {
            const { kind: strengthKind, targets: strengthTargets } = strengthSource(request?.target)

            return (
              <tr
                key={c.id}
                className="hover:bg-surface-2/60 transition-colors"
              >
                <td className="bg-surface sticky left-0 z-10 px-3 py-2 font-semibold font-mono">
                  <Link to={designPath(jobId, c.id)} className="text-accent hover:underline">
                    #{c.rank}
                  </Link>
                </td>
                <td className="px-3 py-2">
                  {c.matches_targets ? (
                    <span className="inline-flex items-center gap-1 text-success text-[11px] font-medium">
                      <Check className="h-3 w-3" /> Match
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-warning text-[11px] font-medium">
                      <Minus className="h-3 w-3" /> Closest
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 font-mono tabular-nums">
                  <span
                    className={cn(
                      c.matches_targets ? 'text-success' : 'text-warning',
                      c.match_error_pct === minError && 'font-bold underline decoration-accent/40',
                    )}
                  >
                    {fmtPct(c.match_error_pct)}
                  </span>
                </td>
                <td
                  className={cn(
                    'px-3 py-2 text-right font-mono tabular-nums',
                    c.mass_g === minMass && 'text-accent font-medium',
                  )}
                >
                  {fmtMass(c.mass_g)}
                </td>
                <td
                  className={cn(
                    'px-3 py-2 text-right font-mono tabular-nums',
                    c.rel_density === minRd && 'text-accent font-medium',
                  )}
                >
                  {fmtRelDensity(c.rel_density)}
                </td>
                {AXES.map((axis) => {
                  const target = request?.target.stiffness_gpa[axis] ?? null
                  const value = c.verified.stiffness_gpa[axis]
                  const result = request && target != null
                    ? evaluateAxis({
                        target,
                        value,
                        mode: request.modes.stiffness,
                        tolerancePct: tolerance,
                      })
                    : null

                  return (
                    <td key={`stiff-${axis}`} className="px-3 py-2 text-right font-mono tabular-nums">
                      {target !== null ? (
                        <div className="flex items-center justify-end gap-1.5">
                          {/* Mini inline bar */}
                          <div className="relative w-8 h-1.5 bg-surface-2 rounded-full overflow-hidden hidden sm:block">
                            <div
                              className={cn(
                                'h-full transition-all rounded-full',
                                result?.status === 'pass' ? 'bg-success' : 'bg-warning',
                              )}
                              style={{ width: `${Math.min(100, (value / target) * 100)}%` }}
                            />
                          </div>
                          <span>{value.toFixed(2)}</span>
                          {result?.status === 'pass' && <Check className="text-success h-3 w-3 shrink-0" />}
                          {result?.status === 'fail' && <X className="text-danger h-3 w-3 shrink-0" />}
                        </div>
                      ) : (
                        <span className="text-faint">&mdash;</span>
                      )}
                    </td>
                  )
                })}
                {AXES.map((axis) => {
                  const target = strengthTargets?.[axis] ?? null
                  const value = strengthValue(c.verified, strengthKind, axis)
                  const result = request && target != null
                    ? evaluateAxis({
                        target,
                        value,
                        mode: request.modes.strength,
                        tolerancePct: tolerance,
                      })
                    : null

                  return (
                    <td key={`str-${axis}`} className="px-3 py-2 text-right font-mono tabular-nums">
                      {target !== null ? (
                        <div className="flex items-center justify-end gap-1.5">
                          {/* Mini inline bar */}
                          <div className="relative w-8 h-1.5 bg-surface-2 rounded-full overflow-hidden hidden sm:block">
                            <div
                              className={cn(
                                'h-full transition-all rounded-full',
                                result?.status === 'pass' ? 'bg-success' : 'bg-warning',
                              )}
                              style={{ width: `${Math.min(100, (value / target) * 100)}%` }}
                            />
                          </div>
                          <span>{value.toFixed(1)}</span>
                          {result?.status === 'pass' && <Check className="text-success h-3 w-3 shrink-0" />}
                          {result?.status === 'fail' && <X className="text-danger h-3 w-3 shrink-0" />}
                        </div>
                      ) : (
                        <span className="text-faint">&mdash;</span>
                      )}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
