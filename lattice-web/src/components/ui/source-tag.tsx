import { cn } from '@/lib/cn'
import { Tooltip } from '@/components/ui/tooltip'

export type SourceKind =
  | 'requested'
  | 'adjusted'
  | 'predicted'
  | 'verified'
  | 'stored'
  | 'estimate'
  | 'automatic'

const SOURCE_CONFIG: Record<SourceKind, { label: string; tooltip: string; className: string }> = {
  requested: {
    label: 'Requested',
    tooltip: 'Value you entered as a target.',
    className: 'bg-accent-soft text-accent',
  },
  adjusted: {
    label: 'Adjusted',
    tooltip: 'You accepted a suggested adjustment to this target.',
    className: 'bg-warning/15 text-warning',
  },
  predicted: {
    label: 'Predicted',
    tooltip: 'Proposed by the AI surrogate model.',
    className: 'bg-info/15 text-info',
  },
  verified: {
    label: 'Verified',
    tooltip: 'Recomputed by the physics solver. This is the authoritative value.',
    className: 'bg-success/15 text-success',
  },
  stored: {
    label: 'Stored lattice',
    tooltip:
      'Solver-computed values of the nearest lattice already in the dataset. A suggestion for your target, not a result for your request.',
    className: 'bg-success/10 text-success',
  },
  estimate: {
    label: 'Estimate',
    tooltip:
      'Derived client-side from input values. Not computed by the solver.',
    className: 'bg-surface-2 text-muted',
  },
  automatic: {
    label: 'Automatic',
    tooltip: 'Set automatically based on zone geometry and loading.',
    className: 'bg-surface-2 text-muted',
  },
}

interface SourceTagProps {
  source: SourceKind
  className?: string
}

export function SourceTag({ source, className }: SourceTagProps) {
  const config = SOURCE_CONFIG[source]
  if (!config) return null

  return (
    <Tooltip content={config.tooltip}>
      <span
        className={cn(
          'inline-block rounded px-1.5 py-0.5 text-[10px] leading-tight font-medium tracking-wide uppercase',
          config.className,
          className,
        )}
      >
        {config.label}
      </span>
    </Tooltip>
  )
}
