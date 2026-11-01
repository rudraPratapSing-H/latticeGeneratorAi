import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { PageHeader } from '@/components/layout/PageHeader'
import { ImplantBanner } from '@/features/implant/ImplantBanner'
import { ZoneStrip } from '@/features/implant/ZoneStrip'
import { ZoneTable } from '@/features/implant/ZoneTable'
import { ZoneModels } from '@/features/implant/ZoneModels'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/feedback/ErrorState'
import { InlineAlert } from '@/components/feedback/InlineAlert'
import { useImplantZones, useSearchImplantZones } from '@/hooks/useImplant'
import { Search } from 'lucide-react'
import { toast } from 'sonner'
import type { Zone } from '@/api/implantTypes'

export default function ImplantZonesPage() {
  const { implantId } = useParams<{ implantId: string }>()
  const navigate = useNavigate()

  const { data: zones, table, isLoading, error, updateZones, isUpdating, updateError } = useImplantZones(implantId!)
  const searchMutation = useSearchImplantZones(implantId!)

  const [activeZoneId, setActiveZoneId] = useState<string | undefined>()

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-20" />
        <Skeleton className="h-32" />
        <Skeleton className="h-64" />
      </div>
    )
  }

  if (error || !zones) {
    return (
      <ErrorState
        title="Could not load implant zones"
        message="The implant data may have expired or is invalid."
        onBack={() => navigate('/implant')}
        backLabel="Back to implant upload"
      />
    )
  }

  const handleBoundaryChange = (idx: number, newBoundaryMm: number) => {
    const updated = [...zones]
    // Zone idx ends at newBoundaryMm; zone idx + 1 starts at newBoundaryMm
    updated[idx] = {
      ...updated[idx],
      range_mm: [updated[idx].range_mm[0], newBoundaryMm],
      thickness_mm: newBoundaryMm - updated[idx].range_mm[0],
    }
    updated[idx + 1] = {
      ...updated[idx + 1],
      range_mm: [newBoundaryMm, updated[idx + 1].range_mm[1]],
      thickness_mm: updated[idx + 1].range_mm[1] - newBoundaryMm,
    }
    updateZones(updated)
  }

  const handleUpdateZone = (idx: number, updatedZone: Zone) => {
    const next = [...zones]
    next[idx] = updatedZone
    updateZones(next)
  }

  const handleSearchAll = () => {
    searchMutation.mutate(undefined, {
      onSuccess: () => {
        toast.success('Initiated lattice searches for all zones.')
        navigate(`/implant/${implantId}/results`)
      },
      onError: (err) => {
        toast.error(err.message || 'Failed to start zone searches')
      },
    })
  }

  const latticeZonesCount = zones.filter((z) => z.kind === 'lattice').length

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <PageHeader
          title="Zoning &amp; Target Optimization"
          description={`Implant ${implantId} · The stem is split along its length into zones.`}
        />
        <Button
          size="lg"
          onClick={handleSearchAll}
          disabled={searchMutation.isPending || isUpdating || latticeZonesCount === 0}
          loading={searchMutation.isPending}
        >
          <Search className="mr-1.5 h-4 w-4" />
          Search lattices for all zones ({latticeZonesCount})
        </Button>
      </div>

      <ImplantBanner />

      {(table?.warnings?.length ?? 0) > 0 && (
        <div className="space-y-1">
          {table?.warnings?.map((w, i) => (
            <InlineAlert key={i} variant="warning">{w}</InlineAlert>
          ))}
        </div>
      )}
      {updateError && <InlineAlert variant="error">That change was refused: {(updateError as Error).message}</InlineAlert>}

      {table?.load && (
        <details className="rounded-xl border border-line bg-surface p-4 text-xs">
          <summary className="cursor-pointer font-semibold text-text">
            Load used for the design stress: {table.load.governing.name} ({table.load.governing.force_n.toFixed(0)} N), safety factor {table.load.safety_factor}
          </summary>
          <ul className="mt-3 space-y-1 text-muted">
            {table.load.assumptions.map((a) => (
              <li key={a.name}>
                {a.name}: <span className="font-mono text-text">{String(a.value)} {a.unit}</span> ({a.source}
                {a.todo ? ', placeholder' : ''})
              </li>
            ))}
          </ul>
          <p className="mt-2 text-muted">{table.disclaimer}</p>
        </details>
      )}

      {/* 1D Zone Strip Visualization & Controls */}
      <ZoneStrip
        zones={zones}
        totalLengthMm={table?.length_mm ?? 160}
        onBoundaryChange={handleBoundaryChange}
        activeZoneId={activeZoneId}
        onSelectZone={setActiveZoneId}
      />

      {/* 3D view of each zone */}
      <ZoneModels
        zones={zones}
        totalLengthMm={table?.length_mm ?? 160}
        activeZoneId={activeZoneId}
        onSelectZone={setActiveZoneId}
      />

      {/* Zone Table */}
      <ZoneTable
        zones={zones}
        onUpdateZone={handleUpdateZone}
        activeZoneId={activeZoneId}
      />

      <div className="flex justify-end pt-2">
        <Button
          size="lg"
          onClick={handleSearchAll}
          disabled={searchMutation.isPending || isUpdating || latticeZonesCount === 0}
          loading={searchMutation.isPending}
          className="min-w-[200px]"
        >
          <Search className="mr-1.5 h-4 w-4" />
          Search lattices for all zones
        </Button>
      </div>
    </div>
  )
}
