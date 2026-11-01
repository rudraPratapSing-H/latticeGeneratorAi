import { lazy, Suspense, useMemo } from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/cn'
import type { Zone } from '@/api/implantTypes'
import type { ShapeZone } from '@/lib/implantGeometry'

const NO_LATTICES = {}

const ImplantModel3D = lazy(() => import('@/features/implant/ImplantModel3D'))

interface ZoneModelsProps {
  zones: Zone[]
  totalLengthMm: number
  activeZoneId?: string
  onSelectZone?: (zoneId: string) => void
}

/** A 3D view of each axial zone, drawn from the zone table. Solid blocks until the search has chosen the lattice. */
export function ZoneModels({ zones, totalLengthMm, activeZoneId, onSelectZone }: ZoneModelsProps) {
  const shapes = useMemo<ShapeZone[]>(
    () =>
      zones.map((z) => ({
        id: z.id,
        name: z.name,
        kind: 'solid', // before the search every zone is drawn as a solid block
        startMm: z.range_mm[0],
        endMm: z.range_mm[1],
        areaMm2: z.area_mm2,
      })),
    [zones],
  )

  return (
    <div className="space-y-2">
      <div>
        <h3 className="text-text text-sm font-semibold">3D view of each zone</h3>
        <p className="text-muted text-xs">
          Each zone as a solid block, before the search. The search fills it with the lattice cell
          it picks, and the assembled implant shows the result.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {zones.map((z) => (
          <div
            key={z.id}
            className={cn(
              'bg-surface space-y-2 rounded-xl border p-3 transition-colors',
              activeZoneId === z.id ? 'border-accent ring-accent ring-1' : 'border-line',
            )}
          >
            <button
              type="button"
              className="flex w-full flex-wrap items-baseline justify-between gap-2 text-left"
              onClick={() => onSelectZone?.(z.id)}
            >
              <span className="text-text text-sm font-medium">{z.name}</span>
              <span className="text-muted font-mono text-[11px]">
                {z.range_mm[0].toFixed(1)}–{z.range_mm[1].toFixed(1)} mm · {z.cells} cells ·{' '}
                {z.kind}
              </span>
            </button>
            <Suspense fallback={<Skeleton className="h-72" />}>
              <ImplantModel3D
                zones={shapes}
                lattices={NO_LATTICES}
                lengthMm={totalLengthMm}
                onlyZoneId={z.id}
                compact
              />
            </Suspense>
          </div>
        ))}
      </div>
    </div>
  )
}
