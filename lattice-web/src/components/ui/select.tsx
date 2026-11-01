import * as SelectPrimitive from '@radix-ui/react-select'
import { Check, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/cn'

interface SelectProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  children: React.ReactNode
  className?: string
  label?: string
  error?: string
  disabled?: boolean
}

export function Select({
  value,
  onChange,
  placeholder,
  children,
  className,
  label,
  error,
  disabled,
}: SelectProps) {
  return (
    <div className="flex flex-col gap-1.5">
      {label && <span className="text-text text-sm font-medium">{label}</span>}
      <SelectPrimitive.Root
        value={value || undefined}
        onValueChange={onChange}
        disabled={disabled}
      >
        <SelectPrimitive.Trigger
          className={cn(
            'border-line bg-surface text-text inline-flex h-10 w-full items-center justify-between rounded-md border px-3 text-sm',
            'placeholder:text-faint',
            'cursor-pointer transition-colors duration-150',
            'focus:border-accent focus:ring-accent focus:ring-1 focus:outline-none',
            'disabled:cursor-not-allowed disabled:opacity-50',
            error && 'border-danger',
            className,
          )}
        >
          <SelectPrimitive.Value placeholder={placeholder} />
          <SelectPrimitive.Icon>
            <ChevronDown className="text-muted h-4 w-4" />
          </SelectPrimitive.Icon>
        </SelectPrimitive.Trigger>
        <SelectPrimitive.Portal>
          <SelectPrimitive.Content
            className="border-line bg-surface animate-fade-in z-50 min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-lg border shadow-lg"
            position="popper"
            sideOffset={4}
          >
            <SelectPrimitive.Viewport className="p-1">{children}</SelectPrimitive.Viewport>
          </SelectPrimitive.Content>
        </SelectPrimitive.Portal>
      </SelectPrimitive.Root>
      {error && <p className="text-danger text-xs">{error}</p>}
    </div>
  )
}

interface SelectItemProps extends SelectPrimitive.SelectItemProps {
  className?: string
}

export function SelectItem({ className, children, ...props }: SelectItemProps) {
  return (
    <SelectPrimitive.Item
      className={cn(
        'text-text relative flex cursor-pointer items-center rounded-md px-3 py-2 pr-8 text-sm',
        'transition-colors outline-none',
        'hover:bg-surface-2 focus:bg-surface-2',
        'data-[disabled]:opacity-50',
        className,
      )}
      {...props}
    >
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
      <SelectPrimitive.ItemIndicator className="absolute right-2">
        <Check className="text-accent h-4 w-4" />
      </SelectPrimitive.ItemIndicator>
    </SelectPrimitive.Item>
  )
}
