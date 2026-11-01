import { Progress } from '@/components/ui/progress'

interface ProgressPanelProps {
  progress: number
  message: string
}

export function ProgressPanel({ progress, message }: ProgressPanelProps) {
  return (
    <div className="space-y-3">
      <Progress value={progress} showLabel />
      <p className="text-muted flex items-center gap-2 text-sm" role="status" aria-live="polite">
        {progress < 1 && <span className="bg-accent animate-pulse-dot inline-block h-1.5 w-1.5 shrink-0 rounded-full" />}
        <span className="min-w-0 truncate">{message}</span>
      </p>
    </div>
  )
}
