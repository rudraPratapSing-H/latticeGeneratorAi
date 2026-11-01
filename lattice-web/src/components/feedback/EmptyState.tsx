import { Inbox } from 'lucide-react'
import { cn } from '@/lib/cn'

interface EmptyStateProps {
  icon?: React.ReactNode
  title: string
  message?: string
  children?: React.ReactNode
  className?: string
}

export function EmptyState({ icon, title, message, children, className }: EmptyStateProps) {
  return (
    <div
      className={cn('flex flex-col items-center justify-center gap-3 py-12 text-center', className)}
    >
      {icon ?? <Inbox className="text-faint h-10 w-10" />}
      <div>
        <h3 className="text-text text-base font-medium">{title}</h3>
        {message && <p className="text-muted mt-1 max-w-md text-sm">{message}</p>}
      </div>
      {children}
    </div>
  )
}
