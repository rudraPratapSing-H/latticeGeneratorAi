import { createRoot } from 'react-dom/client'
import { useState } from 'react'
import { ALL_SCENARIOS, SCENARIO_LABELS } from '@/mocks/scenarios'
import type { MockScenario } from '@/mocks/scenarios'
import { getMockScenario, setMockScenario, clearMockData } from '@/lib/storage'
import { cn } from '@/lib/cn'

function MockControls() {
  const [open, setOpen] = useState(false)
  const [scenario, setScenarioState] = useState<MockScenario>(getMockScenario() as MockScenario)

  const handleChange = (s: MockScenario) => {
    setMockScenario(s)
    setScenarioState(s)
  }

  return (
    <div className="fixed right-4 bottom-4 z-[9999]">
      {open ? (
        <div className="bg-surface border-line animate-fade-in w-64 rounded-xl border p-4 shadow-lg">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-text text-sm font-semibold">Mock Controls</h3>
            <button
              onClick={() => setOpen(false)}
              className="text-muted hover:text-text cursor-pointer text-xs"
            >
              Close
            </button>
          </div>
          <div className="space-y-1.5">
            {ALL_SCENARIOS.map((s) => (
              <button
                key={s}
                onClick={() => handleChange(s)}
                className={cn(
                  'w-full cursor-pointer rounded-md px-3 py-1.5 text-left text-xs transition-colors',
                  scenario === s
                    ? 'bg-accent-soft text-accent font-medium'
                    : 'text-muted hover:bg-surface-2 hover:text-text',
                )}
              >
                {SCENARIO_LABELS[s]}
              </button>
            ))}
          </div>
          <button
            onClick={() => {
              clearMockData()
              window.location.reload()
            }}
            className="border-line text-muted hover:text-text mt-3 w-full cursor-pointer rounded-md border px-3 py-1.5 text-xs"
          >
            Clear mock data & reload
          </button>
        </div>
      ) : (
        <button
          onClick={() => setOpen(true)}
          className="bg-accent text-accent-fg cursor-pointer rounded-full px-3 py-1.5 text-xs font-medium shadow-lg hover:brightness-110"
        >
          Mock
        </button>
      )}
    </div>
  )
}

export function mountMockControls() {
  if (typeof document === 'undefined') return
  if (document.getElementById('mock-controls')) return
  const container = document.createElement('div')
  container.id = 'mock-controls'
  document.body.appendChild(container)
  createRoot(container).render(<MockControls />)
}
