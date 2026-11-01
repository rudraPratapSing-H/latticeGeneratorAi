import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/cn'

interface SpinnerProps {
  className?: string
  size?: 'sm' | 'md' | 'lg'
}

const sizes = { sm: 'h-4 w-4', md: 'h-6 w-6', lg: 'h-8 w-8' }

export function Spinner({ className, size = 'md' }: SpinnerProps) {
  return <Loader2 className={cn('text-accent animate-spin', sizes[size], className)} />
}
