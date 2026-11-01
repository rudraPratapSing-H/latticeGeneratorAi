import { forwardRef } from 'react'
import type { InputHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  hint?: string
  error?: string
  suffix?: string
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, hint, error, suffix, id, ...props }, ref) => {
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
            className={cn(
              'border-line bg-surface text-text h-10 w-full rounded-md border px-3 text-sm',
              'placeholder:text-faint',
              'transition-[border-color,box-shadow] duration-200',
              'hover:border-faint/60 focus:border-accent focus:ring-accent/40 focus:ring-4 focus:outline-none',
              'disabled:cursor-not-allowed disabled:opacity-50',
              suffix && 'pr-12',
              error && 'border-danger focus:border-danger focus:ring-danger',
              className,
            )}
            {...props}
          />
          {suffix && (
            <span className="text-faint pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 font-mono text-xs">
              {suffix}
            </span>
          )}
        </div>
        {hint && !error && <p className="text-muted text-xs">{hint}</p>}
        {error && <p className="text-danger text-xs">{error}</p>}
      </div>
    )
  },
)
Input.displayName = 'Input'

export { Input }
export type { InputProps }
