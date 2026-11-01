import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import { StageStepper } from '@/features/job/StageStepper'
import { RoundsTimeline } from '@/features/job/RoundsTimeline'
import { TargetChips } from '@/features/job/TargetChips'
import type { DesignRequest, RoundInfo } from '@/api/types'

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

describe('Job Page Components', () => {
  it('renders StageStepper with Search, Repair, Verify with Solver-verified badge, and Rank', () => {
    renderWithProviders(
      <StageStepper currentStage="verify" status="running" />,
    )

    expect(screen.getByText('Search')).toBeInTheDocument()
    expect(screen.getByText('Repair')).toBeInTheDocument()
    expect(screen.getByText('Verify')).toBeInTheDocument()
    expect(screen.getByText('Rank')).toBeInTheDocument()
    expect(screen.getByText('Solver-verified')).toBeInTheDocument()
  })

  it('renders RoundsTimeline table with rounds, K, best error %, matched status', () => {
    const rounds: RoundInfo[] = [
      {
        round: 1,
        k: 100,
        best_error_pct: 11.8,
        matched: false,
        n_candidates: 240,
        round_seconds: 10.1,
        elapsed_seconds: 10.1,
      },
      {
        round: 2,
        k: 300,
        best_error_pct: 3.2,
        matched: true,
        n_candidates: 720,
        round_seconds: 22.4,
        elapsed_seconds: 32.5,
      },
    ]

    renderWithProviders(<RoundsTimeline rounds={rounds} />)

    expect(screen.getByText('Search Rounds')).toBeInTheDocument()
    expect(screen.getByText('Round 1')).toBeInTheDocument()
    expect(screen.getByText('Round 2')).toBeInTheDocument()
    expect(screen.getByText('11.8%')).toBeInTheDocument()
    expect(screen.getByText('3.2%')).toBeInTheDocument()
    expect(screen.getByText('K = 100')).toBeInTheDocument()
    expect(screen.getByText('K = 300')).toBeInTheDocument()
  })

  it('renders TargetChips with appropriate SourceTags', () => {
    renderWithProviders(
      <TargetChips
        request={{
          ...mockRequest,
          _metadata: { adjustedFields: ['stiffnessZ'] },
        }}
      />,
    )

    expect(screen.getByText(/Stiffness X 8 GPa/i)).toBeInTheDocument()
    expect(screen.getByText(/Stiffness Z 12 GPa/i)).toBeInTheDocument()
    expect(screen.getByText('Adjusted')).toBeInTheDocument()
    expect(screen.getAllByText('Requested').length).toBeGreaterThan(0)
  })
})
