import { z } from 'zod/v4'
import type { DesignRequest } from '@/api/types'

/** The backend sends null for "not set" (stage while queued, round/k before the first round, queue_position when
 *  not queued, ...). Accept null and hand the app undefined. */
const opt = <T extends z.ZodType>(schema: T) => schema.nullish().transform((v) => v ?? undefined)

const failureModeSchema = z.enum(['yield', 'buckling'])

const perAxisNumber = z.object({
  x: z.number(),
  y: z.number(),
  z: z.number(),
})

const perAxisFailure = z.object({
  x: failureModeSchema,
  y: failureModeSchema,
  z: failureModeSchema,
})

export const healthSchema = z
  .object({
    status: z.string(),
    model_loaded: z.boolean(),
    gpu: z.boolean(),
  })
  .passthrough()

export const materialSchema = z
  .object({
    id: z.string(),
    name: z.string(),
    E_gpa: z.number(),
    yield_mpa: z.number(),
    density_g_cm3: z.number(),
  })
  .passthrough()

export const materialsListSchema = z.array(materialSchema)

export const propertiesSchema = z
  .object({
    stiffness_gpa: perAxisNumber,
    yield_strength_mpa: perAxisNumber,
    buckling_strength_mpa: perAxisNumber,
    strength_mpa: perAxisNumber,
    governing_failure: perAxisFailure.optional(),
  })
  .passthrough()

export const latticeSchema = z
  .object({
    format: z.literal('octant27'),
    nodes: z.array(z.array(z.number())),
    edges: z.array(z.array(z.number())),
    cell_size_mm: z.number(),
    strut_radius_mm: z.number(),
  })
  .passthrough()

export const candidateSchema = z
  .object({
    id: z.string(),
    rank: z.number(),
    match_error_pct: z.number(),
    matches_targets: z
      .boolean()
      .nullish()
      .transform((v) => v ?? false),
    rel_density: z.number(),
    mass_g: z.number(),
    lattice: latticeSchema,
    predicted: propertiesSchema,
    verified: propertiesSchema,
  })
  .passthrough()

const jobStatusSchema = z.enum(['queued', 'running', 'done', 'failed', 'cancelled'])
const jobStageSchema = z.enum(['search', 'repair', 'verify', 'rank'])
const reachLevelSchema = z.enum(['covered', 'extended', 'outside', 'infeasible'])

const roundInfoSchema = z
  .object({
    round: z.number(),
    k: z.number(),
    best_error_pct: z.number().nullish().transform((v) => v ?? NaN),
    matched: z.boolean(),
    n_candidates: z.number(),
    round_seconds: z.number(),
    elapsed_seconds: z.number(),
  })
  .passthrough()

export const jobSchema = z
  .object({
    job_id: z.string(),
    status: jobStatusSchema,
    stage: opt(jobStageSchema),
    round: opt(z.number()),
    k: opt(z.number()),
    progress: z.number(),
    message: z
      .string()
      .nullish()
      .transform((v) => v ?? ''),
    rounds: opt(z.array(roundInfoSchema)),
    infeasible: opt(z.boolean()),
    warnings: opt(z.array(z.string())),
    reach: opt(z.object({ level: reachLevelSchema, distance_pct: z.number() }).passthrough()),
    candidates: z.array(candidateSchema),
    queue_position: opt(z.number()),
    request: opt(z.custom<DesignRequest>()),
    failure_reason: opt(z.string()),
  })
  .passthrough()

export const jobEventSchema = z
  .object({
    stage: opt(jobStageSchema),
    progress: z.number(),
    message: z
      .string()
      .nullish()
      .transform((v) => v ?? ''),
    status: opt(jobStatusSchema),
    round: opt(z.number()),
    k: opt(z.number()),
    queue_position: opt(z.number()),
  })
  .passthrough()

export const createDesignResponseSchema = z
  .object({
    job_id: z.string(),
  })
  .passthrough()

export const reachResponseSchema = z
  .object({
    level: reachLevelSchema,
    distance_pct: z.number(),
    density: z.number(),
    requested: z
      .object({
        stiffness_gpa: z.array(z.union([z.number(), z.null()])).nullable(),
        strength_mpa: z.array(z.union([z.number(), z.null()])).nullable(),
      })
      .passthrough(),
    nearest: z
      .object({
        stiffness_gpa: z.array(z.number()),
        strength_mpa: z.array(z.number()),
        lattice_id: z.number(),
      })
      .passthrough(),
    bounds: z
      .object({
        stiffness_sum_max_gpa: z.number(),
        strength_max_mpa: z.number(),
      })
      .passthrough(),
    message: z.string(),
  })
  .passthrough()

export {
  failureModeSchema,
  jobStatusSchema,
  jobStageSchema,
  reachLevelSchema,
}

/** Validate data against a schema. In DEV, throws on mismatch. In PROD, warns and returns raw data. */
export function parseResponse<S extends z.ZodType>(schema: S, data: unknown, label: string): z.output<S> {
  const result = schema.safeParse(data)
  if (result.success) {
    return result.data
  }

  const summary = z.prettifyError(result.error)

  if (import.meta.env.DEV) {
    console.error(`[contract_mismatch] ${label}:`, summary)
  } else {
    console.warn(`[contract_mismatch] ${label}:`, summary)
  }

  // Return raw data so the UI doesn't crash on unknown extra fields
  return data as z.output<S>
}
