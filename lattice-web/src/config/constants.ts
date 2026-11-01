import type { Axis, JobStage, TargetMode } from '@/api/types'

export const AXES: readonly Axis[] = ['x', 'y', 'z'] as const

export const AXIS_LABELS: Record<Axis, string> = { x: 'X', y: 'Y', z: 'Z' }

export const STAGES: readonly JobStage[] = ['search', 'repair', 'verify', 'rank'] as const

export const STAGE_LABELS: Record<JobStage, string> = {
  search: 'Search',
  repair: 'Repair',
  verify: 'Verify',
  rank: 'Rank',
}

export const STAGE_DESCRIPTIONS: Record<JobStage, string> = {
  search: 'The AI proposes candidate lattices',
  repair: 'Invalid ones are fixed',
  verify: 'The physics solver recomputes stiffness and strength',
  rank: 'Best matches are ordered by error',
}

export const MODE_LABELS: Record<TargetMode, string> = {
  about: 'About',
  at_least: 'At least',
  at_most: 'At most',
}

export const MIN_PRINT_DIAMETER_MM = 0.4

export const DATASET_DENSITIES = [0.05, 0.15, 0.25] as const

export const AT_LEAST_STRENGTH_SLACK = 0.005

export const MAX_VIEWER_TILES = 5

export const MAX_STL_TILES = 8

export function jobPath(jobId: string): string {
  return `/job/${jobId}`
}

export function designPath(jobId: string, designId: string): string {
  return `/job/${jobId}/design/${designId}`
}
