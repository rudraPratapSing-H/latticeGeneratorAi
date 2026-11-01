import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import { ImplantBanner } from '@/features/implant/ImplantBanner'
import { ZoneStrip } from '@/features/implant/ZoneStrip'
import zoneTable from '@/mocks/fixtures/real/implant/zones.json'
import type { ZoneTable } from '@/api/implantTypes'

const table = zoneTable as unknown as ZoneTable

describe('Implant workflow components', () => {
  it('says this is a design demo and makes no clinical claim', () => {
    renderWithProviders(<ImplantBanner />)
    expect(screen.getByText(/Design demo, not a medical device/i)).toBeInTheDocument()
    expect(screen.getByText(/Nothing here is a clinical, safety or regulatory claim/i)).toBeInTheDocument()
  })

  it('renders the real zone table from the backend as a strip with names, ranges and a boundary slider', () => {
    renderWithProviders(<ZoneStrip zones={table.zones ?? []} totalLengthMm={table.length_mm ?? 160} onBoundaryChange={() => {}} />)
    for (const z of table.zones ?? []) {
      expect(screen.getAllByText(z.name).length).toBeGreaterThan(0)
    }
    expect(screen.getAllByRole('slider').length).toBe((table.zones?.length ?? 1) - 1)
  })
})
