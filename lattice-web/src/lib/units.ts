/** Part volume in cm³ from dimensions in mm */
export function partVolumeCm3(sizeMm: [number, number, number]): number {
  return (sizeMm[0] * sizeMm[1] * sizeMm[2]) / 1000
}

/** Solid mass in grams: volume_cm3 × density_g_cm3 */
export function solidMassG(volumeCm3: number, densityGCm3: number): number {
  return volumeCm3 * densityGCm3
}

/** Relative density from mass and solid mass */
export function relDensityFromMass(massG: number, solidMassG: number): number {
  if (solidMassG <= 0) return 0
  return massG / solidMassG
}

/** Tiles per axis: integer count of cells that fit */
export function tilesPerAxis(sizeMm: number, cellMm: number): number {
  if (cellMm <= 0) return 0
  return Math.floor(sizeMm / cellMm)
}

/** Whether size is an integer multiple of cell size */
export function isIntegerMultiple(sizeMm: number, cellMm: number): boolean {
  if (cellMm <= 0) return false
  return Math.abs(sizeMm % cellMm) < 0.001
}

/**
 * Voigt upper bound: stiffness along an axis cannot exceed ρ × E_material.
 * Returns the bound in GPa.
 */
export function voigtBound(relDensity: number, eMaterialGpa: number): number {
  return relDensity * eMaterialGpa
}
