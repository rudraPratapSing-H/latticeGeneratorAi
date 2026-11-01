import { AlertCircle, AlertTriangle, Info } from 'lucide-react'
import { cn } from '@/lib/cn'

type AlertVariant = 'info' | 'warning' | 'error'

interface InlineAlertProps {
  variant: AlertVariant
  children: React.ReactNode
  className?: string
}

const config: Record<AlertVariant, { icon: React.ReactNode; classes: string }> = {
  info: {
    icon: <Info className="text-info h-4 w-4 shrink-0" />,
    classes: 'border-info/30 bg-info-soft text-info',
  },
  warning: {
    icon: <AlertTriangle className="text-warning h-4 w-4 shrink-0" />,
    classes: 'border-warning/30 bg-warning-soft text-warning',
  },
  error: {
    icon: <AlertCircle className="text-danger h-4 w-4 shrink-0" />,
    classes: 'border-danger/30 bg-danger-soft text-danger',
  },
}

export function InlineAlert({ variant, children, className }: InlineAlertProps) {
  const { icon, classes } = config[variant]

  return (
    <div
      className={cn(
        'flex items-start gap-2.5 rounded-lg border px-4 py-3 text-sm',
        classes,
        className,
      )}
      role="alert"
    >
      {icon}
      <div>{children}</div>
    </div>
  )
}
