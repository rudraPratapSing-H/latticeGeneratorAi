/**
 * Mock /api/reach implementation.
 * Clearly commented: these are mock rules, not real physics.
 */
import type { DesignRequest, ReachResponse } from '@/api/types'
import { DATASET_DENSITIES } from '@/config/constants'
import { TI64_LIMITS, scaleLimitsForMaterial } from '@/config/limits'
import type { MaterialLimits, DensityRange } from '@/config/limits'

interface MaterialInfo {
  E_gpa: number
  yield_mpa: number
  density_g_cm3: number
}

interface ReachResult {
  response?: ReachResponse
  error?: { status: number; code: string; message: string }
}

export function mockReach(request: DesignRequest, material: MaterialInfo): ReachResult {
  const partVol =
    (request.part.size_mm[0] * request.part.size_mm[1] * request.part.size_mm[2]) / 1000 // cm³

  // Determine density from request
  let targetDensity: number
  if ('rel_density' in request.target && request.target.rel_density != null) {
    targetDensity = request.target.rel_density
  } else if ('max_mass_g' in request.target && request.target.max_mass_g != null) {
    targetDensity = request.target.max_mass_g / (partVol * material.density_g_cm3)
  } else {
    targetDensity = 0.15
  }

  // ρ below 0.05 → 422 bad_target
  if (targetDensity < 0.05) {
    const lightestMass = 0.05 * partVol * material.density_g_cm3
    return {
      error: {
        status: 422,
        code: 'bad_target',
        message: `Mass limit implies ρ < 0.05. The lightest possible mass ≈ ${lightestMass.toFixed(1)} g.`,
      },
    }
  }

  // Clamp density
  if (targetDensity > 0.25) targetDensity = 0.25

  // Get limits for this material
  const limits: MaterialLimits =
    material.E_gpa === 114 && material.yield_mpa === 880
      ? TI64_LIMITS
      : scaleLimitsForMaterial(material.E_gpa, material.yield_mpa)

  // Find closest dataset density
  let bestDensity: (typeof DATASET_DENSITIES)[number] = DATASET_DENSITIES[0]
  for (const d of DATASET_DENSITIES) {
    if (d <= targetDensity + 0.001) bestDensity = d
  }

  const densityKey = bestDensity.toFixed(2)
  const range: DensityRange = limits.densities[densityKey] ?? limits.densities['0.15']!

  // Check targets
  const stiff = request.target.stiffness_gpa
  const strengthKey = 'strength_mpa' in request.target ? 'strength_mpa' : 'yield_strength_mpa'
  const strength = request.target[strengthKey as keyof typeof request.target] as
    | Record<string, number | null>
    | undefined

  const stiffValues = [stiff.x, stiff.y, stiff.z].filter((v): v is number => v != null)
  const strValues = strength
    ? [strength.x, strength.y, strength.z].filter((v): v is number => v != null)
    : []

  // Check infeasible: stiffness sum > 1.05×ρ×E_s or any strength above density max
  const stiffSum = stiffValues.reduce((a, b) => a + b, 0)
  const maxStiffSum = 1.05 * bestDensity * material.E_gpa
  const maxStrength = range.strength_mpa.max

  if (stiffSum > maxStiffSum || strValues.some((v) => v > maxStrength * 1.05)) {
    return {
      response: {
        level: 'infeasible',
        distance_pct: 100,
        density: bestDensity,
        requested: {
          stiffness_gpa: [stiff.x, stiff.y, stiff.z],
          strength_mpa: strValues.length > 0 ? strValues : [null, null, null],
        },
        nearest: {
          stiffness_gpa: stiffValues.map((v) => Math.min(v, range.stiffness_gpa.max)),
          strength_mpa: strValues.map((v) => Math.min(v, maxStrength)),
          lattice_id: 0,
        },
        bounds: {
          stiffness_sum_max_gpa: Math.round(maxStiffSum * 10) / 10,
          strength_max_mpa: Math.round(maxStrength * 10) / 10,
        },
        message: `No beam lattice can reach these targets at ρ = ${bestDensity}.`,
      },
    }
  }

  // Compute distance: max percent deviation from range
  let maxDist = 0
  for (const v of stiffValues) {
    if (v < range.stiffness_gpa.min) {
      maxDist = Math.max(maxDist, ((range.stiffness_gpa.min - v) / range.stiffness_gpa.min) * 100)
    } else if (v > range.stiffness_gpa.max) {
      maxDist = Math.max(maxDist, ((v - range.stiffness_gpa.max) / range.stiffness_gpa.max) * 100)
    }
  }
  for (const v of strValues) {
    if (v < range.strength_mpa.min) {
      maxDist = Math.max(maxDist, ((range.strength_mpa.min - v) / range.strength_mpa.min) * 100)
    } else if (v > range.strength_mpa.max) {
      maxDist = Math.max(maxDist, ((v - range.strength_mpa.max) / range.strength_mpa.max) * 100)
    }
  }

  const distPct = Math.round(maxDist * 10) / 10

  let level: 'covered' | 'extended' | 'outside'
  let message: string
  if (distPct <= 0.5) {
    level = 'covered'
    message = 'Within range of stored lattices. A match is very likely.'
  } else if (distPct <= 25) {
    level = 'extended'
    message = `No stored lattice is within ${request.tolerance_pct}%. The search will try to design a new one.`
  } else {
    level = 'outside'
    message = `Target is ${distPct}% away from the dataset. A match is unlikely.`
  }

  return {
    response: {
      level,
      distance_pct: distPct,
      density: bestDensity,
      requested: {
        stiffness_gpa: [stiff.x, stiff.y, stiff.z],
        strength_mpa: strValues.length > 0
          ? strValues
          : [null, null, null],
      },
      nearest: {
        stiffness_gpa: stiffValues.map((v) =>
          Math.min(Math.max(v, range.stiffness_gpa.min), range.stiffness_gpa.max),
        ),
        strength_mpa: strValues.map((v) =>
          Math.min(Math.max(v, range.strength_mpa.min), range.strength_mpa.max),
        ),
        lattice_id: 123456,
      },
      bounds: {
        stiffness_sum_max_gpa: Math.round(maxStiffSum * 10) / 10,
        strength_max_mpa: Math.round(maxStrength * 10) / 10,
      },
      message,
    },
  }
}

