import type { TargetMode } from '@/api/types'
import { Segmented } from '@/components/ui/segmented'
import { MODE_LABELS } from '@/config/constants'

interface ModeSelectorProps {
  value: TargetMode
  onChange: (value: TargetMode) => void
  tolerancePct?: string
}

const MODE_OPTIONS: Array<{ value: TargetMode; label: string }> = [
  { value: 'about', label: MODE_LABELS.about },
  { value: 'at_least', label: MODE_LABELS.at_least },
  { value: 'at_most', label: MODE_LABELS.at_most },
]

export function ModeSelector({ value, onChange, tolerancePct }: ModeSelectorProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Segmented value={value} onChange={onChange} options={MODE_OPTIONS} />
      {value === 'about' && tolerancePct && (
        <span className="text-muted text-xs">± {tolerancePct}%</span>
      )}
    </div>
  )
}
