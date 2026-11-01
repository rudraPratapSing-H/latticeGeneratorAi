import { z } from 'zod/v4'
import { FORM_BOUNDS } from '@/config/limits'
import type { Material } from '@/api/types'

const positiveNum = z
  .string()
  .transform((v) => parseFloat(v))
  .pipe(z.number().positive('Must be greater than 0').finite('Must be a finite number'))

export function createFormSchema(materials?: Material[]) {
  return z
    .object({
      material: z.string().min(1, 'Select a material'),

      partSizeX: positiveNum,
      partSizeY: positiveNum,
      partSizeZ: positiveNum,
      cellMm: positiveNum,

      stiffnessX: z.string(),
      stiffnessY: z.string(),
      stiffnessZ: z.string(),
      stiffnessDontCareX: z.boolean(),
      stiffnessDontCareY: z.boolean(),
      stiffnessDontCareZ: z.boolean(),
      stiffnessSameAll: z.boolean(),
      stiffnessMode: z.enum(['about', 'at_least', 'at_most']),

      strengthX: z.string(),
      strengthY: z.string(),
      strengthZ: z.string(),
      strengthDontCareX: z.boolean(),
      strengthDontCareY: z.boolean(),
      strengthDontCareZ: z.boolean(),
      strengthSameAll: z.boolean(),
      strengthMode: z.enum(['about', 'at_least', 'at_most']),
      strengthType: z.enum(['effective', 'yield_only']),

      maxMassG: z.string(),
      weightMode: z.enum(['about', 'at_least', 'at_most']),
      useRelDensity: z.boolean(),
      relDensity: z.string(),

      tolerancePct: z
        .string()
        .transform((v) => parseFloat(v))
        .pipe(
          z
            .number()
            .min(FORM_BOUNDS.tolerance_pct.min, `Min ${FORM_BOUNDS.tolerance_pct.min}%`)
            .max(FORM_BOUNDS.tolerance_pct.max, `Max ${FORM_BOUNDS.tolerance_pct.max}%`),
        ),
      nResults: z
        .string()
        .transform((v) => parseInt(v, 10))
        .pipe(
          z
            .number()
            .int()
            .min(FORM_BOUNDS.n_results.min, `Min ${FORM_BOUNDS.n_results.min}`)
            .max(FORM_BOUNDS.n_results.max, `Max ${FORM_BOUNDS.n_results.max}`),
        ),
    })
    .superRefine((data, ctx) => {
      // Cell size must be ≤ min(part size)
      const cellMm =
        typeof data.cellMm === 'number' ? data.cellMm : parseFloat(data.cellMm as unknown as string)
      const sizes = [data.partSizeX, data.partSizeY, data.partSizeZ].map((s) =>
        typeof s === 'number' ? s : parseFloat(s as unknown as string),
      )
      const minSize = Math.min(...sizes.filter((s) => isFinite(s)))
      if (isFinite(cellMm) && isFinite(minSize) && cellMm > minSize) {
        ctx.addIssue({
          code: 'custom',
          message: 'Cell size must be ≤ the smallest part dimension',
          path: ['cellMm'],
        })
      }

      // Weight validation
      if (data.useRelDensity) {
        const rd = parseFloat(data.relDensity)
        if (!isFinite(rd) || rd <= 0 || rd >= 1) {
          ctx.addIssue({
            code: 'custom',
            message: 'Relative density must be between 0 and 1',
            path: ['relDensity'],
          })
        }
      } else {
        const mass = parseFloat(data.maxMassG)
        if (!isFinite(mass) || mass <= 0) {
          ctx.addIssue({
            code: 'custom',
            message: 'Mass must be greater than 0',
            path: ['maxMassG'],
          })
        }
      }

      // At least one targeted axis across stiffness + strength
      const hasStiffness =
        (!data.stiffnessDontCareX && data.stiffnessX.trim() !== '') ||
        (!data.stiffnessDontCareY && data.stiffnessY.trim() !== '') ||
        (!data.stiffnessDontCareZ && data.stiffnessZ.trim() !== '')

      const hasStrength =
        (!data.strengthDontCareX && data.strengthX.trim() !== '') ||
        (!data.strengthDontCareY && data.strengthY.trim() !== '') ||
        (!data.strengthDontCareZ && data.strengthZ.trim() !== '')

      if (!hasStiffness && !hasStrength) {
        ctx.addIssue({
          code: 'custom',
          message: 'Set at least one stiffness or strength target.',
          path: ['stiffnessX'],
        })
      }

      // Validate targeted stiffness axes are positive numbers
      if (!data.stiffnessDontCareX && data.stiffnessX.trim() !== '') {
        const v = parseFloat(data.stiffnessX)
        if (!isFinite(v) || v <= 0) {
          ctx.addIssue({ code: 'custom', message: 'Must be > 0', path: ['stiffnessX'] })
        }
      }
      if (!data.stiffnessDontCareY && !data.stiffnessSameAll && data.stiffnessY.trim() !== '') {
        const v = parseFloat(data.stiffnessY)
        if (!isFinite(v) || v <= 0) {
          ctx.addIssue({ code: 'custom', message: 'Must be > 0', path: ['stiffnessY'] })
        }
      }
      if (!data.stiffnessDontCareZ && !data.stiffnessSameAll && data.stiffnessZ.trim() !== '') {
        const v = parseFloat(data.stiffnessZ)
        if (!isFinite(v) || v <= 0) {
          ctx.addIssue({ code: 'custom', message: 'Must be > 0', path: ['stiffnessZ'] })
        }
      }

      // Validate targeted strength axes
      if (!data.strengthDontCareX && data.strengthX.trim() !== '') {
        const v = parseFloat(data.strengthX)
        if (!isFinite(v) || v <= 0) {
          ctx.addIssue({ code: 'custom', message: 'Must be > 0', path: ['strengthX'] })
        }
      }
      if (!data.strengthDontCareY && !data.strengthSameAll && data.strengthY.trim() !== '') {
        const v = parseFloat(data.strengthY)
        if (!isFinite(v) || v <= 0) {
          ctx.addIssue({ code: 'custom', message: 'Must be > 0', path: ['strengthY'] })
        }
      }
      if (!data.strengthDontCareZ && !data.strengthSameAll && data.strengthZ.trim() !== '') {
        const v = parseFloat(data.strengthZ)
        if (!isFinite(v) || v <= 0) {
          ctx.addIssue({ code: 'custom', message: 'Must be > 0', path: ['strengthZ'] })
        }
      }

      // Check against material properties if material is selected
      if (materials && data.material) {
        const mat = materials.find((m) => m.id === data.material)
        if (mat) {
          // Stiffness > E_s error with unit hint
          const checkStiff = (valStr: string, dontCare: boolean, path: string) => {
            if (!dontCare && valStr.trim() !== '') {
              const v = parseFloat(valStr)
              if (isFinite(v) && v > mat.E_gpa) {
                ctx.addIssue({
                  code: 'custom',
                  message: `Target ${v} GPa exceeds material stiffness (${mat.E_gpa} GPa). Stiffness is in GPa; did you enter MPa?`,
                  path: [path],
                })
              }
            }
          }
          checkStiff(data.stiffnessX, data.stiffnessDontCareX, 'stiffnessX')
          if (!data.stiffnessSameAll) {
            checkStiff(data.stiffnessY, data.stiffnessDontCareY, 'stiffnessY')
            checkStiff(data.stiffnessZ, data.stiffnessDontCareZ, 'stiffnessZ')
          }

          // Strength > yield error
          const checkStr = (valStr: string, dontCare: boolean, path: string) => {
            if (!dontCare && valStr.trim() !== '') {
              const v = parseFloat(valStr)
              if (isFinite(v) && v > mat.yield_mpa) {
                ctx.addIssue({
                  code: 'custom',
                  message: `Target ${v} MPa exceeds material yield strength (${mat.yield_mpa} MPa).`,
                  path: [path],
                })
              }
            }
          }
          checkStr(data.strengthX, data.strengthDontCareX, 'strengthX')
          if (!data.strengthSameAll) {
            checkStr(data.strengthY, data.strengthDontCareY, 'strengthY')
            checkStr(data.strengthZ, data.strengthDontCareZ, 'strengthZ')
          }
        }
      }
    })
}

export const formSchema = createFormSchema()
