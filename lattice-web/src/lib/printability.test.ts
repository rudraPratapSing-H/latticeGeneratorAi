import { describe, it, expect } from 'vitest'
import { checkPrintability } from '@/lib/printability'

describe('checkPrintability', () => {
  it('passes worked example: radius 0.29672 mm, cell 10 mm (diameter 0.593 mm >= 0.4 mm)', () => {
    const res = checkPrintability(0.29672, 10)
    expect(res.passes).toBe(true)
    expect(res.strutDiameterMm).toBeCloseTo(0.59344, 4)
    expect(res.message).toContain('OK for a 0.4 mm nozzle')
  })

  it('fails worked example: radius 0.14836 mm (equivalent to 5mm cell scaled), cell 5 mm (diameter ~0.297 mm < 0.4 mm)', () => {
    // If radius in a 5 mm cell is 0.14836 (so diameter is 0.29672 mm)
    const res = checkPrintability(0.14836, 5)
    expect(res.passes).toBe(false)
    expect(res.strutDiameterMm).toBeCloseTo(0.29672, 4)
    // minCellMm = 0.4 * 5 / (2 * 0.14836) ≈ 6.74 mm -> rounded to 6.7 mm
    expect(res.minCellMm).toBe(6.7)
    expect(res.message).toContain('Use a cell size ≥ 6.7 mm')
  })

  it('passes right at boundary 0.4 mm diameter', () => {
    const res = checkPrintability(0.2, 10)
    expect(res.passes).toBe(true)
    expect(res.strutDiameterMm).toBe(0.4)
  })

  it('fails below 0.4 mm diameter and computes required cell size', () => {
    const res = checkPrintability(0.19, 10)
    expect(res.passes).toBe(false)
    // 0.4 * 10 / (2 * 0.19) = 4 / 0.38 ≈ 10.5 mm
    expect(res.minCellMm).toBe(10.5)
  })
})

