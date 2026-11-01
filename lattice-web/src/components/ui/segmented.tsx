import { cn } from '@/lib/cn'

interface SegmentedProps<T extends string> {
  value: T
  onChange: (value: T) => void
  options: Array<{ value: T; label: string }>
  className?: string
}

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  className,
}: SegmentedProps<T>) {
  return (
    <div
      className={cn('border-line bg-surface-2 inline-flex rounded-lg border p-0.5', className)}
      role="radiogroup"
    >
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          role="radio"
          aria-checked={value === opt.value}
          onClick={() => onChange(opt.value)}
          className={cn(
            'cursor-pointer whitespace-nowrap rounded-md px-3 py-1.5 text-xs font-medium transition-[background-color,color,box-shadow] duration-200',
            value === opt.value ? 'bg-surface text-text shadow-sm ring-1 ring-line' : 'text-muted hover:text-text',
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}
