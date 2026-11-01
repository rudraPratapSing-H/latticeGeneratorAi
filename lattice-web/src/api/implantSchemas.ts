// Zod schemas for the implant endpoints. The contract test parses real backend output with them; the TypeScript types the
// pages use come from the generated OpenAPI file (implantTypes.ts), so a backend change shows up in both places.
import { z } from 'zod/v4'
import { candidateSchema } from '@/api/schemas'

const num = z.number().refine(Number.isFinite, 'must be finite')
const sourced = z.object({ value: num.nullable().optional(), source: z.string(), note: z.string().nullable().optional() })
const axisSourced = z.object({ x: sourced, y: sourced, z: sourced })
const axisNumbers = z.object({ x: num, y: num, z: num })
const kind = z.enum(['lattice', 'solid', 'undecided'])
const jobStatus = z.enum(['queued', 'running', 'done', 'failed', 'cancelled'])

export const zoneSchema = z.object({
  id: z.string(),
  name: z.string(),
  range_mm: z.tuple([num, num]),
  thickness_mm: num,
  area_mm2: num,
  stress_mpa: num,
  cells: z.number().int(),
  requirement: z.object({ stiffness_gpa: axisSourced, strength_mpa: axisSourced }).passthrough(),
  reach: z
    .object({
      level: z.enum(['covered', 'extended', 'outside', 'infeasible']),
      distance_pct: num,
      density: num,
      message: z.string(),
      snapped: z.object({ stiffness_gpa: axisNumbers, strength_mpa: axisNumbers, lattice_id: z.number() }),
    })
    .nullable()
    .optional(),
  kind,
  reason: z.string().nullable().optional(),
})

const loadCase = z.object({ name: z.string(), force_n: num, angle_deg: num })

export const zoneTableSchema = z.object({
  implant_id: z.string(),
  state: z.enum(['uploaded', 'confirmed']),
  length_mm: num.nullable().optional(),
  cell_mm: num.nullable().optional(),
  load: z
    .object({
      cases: z.array(loadCase),
      governing: loadCase,
      safety_factor: num,
      assumptions: z.array(z.object({ name: z.string(), source: z.string(), todo: z.boolean() }).passthrough()),
    })
    .nullable()
    .optional(),
  zones: z.array(zoneSchema),
  notes: z.array(z.string()),
  warnings: z.array(z.string()),
  disclaimer: z.string().includes('not a medical device'),
})

export const createImplantSchema = z.object({
  implant_id: z.string().startsWith('i_'),
  mesh_report: z
    .object({ watertight: z.boolean(), bodies: z.number(), size_mm: z.array(num).length(3), units_confident: z.boolean() })
    .passthrough(),
  fields: z.object({
    implant_type: z.string(),
    body_weight_kg: num.nullable().optional(),
    activity: z.string().nullable().optional(),
    special_rules: z.array(z.string()),
  }),
  parsed_by: z.enum(['offline', 'gemini']),
  disclaimer: z.string().includes('not a medical device'),
})

export const zoneCandidatesSchema = z.object({
  zone_id: z.string(),
  kind,
  reason: z.string().nullable(),
  candidates: z.array(candidateSchema),
  grid: z.object({ cell_mm: num, cells: z.array(z.number()).length(3), whole_cells: z.number() }).nullable(),
  job: z.object({ job_id: z.string(), status: jobStatus }).passthrough().nullable(),
})

export const assembleJobSchema = z
  .object({
    job_id: z.string().startsWith('a_'),
    status: jobStatus,
    kind: z.literal('assemble'),
    implant_id: z.string(),
    progress: num,
  })
  .passthrough()

const resultZone = z
  .object({
    id: z.string(),
    name: z.string(),
    kind,
    candidate_id: z.string().nullable(),
    verified: z.object({ label: z.literal('solver_verified_infinite_lattice') }).passthrough().nullable(),
    check: z.object({ label: z.literal('beam_model_estimate') }).passthrough().nullable(),
  })
  .passthrough()

export const implantResultSchema = z.object({
  implant_id: z.string(),
  disclaimer: z.string().includes('not a medical device'),
  zones: z.array(resultZone),
  summary: z.object({ mass_label: z.literal('geometry_only'), mass_g: num, triangles: z.number(), lattice_share_pct: num }).passthrough(),
  warnings: z.array(z.string()),
  parts: z.array(z.object({ name: z.string(), watertight: z.boolean() }).passthrough()),
  verification: z.object({
    solver_verified_infinite_lattice: z.string(),
    beam_model_estimate: z.string(),
    geometry_only: z.string(),
    not_modelled: z.string(),
  }),
})
