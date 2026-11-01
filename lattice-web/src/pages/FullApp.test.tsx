import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import { AppShell } from '@/components/layout/AppShell'
import DesignPage from '@/pages/DesignPage'

describe('Full App render', () => {
  it('renders AppShell with Header, PageHeader, DesignPage, and Footer without infinite re-renders', () => {
    renderWithProviders(
      <AppShell>
        <DesignPage />
      </AppShell>,
    )

    expect(screen.getByText('Lattice Designer')).toBeInTheDocument()
    expect(screen.getByText('Design a lattice')).toBeInTheDocument()
    expect(screen.getByText('Material')).toBeInTheDocument()
    expect(screen.getAllByText('Summary')[0]).toBeInTheDocument()
  })
})
