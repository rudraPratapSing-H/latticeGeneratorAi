import type { Candidate } from '@/api/types'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { SourceTag } from '@/components/ui/source-tag'
import { fmtMm, fmtMass, fmtPct, fmtRelDensity } from '@/lib/format'
import { cn } from '@/lib/cn'

interface MetricGridProps {
  candidate: Candidate
  isThinStrut: boolean
  strutDiameter: number
}

export function MetricGrid({ candidate, isThinStrut, strutDiameter }: MetricGridProps) {
  const nodeCount = candidate.lattice.nodes.length
  const edgeCount = candidate.lattice.edges.length

  return (
    <Card>
      <CardHeader>
        <h2 className="text-text text-sm font-semibold">Metrics</h2>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Metric label="Relative density" value={fmtRelDensity(candidate.rel_density)} />
          <div className="space-y-0.5">
            <div className="flex items-center gap-1">
              <span className="text-muted text-xs">Mass</span>
              <SourceTag source="estimate" />
            </div>
            <p className="font-mono text-sm font-medium tabular-nums">
              {fmtMass(candidate.mass_g)}
            </p>
          </div>
          <Metric label="Strut radius" value={fmtMm(candidate.lattice.strut_radius_mm)} />
          <Metric label="Strut diameter" value={fmtMm(strutDiameter)} warn={isThinStrut} />
          <Metric label="Cell size" value={fmtMm(candidate.lattice.cell_size_mm)} />
          <Metric label="Nodes / Edges" value={`${nodeCount} / ${edgeCount}`} />
          <Metric label="Match error" value={fmtPct(candidate.match_error_pct)} />
        </div>
      </CardContent>
    </Card>
  )
}

function Metric({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="space-y-0.5">
      <span className="text-muted text-xs">{label}</span>
      <p className={cn('font-mono text-sm font-medium tabular-nums', warn && 'text-warning')}>
        {value}
      </p>
    </div>
  )
}
