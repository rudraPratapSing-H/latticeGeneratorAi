import { describe, it, expect } from 'vitest'
import {
  fmtGpa,
  fmtMpa,
  fmtMass,
  fmtPct,
  fmtRelDensity,
  fmtMm,
  fmtDuration,
  fmtTime,
} from '@/lib/format'

describe('fmtGpa', () => {
  it('formats with one decimal', () => {
    expect(fmtGpa(8.123)).toBe('8.1 GPa')
  })
})

describe('fmtMpa', () => {
  it('formats with zero decimals', () => {
    expect(fmtMpa(120.7)).toBe('121 MPa')
  })
})

describe('fmtMass', () => {
  it('formats with one decimal and unit', () => {
    expect(fmtMass(45.67)).toBe('45.7 g')
  })
})

describe('fmtPct', () => {
  it('formats with one decimal and percent sign', () => {
    expect(fmtPct(5.45)).toBe('5.5%')
  })
})

describe('fmtRelDensity', () => {
  it('formats as percentage', () => {
    expect(fmtRelDensity(0.12)).toBe('12.0%')
  })
})

describe('fmtMm', () => {
  it('formats with two decimals', () => {
    expect(fmtMm(0.35)).toBe('0.35 mm')
  })
})

describe('fmtDuration', () => {
  it('formats seconds only', () => {
    expect(fmtDuration(45)).toBe('45s')
  })

  it('formats minutes and seconds', () => {
    expect(fmtDuration(125)).toBe('2m 5s')
  })
})

describe('fmtTime', () => {
  it('returns a time string', () => {
    const result = fmtTime(Date.now())
    expect(result).toMatch(/\d{1,2}:\d{2}(:\d{2})?/)
  })
})
