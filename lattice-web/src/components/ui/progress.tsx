import { cn } from '@/lib/cn'

interface ProgressProps {
  value: number // 0..1
  className?: string
  showLabel?: boolean
}

export function Progress({ value, className, showLabel }: ProgressProps) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100)

  return (
    <div className={cn('flex items-center gap-3', className)}>
      <div
        className="bg-surface-2 relative h-2 flex-1 overflow-hidden rounded-full"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="bg-accent relative h-full overflow-hidden rounded-full transition-[width] duration-700 ease-out"
          style={{ width: `${pct}%` }}
        >
          {pct > 0 && pct < 100 && (
            <span className="animate-sweep absolute inset-y-0 left-0 w-1/3 bg-gradient-to-r from-transparent via-white/40 to-transparent" />
          )}
        </div>
      </div>
      {showLabel && (
        <span className="text-muted w-12 text-right font-mono text-sm tabular-nums">{pct}%</span>
      )}
    </div>
  )
}
