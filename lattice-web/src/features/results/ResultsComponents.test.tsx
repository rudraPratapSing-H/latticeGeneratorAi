import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import { ResultsBanner } from '@/features/results/ResultsBanner'
import { CandidateCard } from '@/features/results/CandidateCard'
import { ComparisonMatrix } from '@/features/results/ComparisonMatrix'
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

describe('Results Components', () => {
  it('renders ResultsBanner with matched count when solver verifies matches', () => {
    const raw = generateCandidates('job_123', mockRequest, 'success')
    const candidates = raw.map((c, i) => ({ ...c, matches_targets: i === 0 }))

    renderWithProviders(
      <ResultsBanner
        candidates={candidates}
        request={mockRequest}
        reach={{ level: 'covered', distance_pct: 3.2 }}
      />,
    )

    expect(screen.getByText(/solver-verified and meet/i)).toBeInTheDocument()
    expect(screen.getByText(/Strength: solver estimate/i)).toBeInTheDocument()
    expect(screen.getByText(/covered/i)).toBeInTheDocument()
  })

  it('renders ResultsBanner with shortfall breakdown when no candidates match targets', () => {
    const raw = generateCandidates('job_123', mockRequest, 'no_match')
    const candidates = raw.map((c) => ({ ...c, matches_targets: false }))

    renderWithProviders(
      <ResultsBanner
        candidates={candidates}
        request={mockRequest}
        reach={{ level: 'extended', distance_pct: 14.5 }}
      />,
    )

    expect(screen.getByText(/No design met every target/i)).toBeInTheDocument()
    expect(screen.getByText(/Shortfall breakdown for rank #1 candidate/i)).toBeInTheDocument()
    expect(screen.getByText(/Strength: solver estimate/i)).toBeInTheDocument()
  })

  it('renders CandidateCard with Best match ribbon ONLY when matches_targets is true', () => {
    const candidates = generateCandidates('job_123', mockRequest, 'success')
    const matchedCandidate = { ...candidates[0], rank: 1, matches_targets: true }

    renderWithProviders(
      <CandidateCard
        candidate={matchedCandidate}
        jobId="job_123"
        request={mockRequest}
      />,
    )

    expect(screen.getByText('Best match')).toBeInTheDocument()
    expect(screen.queryByText('Closest, not a match')).not.toBeInTheDocument()
    expect(screen.getByText('Within target')).toBeInTheDocument()
  })

  it('renders CandidateCard with Closest, not a match tag when matches_targets is false', () => {
    const candidates = generateCandidates('job_123', mockRequest, 'no_match')
    const nonMatchedCandidate = { ...candidates[0], rank: 1, matches_targets: false }

    renderWithProviders(
      <CandidateCard
        candidate={nonMatchedCandidate}
        jobId="job_123"
        request={mockRequest}
      />,
    )

    expect(screen.queryByText('Best match')).not.toBeInTheDocument()
    expect(screen.getByText('Closest, not a match')).toBeInTheDocument()
  })

  it('renders ComparisonMatrix with candidate rows and verified values', () => {
    const candidates = generateCandidates('job_123', mockRequest, 'success')
    renderWithProviders(
      <ComparisonMatrix
        candidates={candidates}
        request={mockRequest}
        jobId="job_123"
      />,
    )

    expect(screen.getByText('Rank')).toBeInTheDocument()
    expect(screen.getByText('Status')).toBeInTheDocument()
    expect(screen.getByText('Error')).toBeInTheDocument()
    expect(screen.getByText('Mass')).toBeInTheDocument()
    expect(screen.getByText('#1')).toBeInTheDocument()
  })
})
