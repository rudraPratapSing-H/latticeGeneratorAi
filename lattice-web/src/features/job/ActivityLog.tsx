import { fmtTime } from '@/lib/format'
import { cn } from '@/lib/cn'

interface ActivityLogProps {
  messages: Array<{ message: string; timestamp: number }>
  className?: string
}

export function ActivityLog({ messages, className }: ActivityLogProps) {
  if (messages.length === 0) return null

  return (
    <div className={cn('space-y-1', className)}>
      <h3 className="text-muted text-xs font-medium tracking-wide uppercase">Activity</h3>
      <div className="bg-surface-2 max-h-48 space-y-0.5 overflow-y-auto rounded-lg p-3">
        {messages.map((msg, i) => (
          <div key={i} className="flex gap-2 text-xs">
            <span className="text-faint shrink-0 font-mono tabular-nums">
              {fmtTime(msg.timestamp)}
            </span>
            <span className="text-muted">{msg.message}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
