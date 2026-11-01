import type { TargetMode } from '@/api/types'

export interface DesignFormValues {
  material: string
  // Part
  partSizeX: string
  partSizeY: string
  partSizeZ: string
  cellMm: string
  // Stiffness
  stiffnessX: string
  stiffnessY: string
  stiffnessZ: string
  stiffnessDontCareX: boolean
  stiffnessDontCareY: boolean
  stiffnessDontCareZ: boolean
  stiffnessSameAll: boolean
  stiffnessMode: TargetMode
  // Strength
  strengthX: string
  strengthY: string
  strengthZ: string
  strengthDontCareX: boolean
  strengthDontCareY: boolean
  strengthDontCareZ: boolean
  strengthSameAll: boolean
  strengthMode: TargetMode
  strengthType: 'effective' | 'yield_only'
  // Weight
  maxMassG: string
  weightMode: TargetMode
  useRelDensity: boolean
  relDensity: string
  // Search
  tolerancePct: string
  nResults: string
}

export const DEFAULT_VALUES: DesignFormValues = {
  material: '',
  partSizeX: '40',
  partSizeY: '40',
  partSizeZ: '40',
  cellMm: '10',
  stiffnessX: '',
  stiffnessY: '',
  stiffnessZ: '',
  stiffnessDontCareX: false,
  stiffnessDontCareY: false,
  stiffnessDontCareZ: false,
  stiffnessSameAll: false,
  stiffnessMode: 'about',
  strengthX: '',
  strengthY: '',
  strengthZ: '',
  strengthDontCareX: false,
  strengthDontCareY: false,
  strengthDontCareZ: false,
  strengthSameAll: false,
  strengthMode: 'at_least',
  strengthType: 'effective',
  maxMassG: '',
  weightMode: 'at_most',
  useRelDensity: false,
  relDensity: '',
  tolerancePct: '10',
  nResults: '5',
}

export const EXAMPLE_VALUES: DesignFormValues = {
  material: 'ti64',
  partSizeX: '40',
  partSizeY: '40',
  partSizeZ: '40',
  cellMm: '10',
  stiffnessX: '8',
  stiffnessY: '8',
  stiffnessZ: '12',
  stiffnessDontCareX: false,
  stiffnessDontCareY: false,
  stiffnessDontCareZ: false,
  stiffnessSameAll: false,
  stiffnessMode: 'about',
  strengthX: '90',
  strengthY: '90',
  strengthZ: '',
  strengthDontCareX: false,
  strengthDontCareY: false,
  strengthDontCareZ: true,
  strengthSameAll: false,
  strengthMode: 'at_least',
  strengthType: 'effective',
  maxMassG: '60',
  weightMode: 'at_most',
  useRelDensity: false,
  relDensity: '',
  tolerancePct: '10',
  nResults: '5',
}
