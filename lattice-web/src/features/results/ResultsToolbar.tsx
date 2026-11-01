import { Segmented } from '@/components/ui/segmented'
import { Select, SelectItem } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import type { DesignRequest } from '@/api/types'

export type ViewMode = 'cards' | 'compare'
export type SortKey = 'rank' | 'match_error' | 'mass' | 'rel_density'

interface ResultsToolbarProps {
  viewMode: ViewMode
  onViewModeChange: (v: ViewMode) => void
  sortKey: SortKey
  onSortKeyChange: (v: SortKey) => void
  onlyMeeting: boolean
  onOnlyMeetingChange: (v: boolean) => void
  request: DesignRequest | null
}

export function ResultsToolbar({
  viewMode,
  onViewModeChange,
  sortKey,
  onSortKeyChange,
  onlyMeeting,
  onOnlyMeetingChange,
  request,
}: ResultsToolbarProps) {
  return (
    <div className="bg-bg/85 sm:sticky sm:top-14 z-30 -mx-4 flex flex-wrap items-center gap-3 border-b border-line/70 px-4 py-2.5 backdrop-blur-md sm:-mx-6 sm:px-6">
      <Segmented
        value={viewMode}
        onChange={(v) => onViewModeChange(v as ViewMode)}
        options={[
          { value: 'cards', label: 'Cards' },
          { value: 'compare', label: 'Compare' },
        ]}
      />
      <Select value={sortKey} onChange={(v) => onSortKeyChange(v as SortKey)} className="w-40">
        <SelectItem value="rank">Rank</SelectItem>
        <SelectItem value="match_error">Match error</SelectItem>
        <SelectItem value="mass">Mass</SelectItem>
        <SelectItem value="rel_density">Relative density</SelectItem>
      </Select>
      {request && (
        <Switch
          checked={onlyMeeting}
          onChange={onOnlyMeetingChange}
          label="Only meeting all targets"
        />
      )}
    </div>
  )
}
