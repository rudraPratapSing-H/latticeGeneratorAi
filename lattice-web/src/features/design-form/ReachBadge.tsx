import type { ReachLevel } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { AlertCircle, CheckCircle2, HelpCircle, XCircle } from 'lucide-react'

interface ReachBadgeProps {
  level: ReachLevel
  distancePct?: number
  message?: string
}

const LEVEL_CONFIG: Record<
  ReachLevel,
  {
    label: string
    variant: 'success' | 'info' | 'warning' | 'danger'
    icon: typeof CheckCircle2
    explanation: string
  }
> = {
  covered: {
    label: 'Covered',
    variant: 'success',
    icon: CheckCircle2,
    explanation: 'Within tolerance of a stored lattice. A match is very likely.',
  },
  extended: {
    label: 'Extended',
    variant: 'info',
    icon: HelpCircle,
    explanation: '10–25% from stored lattices. The AI search will invent a new candidate.',
  },
  outside: {
    label: 'Outside',
    variant: 'warning',
    icon: AlertCircle,
    explanation: '>25% from dataset coverage. A close match is unlikely; proceed with caution.',
  },
  infeasible: {
    label: 'Infeasible',
    variant: 'danger',
    icon: XCircle,
    explanation: 'Exceeds theoretical beam lattice limits (Voigt/yield bounds). No design can achieve this.',
  },
}

export function ReachBadge({ level, distancePct, message }: ReachBadgeProps) {
  const config = LEVEL_CONFIG[level]
  const Icon = config.icon

  return (
    <div className="space-y-1.5 rounded-lg border border-line bg-surface-2 p-3 text-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 font-medium">
          <Badge variant={config.variant} className="flex items-center gap-1">
            <Icon className="h-3 w-3" />
            {config.label}
          </Badge>
          {distancePct !== undefined && distancePct > 0 && (
            <span className="text-muted tabular-nums">
              ({distancePct.toFixed(1)}% from stored)
            </span>
          )}
        </div>
      </div>
      <p className="text-text">{message || config.explanation}</p>
      <p className="text-muted text-[11px]">{config.explanation}</p>
    </div>
  )
}

