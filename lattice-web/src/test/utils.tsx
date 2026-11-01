import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { render } from '@testing-library/react'
import type { RenderOptions } from '@testing-library/react'
import { TooltipProvider } from '@/components/ui/tooltip'

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })
}

interface WrapperOptions {
  initialEntries?: string[]
}

export function renderWithProviders(
  ui: React.ReactElement,
  options?: RenderOptions & WrapperOptions,
) {
  const queryClient = createTestQueryClient()
  const { initialEntries = ['/'], ...renderOptions } = options ?? {}

  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
        </TooltipProvider>
      </QueryClientProvider>
    )
  }

  return { ...render(ui, { wrapper: Wrapper, ...renderOptions }), queryClient }
}
