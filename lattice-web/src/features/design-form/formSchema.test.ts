import { describe, it, expect } from 'vitest'
import { createFormSchema } from '@/features/design-form/formSchema'
import { EXAMPLE_VALUES } from '@/features/design-form/defaults'
import type { Material } from '@/api/types'

const mockMaterials: Material[] = [
  { id: 'ti64', name: 'Ti-6Al-4V', E_gpa: 114, yield_mpa: 880, density_g_cm3: 4.43 },
]

describe('formSchema', () => {
  const schema = createFormSchema(mockMaterials)

  it('validates example values successfully', () => {
    const result = schema.safeParse(EXAMPLE_VALUES)
    expect(result.success).toBe(true)
  })

  it('fails if no material is chosen', () => {
    const result = schema.safeParse({ ...EXAMPLE_VALUES, material: '' })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.some((i) => i.path.includes('material'))).toBe(true)
    }
  })

  it('fails if cell size > part dimension', () => {
    const result = schema.safeParse({
      ...EXAMPLE_VALUES,
      partSizeX: '10',
      partSizeY: '10',
      partSizeZ: '10',
      cellMm: '20',
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.some((i) => i.path.includes('cellMm'))).toBe(true)
    }
  })

  it('fails when no stiffness or strength target is provided', () => {
    const result = schema.safeParse({
      ...EXAMPLE_VALUES,
      stiffnessX: '',
      stiffnessY: '',
      stiffnessZ: '',
      strengthX: '',
      strengthY: '',
      strengthZ: '',
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(
        result.error.issues.some((i) =>
          i.message.includes('Set at least one stiffness or strength target'),
        ),
      ).toBe(true)
    }
  })

  it('fails when stiffness exceeds material E_s with unit hint', () => {
    const result = schema.safeParse({
      ...EXAMPLE_VALUES,
      stiffnessX: '150', // exceeds Ti64 114 GPa
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      const issue = result.error.issues.find((i) => i.path.includes('stiffnessX'))
      expect(issue).toBeDefined()
      expect(issue?.message).toContain('Stiffness is in GPa; did you enter MPa?')
    }
  })

  it('fails when strength exceeds material yield', () => {
    const result = schema.safeParse({
      ...EXAMPLE_VALUES,
      strengthX: '1000', // exceeds Ti64 880 MPa
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      const issue = result.error.issues.find((i) => i.path.includes('strengthX'))
      expect(issue).toBeDefined()
      expect(issue?.message).toContain('exceeds material yield strength')
    }
  })
})
