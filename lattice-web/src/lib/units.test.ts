import { describe, it, expect } from 'vitest'
import {
  partVolumeCm3,
  solidMassG,
  relDensityFromMass,
  voigtBound,
  tilesPerAxis,
  isIntegerMultiple,
} from '@/lib/units'

describe('partVolumeCm3', () => {
  it('converts mm to cm³', () => {
    expect(partVolumeCm3([40, 40, 40])).toBeCloseTo(64, 1)
  })

  it('handles rectangular shapes', () => {
    expect(partVolumeCm3([20, 30, 40])).toBeCloseTo(24, 1)
  })
})

describe('solidMassG', () => {
  it('calculates mass from volume and density', () => {
    expect(solidMassG(64, 4.43)).toBeCloseTo(283.52, 1)
  })
})

describe('relDensityFromMass', () => {
  it('returns fraction of solid mass', () => {
    expect(relDensityFromMass(60, 280)).toBeCloseTo(0.214, 2)
  })
})

describe('voigtBound', () => {
  it('calculates upper bound stiffness', () => {
    const bound = voigtBound(0.12, 114)
    expect(bound).toBeCloseTo(13.68, 1)
  })
})

describe('tilesPerAxis', () => {
  it('returns floor of size/cell', () => {
    expect(tilesPerAxis(40, 10)).toBe(4)
    expect(tilesPerAxis(45, 10)).toBe(4)
  })

  it('returns 0 when size is smaller than cell', () => {
    expect(tilesPerAxis(5, 10)).toBe(0)
  })
})

describe('isIntegerMultiple', () => {
  it('returns true for exact multiples', () => {
    expect(isIntegerMultiple(40, 10)).toBe(true)
  })

  it('returns false for non-multiples', () => {
    expect(isIntegerMultiple(45, 10)).toBe(false)
  })
})
