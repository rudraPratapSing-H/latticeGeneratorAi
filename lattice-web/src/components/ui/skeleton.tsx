import { cn } from '@/lib/cn'

export type SkeletonProps = React.HTMLAttributes<HTMLDivElement>

export function Skeleton({ className, ...props }: SkeletonProps) {
  return <div className={cn('animate-shimmer rounded-md', className)} {...props} />
}
