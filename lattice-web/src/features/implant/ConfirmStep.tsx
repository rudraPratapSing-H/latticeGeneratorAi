import { useState } from 'react'
import type { CreateImplantResponse, ConfirmImplantRequest, ImplantFields } from '@/api/implantTypes'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { InlineAlert } from '@/components/feedback/InlineAlert'
import { AXES, AXIS_LABELS } from '@/config/constants'
import { Check, ShieldCheck, AlertTriangle, ArrowUp } from 'lucide-react'

interface ConfirmStepProps {
  implantData: CreateImplantResponse
  onConfirm: (confirmRequest: ConfirmImplantRequest) => void
  isConfirming: boolean
}

export function ConfirmStep({ implantData, onConfirm, isConfirming }: ConfirmStepProps) {
  const { mesh_report, fields: initialFields } = implantData

  const [units, setUnits] = useState<'mm' | 'm' | 'inch'>(
    (mesh_report.guessed_units as 'mm' | 'm' | 'inch') || 'mm',
  )

  // Find longest axis by default
  const [sizeX, sizeY, sizeZ] = mesh_report.size_mm
  const defaultAxis = sizeZ >= sizeX && sizeZ >= sizeY ? 'z' : sizeX >= sizeY ? 'x' : 'y'
  const [axis, setAxis] = useState<'auto' | 'x' | 'y' | 'z'>('auto')
  const [flip, setFlip] = useState(false)

  // Editable fields
  const [fields, setFields] = useState<ImplantFields>(initialFields)

  const longestSideMm = Math.max(sizeX, sizeY, sizeZ)
  const isSuspiciousScale = longestSideMm < 20 || longestSideMm > 600

  const handleConfirm = () => {
    onConfirm({
      units,
      axis,
      flip,
      body_index: 0,
      fields,
    })
  }

  return (
    <div className="space-y-6">
      {/* Mesh Report Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-text">Mesh Analysis Report</h2>
            <span className="font-mono text-xs text-accent">ID: {implantData.implant_id}</span>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 text-xs">
            <div className="rounded-lg border border-line bg-surface-2 p-3">
              <span className="text-muted">Watertight</span>
              <p className="mt-1 font-semibold flex items-center gap-1">
                {mesh_report.watertight ? (
                  <span className="text-success flex items-center gap-1">
                    <Check className="h-4 w-4" /> Yes
                  </span>
                ) : (
                  <span className="text-danger flex items-center gap-1">
                    <AlertTriangle className="h-4 w-4" /> Non-manifold
                  </span>
                )}
              </p>
            </div>

            <div className="rounded-lg border border-line bg-surface-2 p-3">
              <span className="text-muted">Shell Bodies</span>
              <p className="mt-1 font-semibold font-mono text-text">
                {mesh_report.bodies} {mesh_report.bodies === 1 ? 'solid' : 'bodies'}
              </p>
            </div>

            <div className="rounded-lg border border-line bg-surface-2 p-3">
              <span className="text-muted">Dimensions (X &times; Y &times; Z)</span>
              <p className="mt-1 font-semibold font-mono text-text">
                {sizeX.toFixed(0)} &times; {sizeY.toFixed(0)} &times; {sizeZ.toFixed(0)} mm
              </p>
            </div>

            <div className="rounded-lg border border-line bg-surface-2 p-3">
              <span className="text-muted">Detected Units</span>
              <p className="mt-1 font-semibold font-mono text-accent">
                {mesh_report.guessed_units}
              </p>
            </div>
          </div>

          {(!mesh_report.watertight || mesh_report.bodies > 1) && (
            <InlineAlert variant="warning">
              {mesh_report.warnings?.join('; ') ||
                'Mesh is not strictly watertight or contains multiple bodies. Automated zoning will use bounding convex slices.'}
            </InlineAlert>
          )}

          {isSuspiciousScale && (
            <InlineAlert variant="warning">
              Measured longest dimension is {longestSideMm.toFixed(1)} mm. For human femoral implants, typical lengths are 100–220 mm. Please verify the unit scale below.
            </InlineAlert>
          )}
        </CardContent>
      </Card>

      {/* Confirmation & Coordinate Orientation */}
      <Card>
        <CardHeader>
          <h2 className="text-base font-semibold text-text">
            2. Confirm coordinates &amp; request details
          </h2>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* Unit selection */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-text">Unit System</label>
            <div className="flex gap-4">
              {(['mm', 'm', 'inch'] as const).map((u) => (
                <label key={u} className="flex items-center gap-1.5 text-xs text-text cursor-pointer">
                  <input
                    type="radio"
                    name="units"
                    checked={units === u}
                    onChange={() => setUnits(u)}
                    className="accent-accent"
                  />
                  <span>{u === 'mm' ? 'Millimeters (mm)' : u === 'm' ? 'Meters (m)' : 'Inches (in)'}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Long axis & flip */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-text">Long axis</label>
              <div className="flex gap-2">
                {(['auto', ...AXES] as const).map((a) => (
                  <button
                    key={a}
                    type="button"
                    onClick={() => setAxis(a)}
                    className={`flex-1 py-1.5 text-xs font-medium rounded-md border transition-colors ${
                      axis === a
                        ? 'border-accent bg-accent-soft text-accent'
                        : 'border-line text-muted hover:text-text'
                    }`}
                  >
                    {a === 'auto' ? `Auto (${defaultAxis.toUpperCase()})` : `Axis ${AXIS_LABELS[a]}`}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-1.5 flex flex-col justify-end">
              <Switch
                checked={flip}
                onChange={setFlip}
                label="Flip direction (swap the thin and thick ends)"
              />
            </div>
          </div>

          {/* Orientation schematic preview */}
          <div className="rounded-lg border border-line bg-surface-2 p-4 flex items-center justify-between">
            <div className="space-y-1">
              <span className="text-xs font-semibold text-text">Orientation Check</span>
              <p className="text-xs text-muted">
                Long axis: <strong className="text-accent">{axis === 'auto' ? `auto (${defaultAxis.toUpperCase()})` : axis.toUpperCase()}</strong> &middot; Direction: {flip ? 'Reversed' : 'Standard'} (0 mm = thin end, {longestSideMm.toFixed(0)} mm = thick end)
              </p>
            </div>
            <div className="flex items-center gap-2 font-mono text-xs text-accent">
              <ArrowUp className={`h-5 w-5 transition-transform ${flip ? 'rotate-180' : ''}`} />
              <span>Head End</span>
            </div>
          </div>

          {/* Extracted fields */}
          <div className="space-y-3 border-t border-line pt-4">
            <div className="space-y-1">
              <span className="text-xs font-semibold text-text">Extracted Case Parameters</span>
              <p className="text-[11px] text-muted">
                These were read from your description. They never include stiffness or strength numbers. Please confirm or edit.
              </p>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <label className="text-xs text-muted">Implant Type</label>
                <input
                  type="text"
                  value={fields.implant_type}
                  onChange={(e) => setFields({ ...fields, implant_type: e.target.value })}
                  className="w-full rounded border border-line bg-surface px-2.5 py-1.5 text-xs text-text focus:border-accent focus:outline-none"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs text-muted">Patient Body Weight (kg)</label>
                <input
                  type="number"
                  value={fields.body_weight_kg ?? ''}
                  onChange={(e) =>
                    setFields({ ...fields, body_weight_kg: parseFloat(e.target.value) || null })
                  }
                  className="w-full rounded border border-line bg-surface px-2.5 py-1.5 text-xs text-text focus:border-accent focus:outline-none"
                />
              </div>

              <div className="space-y-1 sm:col-span-2">
                <label className="text-xs text-muted">Activity level</label>
                <select
                  value={fields.activity ?? ''}
                  onChange={(e) => setFields({ ...fields, activity: (e.target.value || null) as ImplantFields['activity'] })}
                  className="w-full rounded border border-line bg-surface px-2.5 py-1.5 text-xs text-text focus:border-accent focus:outline-none"
                >
                  <option value="">Not stated (a moderate default is used and shown)</option>
                  {(['sedentary', 'low', 'moderate', 'active', 'high'] as const).map((a) => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-1 sm:col-span-2">
                <label className="text-xs text-muted">Special Constraints &amp; Rules</label>
                <input
                  type="text"
                  value={fields.special_rules.join(', ')}
                  onChange={(e) =>
                    setFields({
                      ...fields,
                      special_rules: e.target.value.split(',').map((s) => s.trim()),
                    })
                  }
                  className="w-full rounded border border-line bg-surface px-2.5 py-1.5 text-xs text-text focus:border-accent focus:outline-none"
                />
              </div>
            </div>
          </div>

          <div className="flex justify-end pt-3">
            <Button
              type="button"
              size="lg"
              onClick={handleConfirm}
              loading={isConfirming}
              className="min-w-[160px]"
            >
              <ShieldCheck className="mr-1.5 h-4 w-4" />
              Confirm &amp; Proceed to Zones
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

