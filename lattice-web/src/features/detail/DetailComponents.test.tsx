import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import { PropertyTable } from '@/features/detail/PropertyTable'
import { PrintabilityNotice } from '@/features/detail/PrintabilityNotice'
import { MetricGrid } from '@/features/detail/MetricGrid'
import LatticeViewer from '@/components/LatticeViewer/LatticeViewer'
import { generateCandidates } from '@/mocks/generate'
import type { DesignRequest } from '@/api/types'

const mockRequest: DesignRequest = {
  material: 'ti64',
  part: { size_mm: [40, 40, 40], cell_mm: 10 },
  target: {
    stiffness_gpa: { x: 8.0, y: 8.0, z: 12.0 },
    strength_mpa: { x: 90, y: 90, z: null },
    max_mass_g: 60,
  },
  modes: { stiffness: 'about', strength: 'at_least', weight: 'at_most' },
  tolerance_pct: 10,
  n_results: 5,
}

describe('Detail Components', () => {
  it('renders PropertyTable with surrogate accuracy and verified governing failure', () => {
    const candidates = generateCandidates('job_123', mockRequest, 'success')
    const candidate = candidates[0]

    renderWithProviders(
      <PropertyTable
        candidate={candidate}
        request={mockRequest}
        tolerance={10}
      />,
    )

    expect(screen.getByText('Properties & Solver Verification')).toBeInTheDocument()
    expect(screen.getByText(/Surrogate Accuracy:/i)).toBeInTheDocument()
    expect(screen.getByText(/Median error:/i)).toBeInTheDocument()
    expect(screen.getByText(/Max error:/i)).toBeInTheDocument()

    // Governing failure is shown on verified properties
    expect(
      screen.getAllByText(/Governs: (yield|buckling)/i).length,
    ).toBeGreaterThan(0)
    expect(
      screen.getAllByText(/Verified only \(no failure mode on prediction\)/i).length,
    ).toBeGreaterThan(0)
  })

  it('renders PrintabilityNotice correctly for passing and failing nozzle diameters', () => {
    // 0.3mm radius in 10mm cell -> 0.6mm diameter >= 0.4mm (passes)
    const { unmount } = renderWithProviders(
      <PrintabilityNotice strutRadiusMm={0.3} cellSizeMm={10} />,
    )
    expect(
      screen.getByText(/Strut diameter OK for a 0.4 mm nozzle/i),
    ).toBeInTheDocument()
    unmount()

    // 0.1mm radius in 10mm cell -> 0.2mm diameter < 0.4mm (fails nozzle check)
    renderWithProviders(
      <PrintabilityNotice strutRadiusMm={0.1} cellSizeMm={10} />,
    )
    expect(
      screen.getByText(/Strut diameter 0.200 mm is below 0.4 mm/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/Use a cell size ≥/i)).toBeInTheDocument()
  })

  it('renders MetricGrid with mass labeled Estimate and node/edge count', () => {
    const candidates = generateCandidates('job_123', mockRequest, 'success')
    const candidate = candidates[0]

    renderWithProviders(
      <MetricGrid
        candidate={candidate}
        isThinStrut={false}
        strutDiameter={candidate.lattice.strut_radius_mm * 2}
      />,
    )

    expect(screen.getByText('Relative density')).toBeInTheDocument()
    expect(screen.getByText('Mass')).toBeInTheDocument()
    expect(screen.getByText('Estimate')).toBeInTheDocument()
    expect(screen.getByText('Nodes / Edges')).toBeInTheDocument()
  })

  it('renders LatticeViewer stub placeholder with SVG wireframe without loading Three.js', () => {
    const candidates = generateCandidates('job_123', mockRequest, 'success')
    const candidate = candidates[0]

    renderWithProviders(
      <LatticeViewer
        lattice={candidate.lattice}
        variant="thumbnail"
      />,
    )

    expect(screen.getByLabelText('Lattice wireframe preview')).toBeInTheDocument()
    expect(screen.queryByText(/Placeholder preview/i)).not.toBeInTheDocument()
  })
})
