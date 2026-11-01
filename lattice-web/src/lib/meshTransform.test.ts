import { describe, it, expect } from 'vitest'
import {
  scaleToMm,
  transformPoint,
  transformBoundingBox,
  getTransformedSize,
} from '@/lib/meshTransform'

describe('meshTransform', () => {
  it('scales from meters and inches to millimeters correctly', () => {
    expect(scaleToMm([1, 2, 3], 'mm')).toEqual([1, 2, 3])
    expect(scaleToMm([0.1, 0.2, 0.3], 'm')).toEqual([100, 200, 300])
    const inMm = scaleToMm([1, 2, 3], 'inch')
    expect(inMm[0]).toBeCloseTo(25.4, 4)
    expect(inMm[1]).toBeCloseTo(50.8, 4)
    expect(inMm[2]).toBeCloseTo(76.2, 4)
  })

  it('aligns axis and handles flip correctly', () => {
    // If axis is X, X coordinate moves to Z position
    const p1 = transformPoint([10, 20, 30], { units: 'mm', axis: 'x', flip: false })
    expect(p1[2]).toBe(10) // original X is now Z

    // Flip inverts the aligned Z coordinate
    const p2 = transformPoint([10, 20, 30], { units: 'mm', axis: 'x', flip: true })
    expect(p2[2]).toBe(-10)
  })

  it('transforms bounding boxes preserving extents', () => {
    const bbox = {
      min: [0, 0, 0] as [number, number, number],
      max: [20, 40, 160] as [number, number, number],
    }

    const transformedBox = transformBoundingBox(bbox, { units: 'mm', axis: 'z', flip: false })
    expect(transformedBox.min).toEqual([0, 0, 0])
    expect(transformedBox.max).toEqual([20, 40, 160])

    const size = getTransformedSize(bbox, { units: 'mm', axis: 'z', flip: false })
    expect(size).toEqual([20, 40, 160])

    const inchSize = getTransformedSize(
      { min: [0, 0, 0], max: [1, 2, 4] },
      { units: 'inch', axis: 'z', flip: false },
    )
    expect(inchSize[0]).toBeCloseTo(25.4, 2)
    expect(inchSize[1]).toBeCloseTo(50.8, 2)
    expect(inchSize[2]).toBeCloseTo(101.6, 2)
  })
})
