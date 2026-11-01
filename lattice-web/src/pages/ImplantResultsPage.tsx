import { useState, useMemo, useEffect, lazy, Suspense } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { PageHeader } from '@/components/layout/PageHeader'
import { ImplantBanner } from '@/features/implant/ImplantBanner'
import { CandidateCard } from '@/features/results/CandidateCard'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { Segmented } from '@/components/ui/segmented'
import { ErrorState } from '@/components/feedback/ErrorState'
import { useImplantZones, useZoneCandidates, useAssembleImplant, useAssembleJob } from '@/hooks/useImplant'
import { InlineAlert } from '@/components/feedback/InlineAlert'
import { Layers, CheckCircle2, ShieldCheck, Box, Eye, ExternalLink } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/cn'
import { designPath, AXES, AXIS_LABELS } from '@/config/constants'
import type { Candidate, DesignRequest } from '@/api/types'

const LatticeViewer = lazy(() => import('@/components/LatticeViewer'))

const round2 = (v: number | null | undefined) => (v == null ? v : Math.round(v * 100) / 100)

/** The live state of one lattice zone's search, shown on its tab until a cell is chosen. */
function ZoneStatusBadge({ implantId, zoneId }: { implantId: string; zoneId: string }) {
  const { data } = useZoneCandidates(implantId, zoneId)
  const status = data?.job?.status
  const searching = status === 'queued' || status === 'running'
  let label = 'pending'
  if (status === 'queued') label = 'queued'
  else if (status === 'running') label = `searching ${Math.round((data?.job?.progress ?? 0) * 100)}%`
  else if (status === 'failed' || status === 'cancelled') label = status
  else if (data && data.candidates.length > 0) label = 'choose a cell'
  return (
    <Badge
      variant={!searching && label === 'choose a cell' ? 'accent' : 'neutral'}
      className="text-[10px] px-1 py-0"
    >
      {label}
    </Badge>
  )
}

export default function ImplantResultsPage() {
  const { implantId } = useParams<{ implantId: string }>()
  const navigate = useNavigate()

  const { data: zones, table, isLoading: zonesLoading, error: zonesError } = useImplantZones(implantId!)
  const [assembleJobId, setAssembleJobId] = useState<string | undefined>()
  const [pickedZoneIdx, setSelectedZoneIdx] = useState<number | null>(null)
  const firstLattice = zones?.findIndex((z) => z.kind === 'lattice') ?? -1
  const selectedZoneIdx = pickedZoneIdx ?? Math.max(0, firstLattice)
  const [choices, setChoices] = useState<Record<string, string>>({})

  // 3D Inspection modal state
  const [inspectCandidate, setInspectCandidate] = useState<Candidate | null>(null)
  const [inspectTiles, setInspectTiles] = useState(1)
  const [inspectRenderMode, setInspectRenderMode] = useState<'solid' | 'wireframe'>('solid')
  const [inspectColorByAxis, setInspectColorByAxis] = useState(false)

  const currentZone = zones?.[selectedZoneIdx]
  const isLatticeZone = currentZone?.kind === 'lattice'

  const {
    data: candidatesData,
    isLoading: candLoading,
  } = useZoneCandidates(implantId!, currentZone?.id ?? '')

  const assembleMutation = useAssembleImplant(implantId!)
  const assembleJob = useAssembleJob(assembleJobId)
  const assembling =
    assembleMutation.isPending || assembleJob.data?.status === 'queued' || assembleJob.data?.status === 'running'
  const assembleStatus = assembleJob.data?.status

  useEffect(() => {
    if (assembleStatus === 'done') {
      toast.success('The implant is assembled.')
      navigate(`/implant/${implantId}/result`)
    } else if (assembleStatus === 'failed') {
      toast.error(assembleJob.data?.message || 'The assembly failed')
    }
  }, [assembleStatus, assembleJob.data?.message, implantId, navigate])

  const zoneJobId = candidatesData?.job?.job_id ?? ''

  // Build zone request for target comparisons
  const zoneRequest = useMemo<DesignRequest | null>(() => {
    if (!currentZone) return null
    return {
      material: 'ti64',
      part: { size_mm: [30, 30, currentZone.thickness_mm], cell_mm: table?.cell_mm ?? 5 },
      target: {
        stiffness_gpa: {
          x: round2(currentZone.requirement.stiffness_gpa.x.value),
          y: round2(currentZone.requirement.stiffness_gpa.y.value),
          z: round2(currentZone.requirement.stiffness_gpa.z.value),
        },
        strength_mpa: {
          x: round2(currentZone.requirement.strength_mpa.x.value),
          y: round2(currentZone.requirement.strength_mpa.y.value),
          z: round2(currentZone.requirement.strength_mpa.z.value),
        },
        rel_density: currentZone.requirement.density?.value ?? 0.15,
      },
      modes: { stiffness: 'about', strength: 'at_least', weight: 'at_most' },
      tolerance_pct: 10,
      n_results: 3,
    }
  }, [currentZone, table?.cell_mm])

  if (zonesLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-24" />
        <Skeleton className="h-64" />
      </div>
    )
  }

  if (zonesError || !zones) {
    return (
      <ErrorState
        title="Could not load implant results"
        message="Please check the implant ID."
        onBack={() => navigate('/implant')}
      />
    )
  }

  const latticeZones = zones.filter((z) => z.kind === 'lattice')
  const allLatticeZonesSelected =
    latticeZones.length > 0 && latticeZones.every((z) => Boolean(choices[z.id]))

  const handleSelectCandidate = (candidateId: string) => {
    if (!currentZone) return
    setChoices({ ...choices, [currentZone.id]: candidateId })
    toast.success(`Selected design for ${currentZone.name || currentZone.id}`)
  }

  const handleAssemble = () => {
    assembleMutation.mutate(choices, {
      onSuccess: (res) => {
        setAssembleJobId(res.job_id)
      },
      onError: (err) => {
        toast.error(err.message || 'Failed to assemble implant')
      },
    })
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <PageHeader
          title="Choose a lattice cell for each zone"
          description={`Implant ${implantId} · Each candidate is a solver-verified lattice cell (infinite-lattice numbers).`}
        />
        <Button
          size="lg"
          onClick={handleAssemble}
          disabled={!allLatticeZonesSelected || assembling}
          loading={assembling}
        >
          <Layers className="mr-1.5 h-4 w-4" />
          Assemble Full Implant ({Object.keys(choices).length}/{latticeZones.length} selected)
        </Button>
      </div>

      <ImplantBanner />

      {assembling && (
        <InlineAlert variant="info">
          Assembling: {assembleJob.data?.message ?? 'queued'} ({Math.round((assembleJob.data?.progress ?? 0) * 100)}%)
          {assembleJob.data?.queue_position ? ` · ${assembleJob.data.queue_position} job(s) ahead` : ''}
        </InlineAlert>
      )}
      {assembleStatus === 'failed' && <InlineAlert variant="error">{assembleJob.data?.message}</InlineAlert>}

      {/* Zone selection tabs */}
      <div className="flex gap-2 border-b border-line pb-2 overflow-x-auto">
        {zones.map((zone, idx) => {
          const isSelected = selectedZoneIdx === idx
          const hasChoice = Boolean(choices[zone.id])
          const isLattice = zone.kind === 'lattice'

          return (
            <button
              key={zone.id}
              onClick={() => setSelectedZoneIdx(idx)}
              className={cn(
                'flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium transition-colors shrink-0',
                isSelected
                  ? 'bg-accent text-accent-fg'
                  : 'bg-surface hover:bg-surface-2 text-muted hover:text-text border border-line',
              )}
            >
              <span>{zone.name || `Zone ${idx + 1}`}</span>
              {isLattice ? (
                hasChoice ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                ) : (
                  <ZoneStatusBadge implantId={implantId!} zoneId={zone.id} />
                )
              ) : (
                <Badge variant="neutral" className="text-[10px] px-1 py-0">
                  solid
                </Badge>
              )}
            </button>
          )
        })}
      </div>

      {/* Active zone content */}
      {currentZone && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-surface p-4">
            <div>
              <h3 className="text-sm font-semibold text-text">
                {currentZone.name || currentZone.id} ({currentZone.range_mm[0]}–{currentZone.range_mm[1]} mm)
              </h3>
              <p className="text-xs text-muted">
                Thickness: {currentZone.thickness_mm.toFixed(1)} mm &middot; Area: {currentZone.area_mm2.toFixed(0)} mm² &middot; Stress: {currentZone.stress_mpa.toFixed(1)} MPa
              </p>
            </div>
            {isLatticeZone && candidatesData?.grid && (
              <div className="flex items-center gap-2 text-xs font-mono text-muted">
                <Box className="h-4 w-4 text-accent" />
                <span>
                  Grid: {candidatesData.grid.whole_cells} whole cells ({candidatesData.grid.cell_mm} mm cell)
                </span>
              </div>
            )}
          </div>

          {!isLatticeZone ? (
            <div className="rounded-xl border border-line bg-surface p-8 text-center space-y-2">
              <ShieldCheck className="h-8 w-8 text-accent mx-auto" />
              <h4 className="text-sm font-semibold text-text">This section will be printed solid</h4>
              <p className="text-xs text-muted max-w-md mx-auto">
                {currentZone.reason || 'Designated solid for high stress or fatigue resistance requirements.'}
              </p>
            </div>
          ) : candidatesData?.job && (candidatesData.job.status === 'queued' || candidatesData.job.status === 'running') ? (
            <div className="rounded-xl border border-line bg-surface p-6 text-sm text-muted">
              Searching this zone: {candidatesData.job.message ?? candidatesData.job.status}
              {candidatesData.job.queue_position ? ` · ${candidatesData.job.queue_position} job(s) ahead` : ''}
              {candidatesData.job.progress != null ? ` · ${Math.round(candidatesData.job.progress * 100)}%` : ''}
            </div>
          ) : candidatesData?.job && (candidatesData.job.status === 'failed' || candidatesData.job.status === 'cancelled') ? (
            <InlineAlert variant="error">The search for this zone {candidatesData.job.status}: {candidatesData.job.message}</InlineAlert>
          ) : candLoading ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Skeleton className="h-64" />
              <Skeleton className="h-64" />
              <Skeleton className="h-64" />
            </div>
          ) : candidatesData && candidatesData.candidates.length > 0 ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {candidatesData.candidates.map((cand) => {
                const isPicked = choices[currentZone.id] === cand.id

                return (
                  <div
                    key={cand.id}
                    className={cn(
                      'relative rounded-xl border transition-all flex flex-col justify-between overflow-hidden',
                      isPicked
                        ? 'border-accent ring-2 ring-accent ring-offset-2 ring-offset-bg'
                        : 'border-line',
                    )}
                  >
                    <CandidateCard
                      candidate={cand}
                      jobId={zoneJobId}
                      linkSearch={`?fromImplant=${implantId}`}
                      request={zoneRequest}
                    />

                    <div className="p-3 bg-surface border-t border-line space-y-2">
                      <div className="flex items-center gap-2">
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="w-1/2 text-xs"
                          onClick={() => {
                            setInspectCandidate(cand)
                            setInspectTiles(1)
                          }}
                        >
                          <Eye className="mr-1 h-3.5 w-3.5 text-accent" />
                          Inspect 3D
                        </Button>

                        <Button
                          type="button"
                          size="sm"
                          variant={isPicked ? 'primary' : 'secondary'}
                          className="w-1/2 text-xs"
                          onClick={() => handleSelectCandidate(cand.id)}
                        >
                          {isPicked ? (
                            <>
                              <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> Selected
                            </>
                          ) : (
                            'Select'
                          )}
                        </Button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-sm text-muted">No candidates found for this zone.</p>
          )}
        </div>
      )}

      {/* Assemble Action Bar */}
      <div className="flex justify-between items-center pt-4 border-t border-line">
        <span className="text-xs text-muted font-mono">
          {Object.keys(choices).length} of {latticeZones.length} lattice zones selected
        </span>
        <Button
          size="lg"
          onClick={handleAssemble}
          disabled={!allLatticeZonesSelected || assembling}
          loading={assembling}
          className="min-w-[180px]"
        >
          <Layers className="mr-1.5 h-4 w-4" />
          Assemble Implant
        </Button>
      </div>

      {/* 3D Inspection Modal */}
      {inspectCandidate && (
        <Dialog open={!!inspectCandidate} onOpenChange={() => setInspectCandidate(null)}>
          <DialogContent className="max-w-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-line">
              <DialogTitle className="text-base font-semibold">
                3D Inspection: Candidate <span className="font-mono text-accent">{inspectCandidate.id}</span>
              </DialogTitle>
              <Badge variant={inspectCandidate.matches_targets ? 'success' : 'warning'}>
                Rank #{inspectCandidate.rank} &middot; {inspectCandidate.match_error_pct.toFixed(1)}% error
              </Badge>
            </div>

            {/* 3D Viewport */}
            <div className="space-y-4 pt-2">
              <div className="aspect-[4/3] rounded-lg overflow-hidden border border-line bg-surface-2">
                <Suspense fallback={<Skeleton className="h-full w-full" />}>
                  <LatticeViewer
                    lattice={inspectCandidate.lattice}
                    variant="full"
                    tiles={inspectTiles}
                    renderMode={inspectRenderMode}
                    colorByAxis={inspectColorByAxis}
                  />
                </Suspense>
              </div>

              {/* Viewport controls */}
              <div className="flex flex-wrap items-center justify-between gap-3 text-xs bg-surface-2/60 p-3 rounded-lg border border-line">
                <div className="flex items-center gap-2">
                  <label className="text-muted">Tiles:</label>
                  <input
                    type="range"
                    min={1}
                    max={5}
                    value={inspectTiles}
                    onChange={(e) => setInspectTiles(parseInt(e.target.value))}
                    className="accent-accent w-20"
                  />
                  <span className="font-mono font-medium">{inspectTiles}</span>
                </div>

                <Segmented
                  value={inspectRenderMode}
                  onChange={(v) => setInspectRenderMode(v as 'solid' | 'wireframe')}
                  options={[
                    { value: 'solid', label: 'Solid' },
                    { value: 'wireframe', label: 'Wire' },
                  ]}
                />

                <label className="flex items-center gap-1.5 cursor-pointer text-muted">
                  <input
                    type="checkbox"
                    checked={inspectColorByAxis}
                    onChange={(e) => setInspectColorByAxis(e.target.checked)}
                    className="accent-accent cursor-pointer"
                  />
                  Colour by axis
                </label>
              </div>

              {/* Properties Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
                <div className="rounded border border-line p-2 bg-surface">
                  <div className="text-muted text-[10px]">Stiffness (GPa)</div>
                  <div className="font-medium text-text mt-0.5">
                    {AXES.map((a) => (
                      <span key={a} className="mr-1.5">
                        <span className={cn('font-semibold', `text-axis-${a}`)}>{AXIS_LABELS[a]}</span>:
                        {inspectCandidate.verified.stiffness_gpa[a].toFixed(1)}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="rounded border border-line p-2 bg-surface">
                  <div className="text-muted text-[10px]">Strength (MPa)</div>
                  <div className="font-medium text-text mt-0.5">
                    {AXES.map((a) => (
                      <span key={a} className="mr-1.5">
                        <span className={cn('font-semibold', `text-axis-${a}`)}>{AXIS_LABELS[a]}</span>:
                        {inspectCandidate.verified.strength_mpa[a].toFixed(0)}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="rounded border border-line p-2 bg-surface">
                  <div className="text-muted text-[10px]">Relative Density</div>
                  <div className="font-medium text-text mt-0.5">
                    {(inspectCandidate.rel_density * 100).toFixed(1)}%
                  </div>
                </div>

                <div className="rounded border border-line p-2 bg-surface">
                  <div className="text-muted text-[10px]">Strut Radius</div>
                  <div className="font-medium text-text mt-0.5">
                    {inspectCandidate.lattice.strut_radius_mm.toFixed(3)} mm
                  </div>
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex items-center justify-between pt-2 border-t border-line">
                <Link
                  to={designPath(zoneJobId, inspectCandidate.id) + `?fromImplant=${implantId}`}
                  className="text-xs text-accent hover:underline flex items-center gap-1"
                >
                  <ExternalLink className="h-3 w-3" />
                  Open the full detail page
                </Link>

                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setInspectCandidate(null)}
                  >
                    Close
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => {
                      if (currentZone) {
                        handleSelectCandidate(inspectCandidate.id)
                        setInspectCandidate(null)
                      }
                    }}
                  >
                    <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
                    Select for this Zone
                  </Button>
                </div>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}

