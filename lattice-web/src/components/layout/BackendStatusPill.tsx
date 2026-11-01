import { useHealth } from '@/hooks/useHealth'
import { USE_MOCK } from '@/config/env'
import { Tooltip } from '@/components/ui/tooltip'
import { cn } from '@/lib/cn'

export function BackendStatusPill() {
  const { data, isError } = useHealth()

  if (USE_MOCK) {
    return (
      <Tooltip content="Using client-side mock data">
        <span className="border-accent/30 bg-accent-soft text-accent inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium">
          <span className="bg-accent h-1.5 w-1.5 rounded-full" />
          Mock
        </span>
      </Tooltip>
    )
  }

  if (isError) {
    return (
      <Tooltip content="Cannot reach the backend service">
        <span className="border-danger/30 bg-danger-soft text-danger inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium">
          <span className="bg-danger h-1.5 w-1.5 rounded-full" />
          Offline
        </span>
      </Tooltip>
    )
  }

  if (!data) {
    return (
      <span className="border-line bg-surface-2 text-faint inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium">
        <span className="bg-faint animate-pulse-dot h-1.5 w-1.5 rounded-full" />
        Checking…
      </span>
    )
  }

  const isHealthy = data.status === 'ok'
  const isDegraded = !data.model_loaded

  const tooltipText = [
    `Status: ${data.status}`,
    `Model: ${data.model_loaded ? 'loaded' : 'not loaded'}`,
    `Compute: ${data.gpu ? 'GPU' : 'CPU'}`,
  ].join(' · ')

  return (
    <Tooltip content={tooltipText}>
      <span
        className={cn(
          'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium',
          isDegraded
            ? 'border-warning/30 bg-warning-soft text-warning'
            : isHealthy
              ? 'border-success/30 bg-success-soft text-success'
              : 'border-warning/30 bg-warning-soft text-warning',
        )}
      >
        <span
          className={cn(
            'h-1.5 w-1.5 rounded-full',
            isDegraded ? 'bg-warning' : isHealthy ? 'bg-success' : 'bg-warning',
          )}
        />
        {isDegraded ? 'Degraded' : isHealthy ? 'Online' : data.status}
      </span>
    </Tooltip>
  )
}
