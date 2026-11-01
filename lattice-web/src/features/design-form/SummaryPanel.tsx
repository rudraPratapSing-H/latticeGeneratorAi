import { useState } from 'react'
import type { DesignFormValues } from '@/features/design-form/defaults'
import type { DesignRequest } from '@/api/types'
import { buildRequest } from '@/features/design-form/buildRequest'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { useClipboard } from '@/hooks/useClipboard'
import { useRecentRuns } from '@/hooks/useRecentRuns'
import { useMaterials } from '@/hooks/useMaterials'
import { partVolumeCm3, solidMassG, relDensityFromMass, voigtBound } from '@/lib/units'
import { fmtRelDensity, fmtMass, fmtGpa } from '@/lib/format'
import { AXES, AXIS_LABELS, jobPath } from '@/config/constants'
import { Link } from 'react-router-dom'
import { Clock, Code2, Copy } from 'lucide-react'

interface SummaryPanelProps {
  values: DesignFormValues
}

export function SummaryPanel({ values }: SummaryPanelProps) {
  const [showJson, setShowJson] = useState(false)
  const { copy } = useClipboard()
  const recentRuns = useRecentRuns()
  const { data: materials } = useMaterials()

  const material = materials?.find((m) => m.id === values.material)

  // Compute volume and mass hints
  const sizeX = parseFloat(values.partSizeX) || 0
  const sizeY = parseFloat(values.partSizeY) || 0
  const sizeZ = parseFloat(values.partSizeZ) || 0
  const volume = partVolumeCm3([sizeX, sizeY, sizeZ])
  const solidMass = material ? solidMassG(volume, material.density_g_cm3) : 0

  let rd: number | null = null
  if (values.useRelDensity) {
    rd = parseFloat(values.relDensity) || null
  } else {
    const mass = parseFloat(values.maxMassG) || 0
    if (solidMass > 0 && mass > 0) {
      rd = relDensityFromMass(mass, solidMass)
    }
  }

  const lighterPct = rd !== null ? ((1 - rd) * 100).toFixed(0) : null

  // Voigt bound hints for stiffness
  const stiffnessWarnings: string[] = []
  if (material && rd !== null) {
    const maxRd = values.useRelDensity ? (rd ?? 0.5) : rd
    AXES.forEach((axis) => {
      const dontCare = values[`stiffnessDontCare${axis.toUpperCase()}` as keyof DesignFormValues]
      if (dontCare) return
      const target = parseFloat(
        values[`stiffness${axis.toUpperCase()}` as keyof DesignFormValues] as string,
      )
      if (!isFinite(target) || target <= 0) return
      const bound = voigtBound(maxRd, material.E_gpa)
      if (target > bound) {
        stiffnessWarnings.push(
          `${AXIS_LABELS[axis]}: target ${target} GPa exceeds Voigt bound ≈ ${fmtGpa(bound)}`,
        )
      }
    })
  }

  let request: DesignRequest | null = null
  try {
    request = buildRequest(values)
  } catch {
    // Form not valid yet
  }

  const requestJson = request ? JSON.stringify(request, null, 2) : null

  return (
    <Card className="sticky top-20">
      <CardHeader>
        <h3 className="text-text text-sm font-semibold">Summary</h3>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {/* Volume & Mass */}
        {volume > 0 && (
          <div className="space-y-1.5">
            <div className="flex justify-between">
              <span className="text-muted">Part volume</span>
              <span className="font-mono tabular-nums">{volume.toFixed(1)} cm³</span>
            </div>
            {solidMass > 0 && (
              <div className="flex justify-between">
                <span className="text-muted">Solid mass</span>
                <span className="font-mono tabular-nums">{fmtMass(solidMass)}</span>
              </div>
            )}
            {rd !== null && (
              <>
                <div className="flex justify-between">
                  <span className="text-muted">Relative density</span>
                  <span className="font-mono tabular-nums">{fmtRelDensity(rd)}</span>
                </div>
                {lighterPct && (
                  <p className="text-accent text-xs">{lighterPct}% lighter than solid</p>
                )}
              </>
            )}
            {rd !== null && rd >= 1 && (
              <p className="text-warning text-xs">
                Relative density ≥ 100%: heavier than a solid block
              </p>
            )}
            {rd !== null && rd < 0.01 && rd > 0 && (
              <p className="text-warning text-xs">
                Very low relative density — may not be manufacturable
              </p>
            )}
          </div>
        )}

        {/* Voigt warnings */}
        {stiffnessWarnings.length > 0 && (
          <div className="space-y-1">
            {stiffnessWarnings.map((w) => (
              <p key={w} className="text-warning text-xs">
                ⚠ Likely infeasible: {w}
              </p>
            ))}
          </div>
        )}

        {/* Request JSON */}
        {requestJson && (
          <button
            type="button"
            onClick={() => setShowJson(true)}
            className="text-accent flex cursor-pointer items-center gap-1.5 text-xs hover:underline"
          >
            <Code2 className="h-3.5 w-3.5" />
            View request JSON
          </button>
        )}

        {/* Recent runs */}
        <div className="border-line border-t pt-3">
          <h4 className="text-muted mb-2 flex items-center gap-1.5 text-xs font-medium">
            <Clock className="h-3.5 w-3.5" />
            Recent runs
          </h4>
          {recentRuns.length === 0 ? (
            <p className="text-faint text-xs">Your runs will appear here.</p>
          ) : (
            <ul className="space-y-1.5">
              {recentRuns.map((run) => (
                <li key={run.jobId}>
                  <Link
                    to={jobPath(run.jobId)}
                    className="hover:bg-surface-2 flex items-center justify-between rounded-md px-2 py-1.5 text-xs transition-colors"
                  >
                    <div>
                      <span className="text-accent font-mono">{run.jobId}</span>
                      <span className="text-faint ml-2">{run.material}</span>
                    </div>
                    <span className="text-faint">
                      {new Date(run.timestamp).toLocaleTimeString(undefined, {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>

      {/* Request JSON dialog */}
      <Dialog open={showJson} onOpenChange={setShowJson}>
        <DialogContent className="max-w-2xl">
          <DialogTitle>Request JSON</DialogTitle>
          <div className="relative mt-4">
            <pre className="bg-surface-2 text-text max-h-96 overflow-x-auto rounded-lg p-4 font-mono text-xs">
              {requestJson}
            </pre>
            <Button
              variant="ghost"
              size="sm"
              className="absolute top-2 right-2"
              onClick={() => requestJson && copy(requestJson, 'Request JSON copied')}
            >
              <Copy className="h-3.5 w-3.5" />
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
