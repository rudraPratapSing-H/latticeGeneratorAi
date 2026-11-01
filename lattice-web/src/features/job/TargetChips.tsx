import { Badge } from '@/components/ui/badge'
import { SourceTag } from '@/components/ui/source-tag'
import type { DesignRequest } from '@/api/types'
import { AXES, AXIS_LABELS, MODE_LABELS } from '@/config/constants'

interface TargetChipsProps {
  request: DesignRequest & { _metadata?: { adjustedFields?: string[] } }
}

export function TargetChips({ request }: TargetChipsProps) {
  const adjusted = new Set(request._metadata?.adjustedFields ?? [])
  const chips: Array<{
    key: string
    label: string
    source: 'requested' | 'adjusted'
  }> = []

  // Stiffness
  const stiff = request.target.stiffness_gpa
  AXES.forEach((axis) => {
    const val = stiff[axis]
    if (val !== null) {
      const fieldKey = `stiffness${axis.toUpperCase()}`
      chips.push({
        key: fieldKey,
        label: `Stiffness ${AXIS_LABELS[axis]} ${val} GPa · ${MODE_LABELS[request.modes.stiffness]}${
          request.modes.stiffness === 'about' ? ` ±${request.tolerance_pct}%` : ''
        }`,
        source: adjusted.has(fieldKey) ? 'adjusted' : 'requested',
      })
    }
  })

  // Strength
  const strengthKey = 'strength_mpa' in request.target ? 'strength_mpa' : 'yield_strength_mpa'
  const strengthVals = request.target[strengthKey as keyof typeof request.target] as
    | Record<string, number | null>
    | undefined
  if (strengthVals && typeof strengthVals === 'object') {
    AXES.forEach((axis) => {
      const val = strengthVals[axis]
      if (val !== null && val !== undefined) {
        const fieldKey = `strength${axis.toUpperCase()}`
        chips.push({
          key: fieldKey,
          label: `Strength ${AXIS_LABELS[axis]} ${val} MPa · ${MODE_LABELS[request.modes.strength]}`,
          source: adjusted.has(fieldKey) ? 'adjusted' : 'requested',
        })
      }
    })
  }

  // Weight
  if ('max_mass_g' in request.target) {
    chips.push({
      key: 'maxMassG',
      label: `Mass ≤ ${request.target.max_mass_g} g · ${MODE_LABELS[request.modes.weight]}`,
      source: 'requested',
    })
  } else if ('rel_density' in request.target) {
    chips.push({
      key: 'relDensity',
      label: `ρ ≤ ${request.target.rel_density} · ${MODE_LABELS[request.modes.weight]}`,
      source: 'requested',
    })
  }

  return (
    <div className="flex flex-wrap gap-2">
      {chips.map((chip) => (
        <Badge
          key={chip.key}
          variant="neutral"
          className="flex items-center gap-1.5 font-mono text-[11px]"
        >
          <span>{chip.label}</span>
          <SourceTag source={chip.source} />
        </Badge>
      ))}
    </div>
  )
}
