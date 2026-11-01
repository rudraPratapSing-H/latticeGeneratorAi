import { Suspense, lazy } from 'react'
import type { Lattice } from '@/api/types'
import { Segmented } from '@/components/ui/segmented'
import { Skeleton } from '@/components/ui/skeleton'

const LatticeViewer = lazy(() => import('@/components/LatticeViewer'))

interface ViewerPanelProps {
  lattice: Lattice
  tiles: number
  onTilesChange: (tiles: number) => void
  renderMode: 'solid' | 'wireframe'
  onRenderModeChange: (mode: 'solid' | 'wireframe') => void
  colorByAxis: boolean
  onColorByAxisChange: (v: boolean) => void
}

export function ViewerPanel({
  lattice,
  tiles,
  onTilesChange,
  renderMode,
  onRenderModeChange,
  colorByAxis,
  onColorByAxisChange,
}: ViewerPanelProps) {
  return (
    <div className="space-y-3 lg:sticky lg:top-20">
      <div className="thumb-stage border-line relative aspect-[4/3] overflow-hidden rounded-xl border shadow-sm">
        <span className="thumb-tick top-3 left-3 border-t border-l" />
        <span className="thumb-tick top-3 right-3 border-t border-r" />
        <span className="thumb-tick bottom-3 left-3 border-b border-l" />
        <span className="thumb-tick right-3 bottom-3 border-r border-b" />
        <Suspense fallback={<Skeleton className="h-full w-full" />}>
          <LatticeViewer
            lattice={lattice}
            variant="full"
            tiles={tiles}
            renderMode={renderMode}
            colorByAxis={colorByAxis}
            className="bg-transparent"
          />
        </Suspense>
      </div>

      {/* Controls */}
      <div className="border-line bg-surface flex flex-wrap items-center gap-x-5 gap-y-3 rounded-xl border px-4 py-3">
        <div className="flex items-center gap-2.5">
          <label htmlFor="tiles-range" className="text-muted text-xs font-medium">
            Tiles
          </label>
          <input
            id="tiles-range"
            type="range"
            min={1}
            max={5}
            value={tiles}
            onChange={(e) => onTilesChange(parseInt(e.target.value))}
            className="accent-accent h-1.5 w-24 cursor-pointer"
          />
          <span className="w-12 font-mono text-xs tabular-nums">
            {tiles}&times;{tiles}&times;{tiles}
          </span>
        </div>
        <Segmented
          value={renderMode}
          onChange={(v) => onRenderModeChange(v as 'solid' | 'wireframe')}
          options={[
            { value: 'solid', label: 'Solid' },
            { value: 'wireframe', label: 'Wire' },
          ]}
        />
        <label className="text-muted hover:text-text flex cursor-pointer items-center gap-1.5 text-xs transition-colors">
          <input
            type="checkbox"
            checked={colorByAxis}
            onChange={(e) => onColorByAxisChange(e.target.checked)}
            className="accent-accent h-3.5 w-3.5 cursor-pointer"
          />
          Colour by axis
        </label>
      </div>

      <div className="text-muted flex items-center justify-between px-1 text-xs">
        <p className="font-mono tabular-nums">
          {lattice.nodes.length} nodes · {lattice.edges.length} edges
        </p>
        <div className="flex gap-3">
          <span className="flex items-center gap-1">
            <span className="bg-axis-x h-2 w-2 rounded-full" /> X
          </span>
          <span className="flex items-center gap-1">
            <span className="bg-axis-y h-2 w-2 rounded-full" /> Y
          </span>
          <span className="flex items-center gap-1">
            <span className="bg-axis-z h-2 w-2 rounded-full" /> Z
          </span>
        </div>
      </div>
    </div>
  )
}
