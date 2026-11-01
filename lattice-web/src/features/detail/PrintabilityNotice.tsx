import { InlineAlert } from '@/components/feedback/InlineAlert'
import { checkPrintability } from '@/lib/printability'

interface PrintabilityNoticeProps {
  strutRadiusMm: number
  cellSizeMm: number
}

export function PrintabilityNotice({ strutRadiusMm, cellSizeMm }: PrintabilityNoticeProps) {
  const result = checkPrintability(strutRadiusMm, cellSizeMm)

  return (
    <InlineAlert variant={result.passes ? 'info' : 'warning'}>
      <div className="space-y-1">
        <p className="font-medium">{result.message}</p>
        <p className="text-muted text-[11px]">
          Always verify against your specific additive manufacturing printer, slicer tolerances, and material shrinkage before production.
        </p>
      </div>
    </InlineAlert>
  )
}
