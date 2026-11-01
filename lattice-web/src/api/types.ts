/**
 * Lattice Designer API types.
 * This file can later be replaced by openapi-typescript output from FastAPI's openapi.json.
 * Do NOT install openapi-typescript now.
 */

export type Axis = 'x' | 'y' | 'z'
export type PerAxis<T> = Record<Axis, T>
export type AxisTargets = PerAxis<number | null>
export type TargetMode = 'about' | 'at_least' | 'at_most'
export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
export type JobStage = 'search' | 'repair' | 'verify' | 'rank'
export type FailureMode = 'yield' | 'buckling'
export type ReachLevel = 'covered' | 'extended' | 'outside' | 'infeasible'

export interface Material {
  id: string
  name: string
  E_gpa: number
  yield_mpa: number
  density_g_cm3: number
}

export interface HealthResponse {
  status: string
  model_loaded: boolean
  gpu: boolean
}

type StrengthTarget =
  | { strength_mpa: AxisTargets; yield_strength_mpa?: never }
  | { yield_strength_mpa: AxisTargets; strength_mpa?: never }

type WeightTarget =
  { max_mass_g: number; rel_density?: never } | { rel_density: number; max_mass_g?: never }

export interface DesignRequest {
  material: string
  part: { size_mm: [number, number, number]; cell_mm: number }
  target: { stiffness_gpa: AxisTargets } & StrengthTarget & WeightTarget
  modes: { stiffness: TargetMode; strength: TargetMode; weight: TargetMode }
  tolerance_pct: number
  n_results: number
  force?: boolean
}

export interface CreateDesignResponse {
  job_id: string
}

export interface ReachResponse {
  level: ReachLevel
  distance_pct: number
  density: number
  requested: { stiffness_gpa: (number | null)[] | null; strength_mpa: (number | null)[] | null }
  nearest: { stiffness_gpa: number[]; strength_mpa: number[]; lattice_id: number }
  bounds: { stiffness_sum_max_gpa: number; strength_max_mpa: number }
  message: string
}

export interface Properties {
  stiffness_gpa: PerAxis<number>
  yield_strength_mpa: PerAxis<number>
  buckling_strength_mpa: PerAxis<number>
  strength_mpa: PerAxis<number>
  governing_failure?: PerAxis<FailureMode>
}

export interface Lattice {
  format: 'octant27'
  nodes: number[][]
  edges: number[][]
  cell_size_mm: number
  strut_radius_mm: number
}

export interface Candidate {
  id: string
  rank: number
  match_error_pct: number
  matches_targets: boolean
  rel_density: number
  mass_g: number
  lattice: Lattice
  predicted: Properties
  verified: Properties
}

export interface RoundInfo {
  round: number
  k: number
  best_error_pct: number
  matched: boolean
  n_candidates: number
  round_seconds: number
  elapsed_seconds: number
}

export interface Job {
  job_id: string
  status: JobStatus
  stage?: JobStage
  round?: number
  k?: number
  progress: number
  message: string
  rounds?: RoundInfo[]
  infeasible?: boolean
  warnings?: string[]
  reach?: { level: ReachLevel; distance_pct: number }
  candidates: Candidate[]
  queue_position?: number
  request?: DesignRequest
}

export interface JobEvent {
  stage?: JobStage
  progress: number
  message: string
}

export interface ApiErrorBody {
  error: { code: string; message: string }
}
