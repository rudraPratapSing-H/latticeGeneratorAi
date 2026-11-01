import { Info } from 'lucide-react'
import { Tooltip } from '@/components/ui/tooltip'

interface InfoTipProps {
  content: React.ReactNode
}

export function InfoTip({ content }: InfoTipProps) {
  return (
    <Tooltip content={content}>
      <button
        type="button"
        className="text-faint hover:text-muted inline-flex cursor-pointer"
        aria-label="More info"
      >
        <Info className="h-3.5 w-3.5" />
      </button>
    </Tooltip>
  )
}
