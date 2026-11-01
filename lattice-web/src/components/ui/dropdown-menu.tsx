import * as DropdownPrimitive from '@radix-ui/react-dropdown-menu'
import { cn } from '@/lib/cn'

export const DropdownMenu = DropdownPrimitive.Root
export const DropdownMenuTrigger = DropdownPrimitive.Trigger

export function DropdownMenuContent({
  className,
  ...props
}: DropdownPrimitive.DropdownMenuContentProps) {
  return (
    <DropdownPrimitive.Portal>
      <DropdownPrimitive.Content
        sideOffset={4}
        className={cn(
          'border-line bg-surface z-50 min-w-[180px] overflow-hidden rounded-lg border p-1 shadow-lg',
          'animate-fade-in',
          className,
        )}
        {...props}
      />
    </DropdownPrimitive.Portal>
  )
}

export function DropdownMenuItem({ className, ...props }: DropdownPrimitive.DropdownMenuItemProps) {
  return (
    <DropdownPrimitive.Item
      className={cn(
        'text-text flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm',
        'transition-colors outline-none',
        'hover:bg-surface-2 focus:bg-surface-2',
        'data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50',
        className,
      )}
      {...props}
    />
  )
}

export const DropdownMenuSeparator = ({
  className,
  ...props
}: DropdownPrimitive.DropdownMenuSeparatorProps) => (
  <DropdownPrimitive.Separator className={cn('bg-line my-1 h-px', className)} {...props} />
)
