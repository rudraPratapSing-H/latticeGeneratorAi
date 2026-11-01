import { forwardRef } from 'react'
import type { ButtonHTMLAttributes } from 'react'
import { cva } from 'class-variance-authority'
import type { VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/cn'
import { Loader2 } from 'lucide-react'

const buttonVariants = cva(
  'inline-flex select-none items-center justify-center gap-2 font-medium transition-[background-color,color,border-color,box-shadow,transform,filter] duration-200 ease-out cursor-pointer active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
  {
    variants: {
      variant: {
        primary:
          'bg-accent text-accent-fg shadow-[inset_0_1px_0_rgba(255,255,255,0.28),0_8px_22px_-10px_var(--color-accent)] hover:brightness-110 hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.28),0_10px_28px_-8px_var(--color-accent)] active:brightness-95',
        secondary:
          'bg-surface-2 text-text border border-line hover:border-faint/60 hover:bg-line/60 active:bg-surface-2',
        ghost: 'text-muted hover:bg-surface-2 hover:text-text active:bg-line',
        danger: 'bg-danger text-white hover:brightness-110 active:brightness-95',
        outline: 'border border-line text-text hover:bg-surface-2 active:bg-line',
      },
      size: {
        sm: 'h-8 px-3 text-xs rounded-sm',
        md: 'h-10 px-4 text-sm rounded-md',
        lg: 'h-12 px-6 text-base rounded-lg',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'md',
    },
  },
)

interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  loading?: boolean
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, disabled, children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        disabled={disabled || loading}
        {...props}
      >
        {loading && <Loader2 className="h-4 w-4 animate-spin" />}
        {children}
      </button>
    )
  },
)
Button.displayName = 'Button'

export { Button, buttonVariants }
export type { ButtonProps }
