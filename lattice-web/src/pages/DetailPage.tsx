import { useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useJob, useCandidateFromJob } from '@/hooks/useJob'
import { useDesign } from '@/hooks/useDesign'
import { loadRequest } from '@/lib/storage'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/feedback/ErrorState'
import { DetailHeader } from '@/features/detail/DetailHeader'
import { MetricGrid } from '@/features/detail/MetricGrid'
import { PropertyTable } from '@/features/detail/PropertyTable'
import { ViewerPanel } from '@/features/detail/ViewerPanel'
import { DownloadMenu } from '@/features/detail/DownloadMenu'
import { PrintabilityNotice } from '@/features/detail/PrintabilityNotice'
import { MIN_PRINT_DIAMETER_MM, designPath, jobPath } from '@/config/constants'
import type { Candidate } from '@/api/types'

export default function DetailPage() {
  const { jobId, designId } = useParams<{ jobId: string; designId: string }>()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const fromImplant = searchParams.get('fromImplant')

  // Try from job cache first
  const { data: candidateFromJob } = useCandidateFromJob(jobId!, designId!)
  const { data: job } = useJob(jobId!)

  // Fallback fetch
  const {
    data: candidateFromApi,
    isLoading,
    error,
  } = useDesign(designId!, {
    enabled: !candidateFromJob,
  })

  const candidate: Candidate | undefined = candidateFromJob ?? candidateFromApi
  const request = useMemo(() => job?.request ?? loadRequest(jobId!), [job, jobId])

  const [tiles, setTiles] = useState(1)
  const [renderMode, setRenderMode] = useState<'solid' | 'wireframe'>('solid')
  const [colorByAxis, setColorByAxis] = useState(false)

  // Keyboard navigation between designs
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (!job || !candidate) return
      const idx = job.candidates.findIndex((c) => c.id === candidate.id)
      const implantParam = fromImplant ? `?fromImplant=${fromImplant}` : ''
      if (e.key === 'ArrowLeft' && idx > 0) {
        navigate(designPath(jobId!, job.candidates[idx - 1].id) + implantParam)
      }
      if (e.key === 'ArrowRight' && idx < job.candidates.length - 1) {
        navigate(designPath(jobId!, job.candidates[idx + 1].id) + implantParam)
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [job, candidate, jobId, fromImplant, navigate])

  useEffect(() => {
    if (candidate) {
      document.title = `Design ${candidate.id} · Lattice Designer`
    }
  }, [candidate])

  // Loading
  if (isLoading || (!candidate && !error)) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Skeleton className="aspect-[4/3]" />
          <div className="space-y-3">
            <Skeleton className="h-6 w-32" />
            <Skeleton className="h-40" />
            <Skeleton className="h-60" />
          </div>
        </div>
      </div>
    )
  }

  // Not found
  if (error || !candidate) {
    return (
      <ErrorState
        title="Design not found"
        message={`We couldn't find design ${designId}.`}
        onBack={() =>
          fromImplant ? navigate(`/implant/${fromImplant}/results`) : navigate(jobPath(jobId!))
        }
        backLabel={fromImplant ? 'Back to implant candidates' : 'Back to results'}
      />
    )
  }

  const tolerance = request?.tolerance_pct ?? 10
  const strutDiameter = candidate.lattice.strut_radius_mm * 2
  const isThinStrut = strutDiameter < MIN_PRINT_DIAMETER_MM

  // Prev/next
  const candidateIdx = job?.candidates.findIndex((c) => c.id === candidate.id) ?? -1
  const prevId = candidateIdx > 0 ? (job?.candidates[candidateIdx - 1]?.id ?? null) : null
  const nextId =
    job && candidateIdx < job.candidates.length - 1
      ? (job.candidates[candidateIdx + 1]?.id ?? null)
      : null

  return (
    <div className="animate-fade-in space-y-6">
      <DetailHeader
        candidate={candidate}
        jobId={jobId!}
        prevId={prevId}
        nextId={nextId}
        tolerance={tolerance}
        fromImplant={fromImplant}
      />

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[1fr_1fr]">
        {/* Left: Viewer */}
        <ViewerPanel
          lattice={candidate.lattice}
          tiles={tiles}
          onTilesChange={setTiles}
          renderMode={renderMode}
          onRenderModeChange={setRenderMode}
          colorByAxis={colorByAxis}
          onColorByAxisChange={setColorByAxis}
        />

        {/* Right: Properties */}
        <div className="space-y-5">
          <MetricGrid
            candidate={candidate}
            isThinStrut={isThinStrut}
            strutDiameter={strutDiameter}
          />

          <PropertyTable candidate={candidate} request={request} tolerance={tolerance} />

          <PrintabilityNotice
            strutRadiusMm={candidate.lattice.strut_radius_mm}
            cellSizeMm={candidate.lattice.cell_size_mm}
          />

          <DownloadMenu candidate={candidate} tiles={tiles} request={request} />
        </div>
      </div>
    </div>
  )
}
