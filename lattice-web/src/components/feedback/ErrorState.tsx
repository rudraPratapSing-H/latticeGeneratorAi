import { AlertTriangle, RefreshCw, WifiOff, FileQuestion } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/cn'
import type { ApiError } from '@/api/client'

interface ErrorStateProps {
  error?: ApiError | Error | null
  title?: string
  message?: string
  onRetry?: () => void
  onBack?: () => void
  backLabel?: string
  className?: string
}

const ERROR_ICONS: Record<string, React.ReactNode> = {
  network_error: <WifiOff className="text-danger h-10 w-10" />,
  not_found: <FileQuestion className="text-warning h-10 w-10" />,
}

export function ErrorState({
  error,
  title,
  message,
  onRetry,
  onBack,
  backLabel = 'Back to form',
  className,
}: ErrorStateProps) {
  const code = error && 'code' in error ? (error as ApiError).code : 'unknown'
  const icon = ERROR_ICONS[code] ?? <AlertTriangle className="text-danger h-10 w-10" />

  const displayTitle =
    title ?? (code === 'network_error' ? 'Connection lost' : 'Something went wrong')
  const displayMessage =
    message ?? error?.message ?? 'An unexpected error occurred. Please try again.'

  return (
    <div
      className={cn('flex flex-col items-center justify-center gap-4 py-12 text-center', className)}
    >
      {icon}
      <div>
        <h3 className="text-text text-lg font-semibold">{displayTitle}</h3>
        <p className="text-muted mt-1 max-w-md text-sm">{displayMessage}</p>
      </div>
      <div className="flex gap-3">
        {onRetry && (
          <Button variant="secondary" size="sm" onClick={onRetry}>
            <RefreshCw className="h-4 w-4" />
            Retry
          </Button>
        )}
        {onBack && (
          <Button variant="ghost" size="sm" onClick={onBack}>
            {backLabel}
          </Button>
        )}
      </div>
    </div>
  )
}
