import { cn } from '@/lib/cn'

interface PageHeaderProps {
  title: string
  description?: string
  children?: React.ReactNode
  className?: string
}

export function PageHeader({ title, description, children, className }: PageHeaderProps) {
  return (
    <div className={cn('relative pb-4', className)}>
      <div className="relative flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-text text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
          {description && <p className="text-muted mt-1 text-sm">{description}</p>}
        </div>
        {children && <div className="mt-3 flex items-center gap-2 sm:mt-0">{children}</div>}
      </div>
    </div>
  )
}
