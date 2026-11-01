import { useState } from 'react'
import type { Zone, ZoneKind } from '@/api/implantTypes'
import { Select, SelectItem } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { SourceTag } from '@/components/ui/source-tag'
import { InlineAlert } from '@/components/feedback/InlineAlert'
import { AXES, AXIS_LABELS } from '@/config/constants'
import { cn } from '@/lib/cn'

interface ZoneTableProps {
  zones: Zone[]
  onUpdateZone: (index: number, updated: Zone) => void
  activeZoneId?: string
}

export function ZoneTable({ zones, onUpdateZone, activeZoneId }: ZoneTableProps) {
  const [mode, setMode] = useState<'automatic' | 'semi-automatic'>('automatic')

  // Check stiffness difference between adjacent zones (> 3x warning)
  const jumpWarnings: string[] = []
  for (let i = 0; i < zones.length - 1; i++) {
    const z1 = zones[i]
    const z2 = zones[i + 1]
    const s1 = z1.requirement.stiffness_gpa.z.value ?? 1
    const s2 = z2.requirement.stiffness_gpa.z.value ?? 1
    const ratio = Math.max(s1, s2) / Math.max(0.1, Math.min(s1, s2))
    if (ratio > 3) {
      jumpWarnings.push(
        `Stiffness between "${z1.name}" and "${z2.name}" changes by ${ratio.toFixed(1)}× (>3×). A solid interface plate is used between them.`,
      )
    }
  }

  const allSolid = zones.every((z) => z.kind === 'solid')

  return (
    <div className="space-y-4">
      {/* Mode toggle */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-text">Zone requirements</h3>
          <p className="text-xs text-muted">
            Target stiffness and strength per zone.
          </p>
        </div>

        <div className="flex items-center gap-1.5 rounded-lg border border-line bg-surface-2 p-1 text-xs">
          <button
            type="button"
            onClick={() => setMode('automatic')}
            className={cn(
              'rounded px-2.5 py-1 font-medium transition-colors',
              mode === 'automatic'
                ? 'bg-accent text-accent-fg'
                : 'text-muted hover:text-text',
            )}
          >
            Automatic
          </button>
          <button
            type="button"
            onClick={() => setMode('semi-automatic')}
            className={cn(
              'rounded px-2.5 py-1 font-medium transition-colors',
              mode === 'semi-automatic'
                ? 'bg-accent text-accent-fg'
                : 'text-muted hover:text-text',
            )}
          >
            Semi-automatic
          </button>
        </div>
      </div>

      {jumpWarnings.length > 0 && (
        <div className="space-y-1">
          {jumpWarnings.map((w, idx) => (
            <InlineAlert key={idx} variant="info">
              {w}
            </InlineAlert>
          ))}
        </div>
      )}

      {allSolid && (
        <InlineAlert variant="warning">
          <div className="space-y-1">
            <p className="font-semibold">All zones are currently set to Solid.</p>
            <p className="text-xs text-muted">
              The design stress is above what any stored lattice carries, so every zone is solid. A lower body weight or activity level gives lattice zones.
            </p>
          </div>
        </InlineAlert>
      )}

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-line bg-surface shadow-sm">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-line bg-surface-2 text-muted">
              <th scope="col" className="px-3 py-2.5 font-medium">Zone</th>
              <th scope="col" className="px-3 py-2.5 font-medium">Axial Range</th>
              <th scope="col" className="px-3 py-2.5 font-medium">Geometry</th>
              <th scope="col" className="px-3 py-2.5 font-medium">Type</th>
              <th scope="col" className="px-3 py-2.5 font-medium">Stiffness (Target vs Snapped)</th>
              <th scope="col" className="px-3 py-2.5 font-medium">Strength Target</th>
              <th scope="col" className="px-3 py-2.5 font-medium">Reach</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line/60">
            {zones.map((zone, idx) => {
              const isSelected = activeZoneId === zone.id
              const isOverStiff = (zone.requirement.stiffness_gpa.z.value ?? 0) > 13.1

              return (
                <tr
                  key={zone.id}
                  className={cn(
                    'transition-colors hover:bg-surface-2/40',
                    isSelected && 'bg-accent-soft/30',
                  )}
                >
                  {/* Name */}
                  <td className="px-3 py-3 font-medium text-text">
                    <p className="font-semibold">{zone.name || `Zone ${idx + 1}`}</p>
                    <span className="font-mono text-[10px] text-faint">{zone.id}</span>
                  </td>

                  {/* Range */}
                  <td className="px-3 py-3 font-mono tabular-nums text-muted">
                    {zone.range_mm[0]}–{zone.range_mm[1]} mm
                    <p className="text-[11px] text-faint">thickness {zone.thickness_mm.toFixed(1)} mm</p>
                  </td>

                  {/* Geometry */}
                  <td className="px-3 py-3 text-muted">
                    <p className="font-mono tabular-nums">{zone.area_mm2.toFixed(0)} mm²</p>
                    <p className="text-[11px] text-faint font-mono">
                      design stress {zone.stress_mpa.toFixed(0)} MPa
                    </p>
                  </td>

                  {/* Kind selector */}
                  <td className="px-3 py-3">
                    <div className="space-y-1 w-32">
                      <Select
                        value={zone.kind}
                        onChange={(v) =>
                          onUpdateZone(idx, {
                            ...zone,
                            kind: v as ZoneKind,
                            reason:
                              v === 'solid'
                                ? 'User designated solid'
                                : undefined,
                          })
                        }
                      >
                        <SelectItem value="lattice">Lattice</SelectItem>
                        <SelectItem value="solid">Solid</SelectItem>
                        <SelectItem value="undecided">Undecided</SelectItem>
                      </Select>
                      {zone.reason && (
                        <p className="text-[10px] text-muted italic leading-tight">
                          {zone.reason}
                        </p>
                      )}
                      {isOverStiff && zone.kind === 'lattice' && (
                        <Badge variant="warning" className="text-[9px] px-1 py-0">
                          Solid, or softer lattice
                        </Badge>
                      )}
                    </div>
                  </td>

                  {/* Stiffness Target vs Snapped */}
                  <td className="px-3 py-3 font-mono tabular-nums">
                    <div className="space-y-0.5">
                      {AXES.map((axis) => {
                        const target = zone.requirement.stiffness_gpa[axis].value
                        const snapped = zone.reach?.snapped?.stiffness_gpa[axis]
                        if (target == null) return null

                        return (
                          <div key={axis} className="flex items-center gap-1.5 text-[11px]">
                            <span className={cn('font-semibold', `text-axis-${axis}`)}>
                              {AXIS_LABELS[axis]}:
                            </span>
                            <span>{target.toFixed(1)}</span>
                            {snapped != null && snapped !== target && (
                              <span className="text-accent">&rarr; {snapped.toFixed(1)}</span>
                            )}
                            <SourceTag
                              source={zone.requirement.stiffness_gpa[axis].source}
                            />
                          </div>
                        )
                      })}
                    </div>
                  </td>

                  {/* Strength Target */}
                  <td className="px-3 py-3 font-mono tabular-nums">
                    <div className="space-y-0.5">
                      {AXES.map((axis) => {
                        const target = zone.requirement.strength_mpa[axis].value
                        const snapped = zone.reach?.snapped?.strength_mpa[axis]
                        if (target == null) return null

                        return (
                          <div key={axis} className="flex items-center gap-1.5 text-[11px]">
                            <span className={cn('font-semibold', `text-axis-${axis}`)}>
                              {AXIS_LABELS[axis]}:
                            </span>
                            <span>{target.toFixed(0)}</span>
                            {snapped != null && snapped !== target && (
                              <span className="text-accent">&rarr; {snapped.toFixed(0)}</span>
                            )}
                            <SourceTag
                              source={zone.requirement.strength_mpa[axis].source}
                            />
                          </div>
                        )
                      })}
                    </div>
                  </td>

                  {/* Reach Level */}
                  <td className="px-3 py-3">
                    {zone.reach ? (
                      <Badge
                        variant={
                          zone.reach.level === 'covered'
                            ? 'success'
                            : zone.reach.level === 'extended'
                              ? 'info'
                              : 'warning'
                        }
                      >
                        {zone.reach.level}
                      </Badge>
                    ) : (
                      <span className="text-faint">&mdash;</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
