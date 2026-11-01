import type { DesignFormValues } from '@/features/design-form/defaults'
import type { DesignRequest, AxisTargets } from '@/api/types'

function parseNum(v: string): number | null {
  const n = parseFloat(v)
  return isFinite(n) ? n : null
}

/**
 * Builds a DesignRequest from form values.
 * Implements XOR rules for strength type and weight type.
 */
export function buildRequest(
  values: DesignFormValues,
  options?: { force?: boolean },
): DesignRequest {
  // Stiffness: respect "same in all directions" and "don't care"
  const stiffX = values.stiffnessDontCareX ? null : parseNum(values.stiffnessX)
  let stiffY = values.stiffnessDontCareY ? null : parseNum(values.stiffnessY)
  let stiffZ = values.stiffnessDontCareZ ? null : parseNum(values.stiffnessZ)

  if (values.stiffnessSameAll) {
    stiffY = stiffX
    stiffZ = stiffX
  }

  const stiffnessGpa: AxisTargets = { x: stiffX, y: stiffY, z: stiffZ }

  // Strength: respect "same in all directions" and "don't care"
  const strX = values.strengthDontCareX ? null : parseNum(values.strengthX)
  let strY = values.strengthDontCareY ? null : parseNum(values.strengthY)
  let strZ = values.strengthDontCareZ ? null : parseNum(values.strengthZ)

  if (values.strengthSameAll) {
    strY = strX
    strZ = strX
  }

  const strengthAxes: AxisTargets = { x: strX, y: strY, z: strZ }

  // Build target with XOR rules
  const target: DesignRequest['target'] = {
    stiffness_gpa: stiffnessGpa,
    ...(values.strengthType === 'yield_only'
      ? { yield_strength_mpa: strengthAxes }
      : { strength_mpa: strengthAxes }),
    ...(values.useRelDensity
      ? { rel_density: parseNum(values.relDensity) ?? 0.1 }
      : { max_mass_g: parseNum(values.maxMassG) ?? 60 }),
  } as DesignRequest['target']

  return {
    material: values.material,
    part: {
      size_mm: [
        parseNum(values.partSizeX) ?? 40,
        parseNum(values.partSizeY) ?? 40,
        parseNum(values.partSizeZ) ?? 40,
      ],
      cell_mm: parseNum(values.cellMm) ?? 10,
    },
    target,
    modes: {
      stiffness: values.stiffnessMode,
      strength: values.strengthMode,
      weight: values.weightMode,
    },
    tolerance_pct: parseNum(values.tolerancePct) ?? 10,
    n_results: parseInt(values.nResults, 10) || 5,
    ...(options?.force ? { force: true } : {}),
  }
}
