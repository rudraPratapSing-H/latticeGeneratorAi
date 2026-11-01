import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import limits from '@/mocks/fixtures/real/limits.json'
import DesignPage from '@/pages/DesignPage'
import { renderWithProviders } from '@/test/utils'

describe('DesignPage', () => {
  it('renders without throwing or exceeding maximum update depth', async () => {
    renderWithProviders(<DesignPage />)
    expect(screen.getByText('Design a lattice')).toBeInTheDocument()
    expect(screen.getByText('Material')).toBeInTheDocument()
    expect(screen.getByText('Stiffness targets')).toBeInTheDocument()
    expect(screen.getByText('Strength targets')).toBeInTheDocument()
    expect(screen.getByText('Weight & part')).toBeInTheDocument()
  })

  it('selects the first material by itself, so the dataset hints can run', async () => {
    renderWithProviders(<DesignPage />)
    await waitFor(() => expect(screen.getAllByText('Ti-6Al-4V').length).toBeGreaterThan(0), { timeout: 3000 })
    expect(screen.queryByText('Choose a material')).not.toBeInTheDocument()
  })

  it('Fill example uses what the dataset holds (median stiffness and strength at density 0.15 from /api/limits)', async () => {
    renderWithProviders(<DesignPage />)
    await waitFor(() => expect(screen.getAllByText('Ti-6Al-4V').length).toBeGreaterThan(0), { timeout: 3000 })
    const row = limits.densities.find((d) => d.rel_density === 0.15)!
    const expected = String(Number(row.stiffness_gpa.median.toPrecision(3)))
    // /api/limits arrives a moment after the material is selected; filling before then uses the built-in example
    await waitFor(
      async () => {
        await userEvent.click(screen.getByRole('button', { name: /fill example/i }))
        expect(screen.getAllByDisplayValue(expected).length).toBeGreaterThan(0)
      },
      { timeout: 5000, interval: 250 },
    )
  })
})
