import { describe, it, expect } from 'vitest'
import { buildRequest } from '@/features/design-form/buildRequest'
import { EXAMPLE_VALUES } from '@/features/design-form/defaults'

describe('buildRequest', () => {
  it('builds correct request from example values', () => {
    const req = buildRequest(EXAMPLE_VALUES)

    expect(req.material).toBe('ti64')
    expect(req.part.size_mm).toEqual([40, 40, 40])
    expect(req.part.cell_mm).toBe(10)
    expect(req.target.stiffness_gpa).toEqual({ x: 8, y: 8, z: 12 })
    expect(req.n_results).toBe(5)
    expect(req.tolerance_pct).toBe(10)
    expect(req.modes.stiffness).toBe('about')
    expect(req.modes.strength).toBe('at_least')
  })

  it('applies "same in all directions" for stiffness', () => {
    const values = { ...EXAMPLE_VALUES, stiffnessSameAll: true, stiffnessX: '5' }
    const req = buildRequest(values)

    expect(req.target.stiffness_gpa.x).toBe(5)
    expect(req.target.stiffness_gpa.y).toBe(5)
    expect(req.target.stiffness_gpa.z).toBe(5)
  })

  it('uses rel_density when useRelDensity is true', () => {
    const values = { ...EXAMPLE_VALUES, useRelDensity: true, relDensity: '0.15' }
    const req = buildRequest(values)

    expect('rel_density' in req.target).toBe(true)
    expect('max_mass_g' in req.target).toBe(false)
  })

  it('uses max_mass_g when useRelDensity is false', () => {
    const values = { ...EXAMPLE_VALUES, useRelDensity: false, maxMassG: '60' }
    const req = buildRequest(values)

    expect('max_mass_g' in req.target).toBe(true)
    expect('rel_density' in req.target).toBe(false)
  })

  it('uses yield_strength_mpa when strengthType is yield_only', () => {
    const values = { ...EXAMPLE_VALUES, strengthType: 'yield_only' as const }
    const req = buildRequest(values)

    expect('yield_strength_mpa' in req.target).toBe(true)
    expect('strength_mpa' in req.target).toBe(false)
  })

  it('sets axis to null when dont care is checked', () => {
    const values = {
      ...EXAMPLE_VALUES,
      stiffnessDontCareZ: true,
    }
    const req = buildRequest(values)

    expect(req.target.stiffness_gpa.z).toBeNull()
  })
})
