import { useEffect, useState } from 'react'
import type { JobEvent, JobStage } from '@/api/types'
import { openJobEvents } from '@/api/events'

interface EventState {
  stage: JobStage | null
  progress: number
  messages: Array<{ message: string; timestamp: number }>
}

export function useJobEvents(jobId: string, enabled: boolean) {
  const [state, setState] = useState<EventState>({
    stage: null,
    progress: 0,
    messages: [],
  })

  useEffect(() => {
    if (!enabled) return

    const unsubscribe = openJobEvents(jobId, {
      onEvent: (event: JobEvent) => {
        setState((prev) => {
          // Only add distinct messages (capped at 50)
          const lastMsg = prev.messages[prev.messages.length - 1]
          const newMessages =
            lastMsg?.message === event.message
              ? prev.messages
              : [...prev.messages, { message: event.message, timestamp: Date.now() }].slice(-50)

          return {
            stage: event.stage ?? prev.stage,
            progress: Math.max(prev.progress, event.progress), // Monotonic
            messages: newMessages,
          }
        })
      },
      onError: () => {
        // Silently rely on polling
      },
    })

    return unsubscribe
  }, [jobId, enabled])

  return state
}
