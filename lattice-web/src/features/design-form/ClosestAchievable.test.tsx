import { describe, it, expect, vi } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import { ClosestAchievable } from './ClosestAchievable'
import type { ReachResponse } from '@/api/types'

describe('ClosestAchievable', () => {
  const baseReach: ReachResponse = {
    level: 'covered',
    distance_pct: 0,
    density: 0.15,
    requested: {
      stiffness_gpa: [2.0, null, null],
      strength_mpa: null,
    },
    nearest: {
      stiffness_gpa: [1.8, 1.8, 1.8],
      strength_mpa: [25.0, 25.0, 25.0],
      lattice_id: 42,
    },
    bounds: {
      stiffness_sum_max_gpa: 15.0,
      strength_max_mpa: 100.0,
    },
    message: 'Within range of stored lattices.',
  }

  it('renders without error when requested.strength_mpa is null', () => {
    const onAccept = vi.fn()
    const onUndo = vi.fn()

    renderWithProviders(
      <ClosestAchievable
        reach={baseReach}
        isAdjusted={false}
        onAccept={onAccept}
        onUndo={onUndo}
      />,
    )

    expect(screen.getByText('Nearest achievable target')).toBeInTheDocument()
    expect(screen.getByText('Stiffness (GPa):')).toBeInTheDocument()
    expect(screen.queryByText('Strength (MPa):')).not.toBeInTheDocument()
    expect(screen.getByText('Accept nearest')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Accept nearest'))
    expect(onAccept).toHaveBeenCalledWith(baseReach.nearest)
  })

  it('renders without error when requested.stiffness_gpa is null', () => {
    const reach: ReachResponse = {
      ...baseReach,
      requested: {
        stiffness_gpa: null,
        strength_mpa: [50.0, null, null],
      },
    }

    renderWithProviders(
      <ClosestAchievable
        reach={reach}
        isAdjusted={false}
        onAccept={vi.fn()}
        onUndo={vi.fn()}
      />,
    )

    expect(screen.getByText('Nearest achievable target')).toBeInTheDocument()
    expect(screen.queryByText('Stiffness (GPa):')).not.toBeInTheDocument()
    expect(screen.getByText('Strength (MPa):')).toBeInTheDocument()
  })

  it('renders both sections when both stiffness and strength are requested', () => {
    const reach: ReachResponse = {
      ...baseReach,
      requested: {
        stiffness_gpa: [2.0, null, null],
        strength_mpa: [50.0, null, null],
      },
    }

    renderWithProviders(
      <ClosestAchievable
        reach={reach}
        isAdjusted={false}
        onAccept={vi.fn()}
        onUndo={vi.fn()}
      />,
    )

    expect(screen.getByText('Stiffness (GPa):')).toBeInTheDocument()
    expect(screen.getByText('Strength (MPa):')).toBeInTheDocument()
  })

  it('returns null when there are no differences and not infeasible', () => {
    const reach: ReachResponse = {
      ...baseReach,
      requested: {
        stiffness_gpa: [1.8, null, null],
        strength_mpa: null,
      },
      nearest: {
        stiffness_gpa: [1.8, 1.8, 1.8],
        strength_mpa: [25.0, 25.0, 25.0],
        lattice_id: 42,
      },
    }

    const { container } = renderWithProviders(
      <ClosestAchievable
        reach={reach}
        isAdjusted={false}
        onAccept={vi.fn()}
        onUndo={vi.fn()}
      />,
    )

    expect(container.firstChild).toBeNull()
  })

  it('renders physical bound constraint when level is infeasible', () => {
    const reach: ReachResponse = {
      ...baseReach,
      level: 'infeasible',
      requested: {
        stiffness_gpa: [2.0, null, null],
        strength_mpa: null,
      },
    }

    renderWithProviders(
      <ClosestAchievable
        reach={reach}
        isAdjusted={false}
        onAccept={vi.fn()}
        onUndo={vi.fn()}
      />,
    )

    expect(screen.getByText('Physical bound constraint:')).toBeInTheDocument()
  })

  it('renders undo button when isAdjusted is true and triggers onUndo', () => {
    const onUndo = vi.fn()

    renderWithProviders(
      <ClosestAchievable
        reach={baseReach}
        isAdjusted={true}
        onAccept={vi.fn()}
        onUndo={onUndo}
      />,
    )

    expect(screen.getByText('Undo adjustments')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Undo adjustments'))
    expect(onUndo).toHaveBeenCalledTimes(1)
  })
})

