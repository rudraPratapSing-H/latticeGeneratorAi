import { MIN_PRINT_DIAMETER_MM } from '@/config/constants'

export interface PrintabilityResult {
  passes: boolean
  strutDiameterMm: number
  minCellMm?: number
  message: string
}

/**
 * Check whether a strut diameter is above the minimum printable threshold.
 * Pure function, unit-tested.
 *
 * If the diameter is too thin, computes the smallest cell size that passes:
 *   minCellMm = MIN_PRINT_DIAMETER_MM / (2 × strut_radius_mm / cell_size_mm)
 *             = MIN_PRINT_DIAMETER_MM × cell_size_mm / (2 × strut_radius_mm)
 *
 * Example: radius 0.29672 mm, cell 10 mm → diameter 0.593 mm → passes.
 * At cell 5 mm: diameter = 2 × 0.29672 × 5/10 = 0.297 mm → fails, minCell ≈ 6.7 mm.
 */
export function checkPrintability(
  strutRadiusMm: number,
  cellSizeMm: number,
): PrintabilityResult {
  const strutDiameterMm = strutRadiusMm * 2

  if (strutDiameterMm >= MIN_PRINT_DIAMETER_MM) {
    return {
      passes: true,
      strutDiameterMm,
      message: `Strut diameter OK for a ${MIN_PRINT_DIAMETER_MM} mm nozzle.`,
    }
  }

  // Strut diameter is below minimum — compute the minimum cell size that would pass
  // The strut radius scales with cell size: radius_at_new_cell = strut_radius * (new_cell / cell_size)
  // We need: 2 * strut_radius * (new_cell / cell_size) >= MIN_PRINT_DIAMETER_MM
  // new_cell >= MIN_PRINT_DIAMETER_MM * cell_size / (2 * strut_radius)
  const minCellMm =
    (MIN_PRINT_DIAMETER_MM * cellSizeMm) / (2 * strutRadiusMm)

  return {
    passes: false,
    strutDiameterMm,
    minCellMm: Math.round(minCellMm * 10) / 10,
    message: `Strut diameter ${strutDiameterMm.toFixed(3)} mm is below ${MIN_PRINT_DIAMETER_MM} mm. Use a cell size ≥ ${Math.round(minCellMm * 10) / 10} mm.`,
  }
}

