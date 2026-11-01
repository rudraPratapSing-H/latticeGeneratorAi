import { Suspense, lazy, useState } from 'react'
import { Link } from 'react-router-dom'
import type { Candidate, DesignRequest } from '@/api/types'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { SourceTag } from '@/components/ui/source-tag'
import { Skeleton } from '@/components/ui/skeleton'
import { AXES, AXIS_LABELS, designPath } from '@/config/constants'
import { evaluateAxis, strengthSource, strengthValue } from '@/lib/compare'
import { fmtPct, fmtMass, fmtRelDensity } from '@/lib/format'
import { ArrowUpRight, Check, Move3d, X, Minus } from 'lucide-react'
import { cn } from '@/lib/cn'

const LatticeViewer = lazy(() => import('@/components/LatticeViewer'))

interface CandidateCardProps {
  candidate: Candidate
  jobId: string
  /** Query string appended to the detail link, for example ?fromImplant=i_1234 */
  linkSearch?: string
  request: DesignRequest | null
  /** position in the grid; staggers the entrance animation */
  index?: number
}

export function CandidateCard({ candidate, jobId, linkSearch = '', request, index = 0 }: CandidateCardProps) {
  const tolerance = request?.tolerance_pct ?? 10
  const [active, setActive] = useState(false)
  const best = candidate.rank === 1 && candidate.matches_targets

  return (
    <Link
      to={designPath(jobId, candidate.id) + linkSearch}
      className="group animate-card-in block h-full rounded-xl outline-offset-4"
      style={{ animationDelay: `${Math.min(index, 8) * 70}ms` }}
      onMouseEnter={() => setActive(true)}
      onMouseLeave={() => setActive(false)}
      onFocus={() => setActive(true)}
      onBlur={() => setActive(false)}
    >
      <Card
        className={cn(
          'relative flex h-full flex-col overflow-hidden rounded-xl transition-[transform,box-shadow,border-color] duration-300',
          'group-hover:-translate-y-0.5 group-hover:shadow-lg group-focus-visible:-translate-y-0.5',
          best
            ? 'border-accent/40 group-hover:border-accent/70'
            : 'group-hover:border-accent/40',
        )}
      >
        {/* 3D stage: the part rotates here; opening the card gives full orbit controls */}
        <div className="thumb-stage relative aspect-[5/4] overflow-hidden border-b border-line">
          <span className="thumb-tick left-2.5 top-2.5 border-l border-t" />
          <span className="thumb-tick right-2.5 top-2.5 border-r border-t" />
          <span className="thumb-tick bottom-2.5 left-2.5 border-b border-l" />
          <span className="thumb-tick bottom-2.5 right-2.5 border-b border-r" />

          <div className="absolute inset-0 transition-transform duration-500 ease-out group-hover:scale-[1.04]">
            <Suspense fallback={<Skeleton className="h-full w-full" />}>
              <LatticeViewer lattice={candidate.lattice} variant="thumbnail" active={active} seedKey={candidate.id} />
            </Suspense>
          </div>

          <div className="absolute left-3 top-3 flex items-center gap-2">
            <span className="bg-bg/70 text-text rounded-md border border-line px-1.5 py-0.5 font-mono text-sm font-semibold backdrop-blur-sm">
              #{candidate.rank}
            </span>
            <Badge
              variant={
                candidate.matches_targets
                  ? 'success'
                  : candidate.match_error_pct <= tolerance * 2
                    ? 'warning'
                    : 'danger'
              }
            >
              {fmtPct(candidate.match_error_pct)} error
            </Badge>
          </div>

          <div className="absolute right-3 top-3 flex flex-col items-end gap-1">
            {best && <Badge variant="accent">Best match</Badge>}
            {!candidate.matches_targets && <Badge variant="warning">Closest, not a match</Badge>}
          </div>

          {candidate.matches_targets && (
            <span className="text-success absolute bottom-3 left-3 flex items-center gap-1 text-xs font-medium">
              <Check className="h-3.5 w-3.5" /> Within target
            </span>
          )}

          <span className="bg-accent text-accent-fg pointer-events-none absolute bottom-3 right-3 flex translate-y-1 items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold opacity-0 shadow-md transition-all duration-300 group-hover:translate-y-0 group-hover:opacity-100 group-focus-visible:translate-y-0 group-focus-visible:opacity-100 [@media(hover:none)]:translate-y-0 [@media(hover:none)]:opacity-100">
            <Move3d className="h-3 w-3" /> Inspect in 3D
          </span>
        </div>

        <div className="flex flex-1 flex-col justify-between gap-3 p-4">
          <div className="space-y-3">
            {/* Stats */}
            <div className="text-muted flex items-center justify-between text-xs">
              <span className="flex items-center gap-1.5">
                <span className="text-text font-medium tabular-nums">{fmtMass(candidate.mass_g)}</span>
                <SourceTag source="estimate" />
              </span>
              <span className="tabular-nums">&rho; = {fmtRelDensity(candidate.rel_density)}</span>
              <span className="text-faint font-mono">r={candidate.lattice.strut_radius_mm.toFixed(2)}mm</span>
            </div>

            {/* Per-axis results */}
            {request && (
              <div className="space-y-1.5 border-t border-line/60 pt-3">
                {AXES.map((axis) => {
                  const target = request.target.stiffness_gpa[axis]
                  if (target === null) return null
                  const verified = candidate.verified.stiffness_gpa[axis]
                  const result = evaluateAxis({
                    target,
                    value: verified,
                    mode: request.modes.stiffness,
                    tolerancePct: tolerance,
                  })
                  return (
                    <AxisRow
                      key={`stiff-${axis}`}
                      axis={axis}
                      label="Stiff"
                      value={verified}
                      unit="GPa"
                      target={target}
                      status={result.status}
                    />
                  )
                })}

                {AXES.map((axis) => {
                  const { kind, targets } = strengthSource(request.target)
                  const target = targets?.[axis] ?? null
                  if (target === null) return null
                  const verified = strengthValue(candidate.verified, kind, axis)
                  const failureMode = candidate.verified.governing_failure?.[axis]
                  const result = evaluateAxis({
                    target,
                    value: verified,
                    mode: request.modes.strength,
                    tolerancePct: tolerance,
                  })
                  return (
                    <AxisRow
                      key={`str-${axis}`}
                      axis={axis}
                      label="Strength"
                      value={verified}
                      unit="MPa"
                      target={target}
                      status={result.status}
                      governingFailure={failureMode}
                    />
                  )
                })}
              </div>
            )}
          </div>

          <div className="flex items-center justify-between gap-3 border-t border-line/60 pt-3 text-xs">
            <span className="text-faint truncate font-mono" title={candidate.id}>
              {candidate.id}
            </span>
            <span className="text-accent flex shrink-0 items-center gap-0.5 font-medium">
              Open design
              <ArrowUpRight className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
            </span>
          </div>
        </div>
      </Card>
    </Link>
  )
}

function AxisRow({
  axis,
  label,
  value,
  unit,
  target,
  status,
  governingFailure,
}: {
  axis: string
  label: string
  value: number
  unit: string
  target: number
  status: 'pass' | 'fail' | 'ignored'
  governingFailure?: 'yield' | 'buckling'
}) {
  // how far the verified value is from the target, as a share of the target (bar is capped at 125%)
  const ratio = target > 0 ? Math.max(0, Math.min(1.25, value / target)) : 0
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 text-xs">
      <div className="min-w-0">
        <div className="flex items-center justify-between">
          <span className="text-muted flex items-center gap-1">
            <span>{label}</span>
            <span
              className={cn(
                'font-semibold',
                axis === 'x' && 'text-axis-x',
                axis === 'y' && 'text-axis-y',
                axis === 'z' && 'text-axis-z',
              )}
            >
              {AXIS_LABELS[axis as 'x' | 'y' | 'z']}
            </span>
            {governingFailure && <span className="text-faint text-[10px]">({governingFailure})</span>}
          </span>
        </div>
        <div className="bg-surface-2 relative mt-1 h-1 overflow-hidden rounded-full" aria-hidden="true">
          <div
            className={cn(
              'h-full rounded-full transition-[width] duration-700 ease-out',
              status === 'fail' ? 'bg-danger/80' : status === 'pass' ? 'bg-success/80' : 'bg-faint/60',
            )}
            style={{ width: `${(ratio / 1.25) * 100}%` }}
          />
          <span className="bg-text/40 absolute top-0 h-full w-px" style={{ left: '80%' }} />
        </div>
      </div>
      <div className="flex items-center gap-1.5 font-mono tabular-nums">
        <span>
          {value.toFixed(1)} {unit}
        </span>
        <span className="text-faint">/ {target}</span>
        {status === 'pass' && (
          <span className="text-success flex items-center" title="Within target">
            <Check className="h-3.5 w-3.5" />
          </span>
        )}
        {status === 'fail' && (
          <span className="text-danger flex items-center" title="Outside target">
            <X className="h-3.5 w-3.5" />
          </span>
        )}
        {status === 'ignored' && (
          <span className="text-faint flex items-center" title="Not targeted">
            <Minus className="h-3.5 w-3.5" />
          </span>
        )}
      </div>
    </div>
  )
}
