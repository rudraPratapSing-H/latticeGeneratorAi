import { lazy, Suspense, useMemo, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { PageHeader } from '@/components/layout/PageHeader'
import { ImplantBanner } from '@/features/implant/ImplantBanner'
import { ZoneStrip } from '@/features/implant/ZoneStrip'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { InlineAlert } from '@/components/feedback/InlineAlert'
import { ErrorState } from '@/components/feedback/ErrorState'
import { useImplantZones, useImplantResult, useZoneLattices } from '@/hooks/useImplant'
import type { ShapeZone } from '@/lib/implantGeometry'
import { useClipboard } from '@/hooks/useClipboard'
import { apiClient } from '@/api/client'
import { Download, FileText, Copy, RotateCcw } from 'lucide-react'
import { toast } from 'sonner'
import type { ImplantResult, VerificationLabel } from '@/api/implantTypes'

const ImplantModel3D = lazy(() => import('@/features/implant/ImplantModel3D'))

const LABEL_TEXT: Record<VerificationLabel, string> = {
  solver_verified_infinite_lattice: 'Solver-verified (infinite lattice)',
  beam_model_estimate: 'Beam-model estimate',
  geometry_only: 'Geometry only',
  not_modelled: 'Not modelled',
}

function Label({ kind }: { kind: VerificationLabel }) {
  return (
    <Badge variant={kind === 'solver_verified_infinite_lattice' ? 'success' : 'neutral'} className="text-[10px]">
      {LABEL_TEXT[kind]}
    </Badge>
  )
}

function ZoneRows({ result }: { result: ImplantResult }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full text-xs">
        <thead className="border-b border-line text-left text-muted">
          <tr>
            <th className="p-3 font-medium">Zone</th>
            <th className="p-3 font-medium">Range (mm)</th>
            <th className="p-3 font-medium">Design stress</th>
            <th className="p-3 font-medium">Chosen cell, stiffness z / strength z</th>
            <th className="p-3 font-medium">Finite-block stiffness z</th>
          </tr>
        </thead>
        <tbody>
          {result.zones.map((z) => (
            <tr key={z.id} className="border-b border-line last:border-0 align-top">
              <td className="p-3 font-medium text-text">
                {z.name}
                <div className="mt-0.5 text-[11px] font-normal text-muted">{z.kind === 'lattice' ? 'lattice' : 'solid'}</div>
              </td>
              <td className="p-3 font-mono">
                {z.range_mm[0].toFixed(0)}–{z.range_mm[1].toFixed(0)}
              </td>
              <td className="p-3 font-mono">{z.stress_mpa.toFixed(0)} MPa</td>
              <td className="p-3">
                {z.verified ? (
                  <div className="space-y-1">
                    <div className="font-mono text-text">
                      {z.verified.stiffness_gpa.z.toFixed(2)} GPa / {z.verified.strength_mpa.z.toFixed(1)} MPa
                    </div>
                    <div className="flex items-center gap-1.5 text-[11px] text-muted">
                      <Label kind="solver_verified_infinite_lattice" />
                      <span className="font-mono">{z.candidate_id}</span>
                    </div>
                  </div>
                ) : (
                  <span className="text-muted">Solid: no lattice cell</span>
                )}
              </td>
              <td className="p-3">
                {z.check && z.check.stiffness_z_gpa != null ? (
                  <div className="space-y-1">
                    <div className="font-mono text-text">
                      {z.check.stiffness_z_gpa.toFixed(2)} GPa
                      {z.check.ratio_to_infinite != null && (
                        <span className="text-muted"> ({(100 * z.check.ratio_to_infinite).toFixed(0)}% of the infinite lattice)</span>
                      )}
                    </div>
                    <Label kind="beam_model_estimate" />
                  </div>
                ) : z.check?.warning ? (
                  <span className="text-muted">{z.check.warning}</span>
                ) : (
                  <span className="text-muted">–</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function ImplantFinalPage() {
  const { implantId } = useParams<{ implantId: string }>()
  const navigate = useNavigate()
  const { copy } = useClipboard()

  const { data: zones, table } = useImplantZones(implantId!)
  const { data: result, isLoading, error } = useImplantResult(implantId!)

  const chosen = useMemo(
    () =>
      (result?.zones ?? [])
        .filter((z) => z.kind === 'lattice' && z.candidate_id)
        .map((z) => ({ zoneId: z.id, candidateId: z.candidate_id! })),
    [result],
  )
  const { lattices, pending: latticesPending } = useZoneLattices(implantId!, chosen)
  const shapeZones = useMemo<ShapeZone[]>(
    () =>
      (zones ?? []).map((z) => ({
        id: z.id,
        name: z.name,
        kind: z.kind,
        startMm: z.range_mm[0],
        endMm: z.range_mm[1],
        areaMm2: z.area_mm2,
      })),
    [zones],
  )

  const [downloadingStl, setDownloadingStl] = useState(false)
  const [downloadingReport, setDownloadingReport] = useState(false)

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-24" />
        <Skeleton className="h-64" />
      </div>
    )
  }

  if (error || !result) {
    return (
      <ErrorState
        title="Could not load the assembled implant"
        message="The assembly may not be finished, or the implant id is wrong."
        onBack={() => navigate('/implant')}
      />
    )
  }

  const download = async (path: string, filename: string, type: string, setBusy: (b: boolean) => void, okMsg: string) => {
    setBusy(true)
    try {
      const response = await apiClient.get(`/api/implants/${implantId}/${path}`, { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([response.data], { type }))
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
      toast.success(okMsg)
    } catch {
      toast.error('The download is not available (the replayed demo data has no STL file).')
    } finally {
      setBusy(false)
    }
  }
  const handleDownloadStl = () =>
    download('export.stl', `implant_${implantId}.stl`, 'model/stl', setDownloadingStl, 'STL downloaded')
  const handleDownloadReport = () =>
    download('report', `implant_report_${implantId}.md`, 'text/markdown', setDownloadingReport, 'Report downloaded')

  const s = result.summary

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <PageHeader
          title="Assembled implant"
          description={`Implant ${implantId} · ${result.zones.length} zones, ${s.cell_mm} mm cell, ${s.length_mm.toFixed(0)} mm long.`}
        />
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => copy(window.location.href, 'Link copied')}>
            <Copy className="mr-1.5 h-3.5 w-3.5" />
            Copy link
          </Button>
          <Button size="sm" variant="secondary" onClick={handleDownloadReport} loading={downloadingReport}>
            <FileText className="mr-1.5 h-3.5 w-3.5" />
            Download report
          </Button>
          <Button size="sm" variant="primary" onClick={handleDownloadStl} loading={downloadingStl}>
            <Download className="mr-1.5 h-3.5 w-3.5" />
            Download STL
          </Button>
        </div>
      </div>

      <ImplantBanner />

      {result.warnings.length > 0 && (
        <div className="space-y-1">
          {result.warnings.map((w, i) => (
            <InlineAlert key={i} variant="info">
              {w}
            </InlineAlert>
          ))}
        </div>
      )}

      {shapeZones.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-text">3D model of the assembled implant</h3>
          <Suspense fallback={<Skeleton className="h-[28rem]" />}>
            <ImplantModel3D
              zones={shapeZones}
              lattices={lattices}
              lengthMm={table?.length_mm ?? s.length_mm}
              pending={latticesPending}
            />
          </Suspense>
        </div>
      )}

      {zones && <ZoneStrip zones={zones} totalLengthMm={table?.length_mm ?? s.length_mm} onBoundaryChange={() => {}} readOnly />}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ['Mass', `${s.mass_g.toFixed(0)} g`, 'geometry_only'],
          ['Lattice share of the volume', `${s.lattice_share_pct.toFixed(1)}%`, 'geometry_only'],
          ['Triangles', s.triangles.toLocaleString(), 'geometry_only'],
          ['STL size', `${(s.stl_bytes / 1e6).toFixed(1)} MB`, 'geometry_only'],
        ].map(([k, v, l]) => (
          <div key={k} className="rounded-xl border border-line bg-surface p-3">
            <div className="text-[11px] text-muted">{k}</div>
            <div className="mt-0.5 font-mono text-sm font-medium text-text">{v}</div>
            <div className="mt-1">
              <Label kind={l as VerificationLabel} />
            </div>
          </div>
        ))}
      </div>

      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-text">Zones</h3>
        <ZoneRows result={result} />
      </div>

      <div className="rounded-xl border border-line bg-surface p-4 space-y-2">
        <h3 className="text-sm font-semibold text-text">What each number is</h3>
        <ul className="space-y-1.5 text-xs text-muted">
          {(Object.keys(result.verification) as VerificationLabel[]).map((k) => (
            <li key={k} className="flex flex-wrap items-start gap-2">
              <Label kind={k} />
              <span className="flex-1 min-w-[16rem]">{result.verification[k]}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-line">
        <Button variant="ghost" size="sm" onClick={() => navigate('/implant')}>
          <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
          Design another implant
        </Button>
        <p className="text-[11px] text-muted max-w-md text-right">{result.disclaimer}</p>
      </div>
    </div>
  )
}
