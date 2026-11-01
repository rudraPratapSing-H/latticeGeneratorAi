import { InlineAlert } from '@/components/feedback/InlineAlert'
import { InfoTip } from '@/components/ui/info-tip'
import { Badge } from '@/components/ui/badge'
import type { Candidate, DesignRequest, ReachLevel } from '@/api/types'
import { AXES, AXIS_LABELS } from '@/config/constants'
import { MATCH_SLACK, strengthSource, strengthValue } from '@/lib/compare'
import { ShieldCheck, AlertTriangle } from 'lucide-react'

interface ResultsBannerProps {
  candidates: Candidate[]
  request: DesignRequest | null
  reach?: { level: ReachLevel; distance_pct: number }
  infeasible?: boolean
  warnings?: string[]
}

export function ResultsBanner({
  candidates,
  request,
  reach,
  infeasible,
  warnings,
}: ResultsBannerProps) {
  if (candidates.length === 0) return null

  const matchedCount = candidates.filter((c) => c.matches_targets).length
  const closestCount = candidates.length - matchedCount
  const bestCandidate = candidates[0]

  // Calculate shortfalls for the best candidate if no design met targets
  const shortfalls: string[] = []
  if (matchedCount === 0 && request && bestCandidate) {
    const tolerance = request.tolerance_pct

    // Check stiffness
    AXES.forEach((axis) => {
      const target = request.target.stiffness_gpa[axis]
      if (target != null) {
        const verified = bestCandidate.verified.stiffness_gpa[axis]
        const mode = request.modes.stiffness
        if (mode === 'about') {
          const diffPct = (Math.abs(verified - target) / target) * 100
          if (diffPct > tolerance) {
            shortfalls.push(
              `Stiffness ${AXIS_LABELS[axis]}: ${verified.toFixed(2)} vs target ${target} GPa (${diffPct.toFixed(1)}% off, tolerance ±${tolerance}%)`,
            )
          }
        } else if (mode === 'at_least' && verified < target * (1 - MATCH_SLACK)) {
          const shortPct = ((target - verified) / target) * 100
          shortfalls.push(
            `Stiffness ${AXIS_LABELS[axis]}: ${verified.toFixed(2)} vs target ${target} GPa (-${shortPct.toFixed(1)}% shortfall)`,
          )
        } else if (mode === 'at_most' && verified > target * (1 + MATCH_SLACK)) {
          const excessPct = ((verified - target) / target) * 100
          shortfalls.push(
            `Stiffness ${AXIS_LABELS[axis]}: ${verified.toFixed(2)} vs target ${target} GPa (+${excessPct.toFixed(1)}% over limit)`,
          )
        }
      }
    })

    // Check strength (shortfalls > 0.5% are misses)
    const { kind: strengthKind, targets: strengthTargets } = strengthSource(request.target)

    if (strengthTargets) {
      AXES.forEach((axis) => {
        const target = strengthTargets[axis]
        if (target != null) {
          const verified = strengthValue(bestCandidate.verified, strengthKind, axis)
          const mode = request.modes.strength
          if (mode === 'at_least') {
            const ratio = verified / target
            if (ratio < 1 - MATCH_SLACK) {
              const shortfallPct = ((target - verified) / target) * 100
              shortfalls.push(
                `Strength ${AXIS_LABELS[axis]}: ${verified.toFixed(1)} vs target ${target} MPa (-${shortfallPct.toFixed(1)}% shortfall)`,
              )
            }
          } else if (mode === 'at_most') {
            if (verified > target * (1 + MATCH_SLACK)) {
              const excessPct = ((verified - target) / target) * 100
              shortfalls.push(
                `Strength ${AXIS_LABELS[axis]}: ${verified.toFixed(1)} vs target ${target} MPa (+${excessPct.toFixed(1)}% over limit)`,
              )
            }
          } else if (mode === 'about') {
            const diffPct = (Math.abs(verified - target) / target) * 100
            if (diffPct > tolerance) {
              shortfalls.push(
                `Strength ${AXIS_LABELS[axis]}: ${verified.toFixed(1)} vs target ${target} MPa (${diffPct.toFixed(1)}% off)`,
              )
            }
          }
        }
      })
    }
  }

  return (
    <div className="space-y-3">
      {/* Primary solver verification banner */}
      {matchedCount > 0 ? (
        <InlineAlert variant="info">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-success" />
              <span>
                <strong>{matchedCount}</strong> of {candidates.length} design
                {candidates.length > 1 ? 's are' : ' is'} solver-verified and meet
                {matchedCount === 1 ? 's' : ''} your targets.
                {closestCount > 0 && ` Showing the closest ${closestCount} as well.`}
              </span>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-muted">
              <span>Strength: solver estimate</span>
              <InfoTip content="First-order, linear-elastic solver estimate. Buckling assumes pinned ends; axis-aligned loads only. Printing and mechanical tests are needed before any clinical or critical claim." />
            </div>
          </div>
        </InlineAlert>
      ) : (
        <InlineAlert variant="warning">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-warning" />
                <span>
                  <strong>No design met every target.</strong> Showing the closest{' '}
                  {candidates.length} candidates.
                </span>
              </div>
              <div className="flex items-center gap-1.5 text-xs text-muted">
                <span>Strength: solver estimate</span>
                <InfoTip content="First-order, linear-elastic solver estimate. Buckling assumes pinned ends; axis-aligned loads only. Printing and mechanical tests are needed before any clinical or critical claim." />
              </div>
            </div>

            {shortfalls.length > 0 && (
              <div className="rounded-md border border-warning/30 bg-surface/50 p-2 text-xs">
                <p className="font-medium text-text mb-1">
                  Shortfall breakdown for rank #1 candidate:
                </p>
                <ul className="list-disc pl-4 space-y-0.5 text-muted font-mono">
                  {shortfalls.map((s, idx) => (
                    <li key={idx}>{s}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </InlineAlert>
      )}

      {/* Warnings from job if any */}
      {warnings && warnings.length > 0 && (
        <div className="space-y-1">
          {warnings.map((w, i) => (
            <InlineAlert key={i} variant="warning">
              {w}
            </InlineAlert>
          ))}
        </div>
      )}

      {/* Infeasible notice */}
      {infeasible && (
        <InlineAlert variant="error">
          Target was marked infeasible. Physics solver search completed using forced execution.
        </InlineAlert>
      )}

      {/* Reach info badge */}
      {reach && (
        <div className="flex items-center gap-2 text-xs text-muted">
          <span>Dataset reach:</span>
          <Badge
            variant={
              reach.level === 'covered'
                ? 'success'
                : reach.level === 'extended'
                  ? 'info'
                  : 'warning'
            }
          >
            {reach.level} ({reach.distance_pct.toFixed(1)}% distance)
          </Badge>
        </div>
      )}
    </div>
  )
}
