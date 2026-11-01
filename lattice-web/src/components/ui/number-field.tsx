import { forwardRef } from 'react'
import type { InputHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

interface NumberFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: string
  hint?: string
  error?: string
  warning?: string
  unit?: string
}

const NumberField = forwardRef<HTMLInputElement, NumberFieldProps>(
  ({ className, label, hint, error, warning, unit, id, ...props }, ref) => {
    const inputId = id ?? label?.toLowerCase().replace(/\s+/g, '-')

    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label htmlFor={inputId} className="text-text text-sm font-medium">
            {label}
          </label>
        )}
        <div className="relative">
          <input
            ref={ref}
            id={inputId}
            type="text"
            inputMode="decimal"
            className={cn(
              'border-line bg-surface text-text h-10 w-full rounded-md border px-3 font-mono text-sm tabular-nums',
              'placeholder:text-faint',
              'transition-colors duration-150',
              'focus:border-accent focus:ring-accent focus:ring-1 focus:outline-none',
              'disabled:cursor-not-allowed disabled:opacity-50',
              unit && 'pr-14',
              error && 'border-danger focus:border-danger focus:ring-danger',
              warning && !error && 'border-warning focus:border-warning focus:ring-warning',
              className,
            )}
            {...props}
          />
          {unit && (
            <span className="text-faint pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 font-mono text-xs">
              {unit}
            </span>
          )}
        </div>
        {warning && !error && <p className="text-warning text-xs">{warning}</p>}
        {hint && !error && !warning && <p className="text-muted text-xs">{hint}</p>}
        {error && <p className="text-danger text-xs">{error}</p>}
      </div>
    )
  },
)
NumberField.displayName = 'NumberField'

export { NumberField }
export type { NumberFieldProps }
