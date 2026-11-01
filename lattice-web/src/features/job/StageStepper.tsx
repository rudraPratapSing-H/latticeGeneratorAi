import { Check } from 'lucide-react'
import type { JobStage } from '@/api/types'
import { STAGES, STAGE_LABELS, STAGE_DESCRIPTIONS } from '@/config/constants'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/cn'

interface StageStepperProps {
  currentStage: JobStage | null
  status: 'queued' | 'running' | 'done' | 'failed'
}

function getStepState(
  step: JobStage,
  currentStage: JobStage | null,
  status: string,
): 'pending' | 'active' | 'done' {
  if (status === 'done') return 'done'
  if (status === 'queued' || !currentStage) return 'pending'

  const currentIdx = STAGES.indexOf(currentStage)
  const stepIdx = STAGES.indexOf(step)

  if (stepIdx < currentIdx) return 'done'
  if (stepIdx === currentIdx) return 'active'
  return 'pending'
}

export function StageStepper({ currentStage, status }: StageStepperProps) {
  return (
    <div className="flex flex-col gap-2 md:flex-row md:gap-0">
      {STAGES.map((stage, i) => {
        const state = getStepState(stage, currentStage, status)

        return (
          <div
            key={stage}
            className="flex flex-1 items-start gap-3 md:flex-col md:items-center md:text-center"
          >
            <div className="flex items-center gap-2 md:w-full">
              <div
                className={cn(
                  'hidden h-px flex-1 transition-colors duration-700 md:block',
                  i === 0 ? 'bg-transparent' : state === 'pending' ? 'bg-line' : 'bg-accent',
                )}
              />
              <div
                className={cn(
                  'flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 font-mono text-xs font-semibold transition-all duration-500',
                  state === 'done' && 'bg-accent border-accent text-accent-fg',
                  state === 'active' && 'border-accent bg-accent-soft text-accent animate-ring-pulse',
                  state === 'pending' && 'border-line text-faint',
                )}
              >
                {state === 'done' ? <Check className="h-4 w-4" /> : i + 1}
              </div>
              <div
                className={cn(
                  'hidden h-px flex-1 transition-colors duration-700 md:block',
                  i === STAGES.length - 1 ? 'bg-transparent' : state === 'done' ? 'bg-accent' : 'bg-line',
                )}
              />
            </div>
            <div className="md:mt-2">
              <div className="flex items-center gap-1.5">
                <span
                  className={cn(
                    'text-sm font-medium',
                    state === 'active'
                      ? 'text-accent'
                      : state === 'done'
                        ? 'text-text'
                        : 'text-muted',
                  )}
                >
                  {STAGE_LABELS[stage]}
                </span>
                {stage === 'verify' && (
                  <Badge variant="accent" className="text-[10px]">
                    Solver-verified
                  </Badge>
                )}
              </div>
              <p className="text-muted mt-0.5 text-xs">{STAGE_DESCRIPTIONS[stage]}</p>
            </div>
          </div>
        )
      })}
    </div>
  )
}
