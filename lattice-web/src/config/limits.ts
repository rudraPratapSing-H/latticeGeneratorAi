/**
 * PLACEHOLDER ranges – Aryan supplies the real trained ranges.
 * These only drive soft warnings and input bounds; they never hard-block the form.
 */

export const TRAINED_RANGES = {
  stiffness_gpa: { min: 0.1, max: 50 },
  strength_mpa: { min: 1, max: 500 },
  mass_g: { min: 1, max: 500 },
  rel_density: { min: 0.01, max: 0.5 },
} as const

export const FORM_BOUNDS = {
  tolerance_pct: { min: 1, max: 50 },
  n_results: { min: 1, max: 20 },
  part_size_mm: { min: 1, max: 500 },
  cell_mm: { min: 1, max: 200 },
} as const

/**
 * Reference Ti-6Al-4V per-density ranges (from section 3).
 * Used as a fallback when /api/limits is unavailable or returns an unrecognised shape.
 */
export interface DensityRange {
  stiffness_gpa: { min: number; median: number; max: number }
  strength_mpa: { min: number; median: number; max: number }
}

export interface MaterialLimits {
  densities: Record<string, DensityRange>
  stiffness_sum_max_gpa: number
  strength_max_mpa: number
}

export const TI64_LIMITS: MaterialLimits = {
  densities: {
    '0.05': {
      stiffness_gpa: { min: 0.005, median: 0.33, max: 2.5 },
      strength_mpa: { min: 0.08, median: 2.3, max: 16.0 },
    },
    '0.15': {
      stiffness_gpa: { min: 0.04, median: 1.2, max: 7.8 },
      strength_mpa: { min: 0.40, median: 7.5, max: 45.3 },
    },
    '0.25': {
      stiffness_gpa: { min: 0.10, median: 2.3, max: 13.1 },
      strength_mpa: { min: 0.83, median: 13.1, max: 76.1 },
    },
  },
  stiffness_sum_max_gpa: 0.25 * 114, // ρ_max × E_s
  strength_max_mpa: 0.36 * 0.25 * 880, // ≈ 79.2
}

/**
 * Scale Ti-6Al-4V limits for a different material (approximate).
 * Stiffness by E_s/114, strength by σ_y/880.
 */
export function scaleLimitsForMaterial(
  E_gpa: number,
  yield_mpa: number,
): MaterialLimits {
  const stiffScale = E_gpa / 114
  const strScale = yield_mpa / 880

  const densities: Record<string, DensityRange> = {}
  for (const [key, range] of Object.entries(TI64_LIMITS.densities)) {
    densities[key] = {
      stiffness_gpa: {
        min: range.stiffness_gpa.min * stiffScale,
        median: range.stiffness_gpa.median * stiffScale,
        max: range.stiffness_gpa.max * stiffScale,
      },
      strength_mpa: {
        min: range.strength_mpa.min * strScale,
        median: range.strength_mpa.median * strScale,
        max: range.strength_mpa.max * strScale,
      },
    }
  }

  return {
    densities,
    stiffness_sum_max_gpa: 0.25 * E_gpa,
    strength_max_mpa: 0.36 * 0.25 * yield_mpa,
  }
}

// PROVISIONAL: exact /api/limits shape not specified
// extractLimits tries to recognise a plausible shape, returns null otherwise
export function extractLimits(raw: unknown): MaterialLimits | null {
  if (!raw || typeof raw !== 'object') return null
  try {
    const obj = raw as Record<string, unknown>
    // Try common shapes
    if ('densities' in obj && typeof obj.densities === 'object' && obj.densities) {
      // The backend sends an ARRAY: [{rel_density, stiffness_gpa:{min,median,max}, strength_mpa:{...},
      // stiffness_sum_max_gpa, strength_max_mpa}, ...] plus top-level stiffness_max_gpa / strength_max_mpa.
      // Older/mock shapes send an object keyed by density; both are accepted.
      const densities = (
        Array.isArray(obj.densities)
          ? Object.fromEntries(
              (obj.densities as Record<string, unknown>[]).map((d) => [String(d.rel_density), d]),
            )
          : obj.densities
      ) as Record<string, unknown>
      const result: Record<string, DensityRange> = {}
      for (const [key, val] of Object.entries(densities)) {
        if (!val || typeof val !== 'object') return null
        const v = val as Record<string, unknown>
        const stiff = v.stiffness_gpa ?? v.stiffness
        const str = v.strength_mpa ?? v.strength
        if (!stiff || !str || typeof stiff !== 'object' || typeof str !== 'object') return null
        const s = stiff as Record<string, number>
        const t = str as Record<string, number>
        if (typeof s.min !== 'number' || typeof s.max !== 'number') return null
        if (typeof t.min !== 'number' || typeof t.max !== 'number') return null
        result[key] = {
          stiffness_gpa: { min: s.min, median: s.median ?? (s.min + s.max) / 2, max: s.max },
          strength_mpa: { min: t.min, median: t.median ?? (t.min + t.max) / 2, max: t.max },
        }
      }
      const bounds = obj.bounds as Record<string, number> | undefined
      const rows = Array.isArray(obj.densities) ? (obj.densities as Record<string, number>[]) : []
      const sumMax = rows.length
        ? Math.max(...rows.map((r) => Number(r.stiffness_sum_max_gpa) || 0))
        : (bounds?.stiffness_sum_max_gpa ?? 0)
      return {
        densities: result,
        stiffness_sum_max_gpa: sumMax,
        strength_max_mpa:
          typeof obj.strength_max_mpa === 'number'
            ? obj.strength_max_mpa
            : (bounds?.strength_max_mpa ?? 0),
      }
    }
    return null
  } catch {
    return null
  }
}
