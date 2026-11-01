/**
 * Implant workflow types. Generated from the backend's OpenAPI document (npm run gen:api); nothing here is hand-typed
 * except the few shapes the backend returns as plain objects (zone candidates, the finished result).
 */
import type { components } from '@/api/generated'
import type { Candidate } from '@/api/types'

type S = components['schemas']

export type ZoneKind = S['Zone']['kind']
export type MeshReport = S['MeshReport']
export type ImplantFields = S['ImplantFields']
export type CreateImplantResponse = S['CreateImplantResponse']
export type ConfirmImplantRequest = S['ConfirmImplantRequest']
export type SourcedValue = S['SourcedValue']
export type Zone = S['Zone']
export type ZoneTable = S['ZoneTable']
export type ZoneEdit = S['ZoneEdit']
export type ZoneEditRequest = S['ZoneEditRequest']
export type LoadSummary = S['LoadSummary']
export type AssembleRequest = S['AssembleRequest']

/** GET /api/implants/{id}/zones/{zone}/candidates */
export interface ZoneCandidates {
  zone_id: string
  kind: ZoneKind
  reason: string | null
  candidates: Candidate[]
  grid: { cell_mm: number; cells: [number, number, number]; whole_cells: number } | null
  job: {
    job_id: string
    status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
    stage: string | null
    progress: number | null
    message: string | null
    queue_position: number | null
  } | null
}

export type VerificationLabel =
  | 'solver_verified_infinite_lattice'
  | 'beam_model_estimate'
  | 'geometry_only'
  | 'not_modelled'

export interface ZoneCheck {
  label: 'beam_model_estimate'
  stiffness_z_gpa: number | null
  infinite_lattice_z_gpa?: number | null
  ratio_to_infinite?: number | null
  block_cells?: number[]
  zone_cells?: number[]
  representative?: boolean
  candidate_verified_z_gpa?: number | null
  note?: string
  warning?: string
}

/** GET /api/implants/{id}/result */
export interface ImplantResult {
  implant_id: string
  disclaimer: string
  zones: {
    id: string
    name: string
    range_mm: [number, number]
    kind: ZoneKind
    stress_mpa: number
    requirement: Zone['requirement']
    candidate_id: string | null
    verified: {
      stiffness_gpa: Candidate['verified']['stiffness_gpa']
      strength_mpa: Candidate['verified']['strength_mpa']
      rel_density: number
      label: 'solver_verified_infinite_lattice'
    } | null
    check: ZoneCheck | null
  }[]
  summary: {
    length_mm: number
    cell_mm: number
    interface_mm: number
    sides: number
    triangles: number
    volume_mm3: number
    mass_g: number
    lattice_share_pct: number
    stl_bytes: number
    mass_label: 'geometry_only'
  }
  notes: string[]
  warnings: string[]
  parts: { name: string; kind: string; triangles: number; watertight: boolean; volume_mm3: number }[]
  verification: Record<VerificationLabel, string>
}
