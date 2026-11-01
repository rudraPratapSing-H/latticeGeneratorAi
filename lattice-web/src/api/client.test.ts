import { describe, it, expect } from 'vitest'
import {
  candidateSchema,
  jobSchema,
  reachResponseSchema,
  parseResponse,
} from '@/api/schemas'
import { ApiError } from '@/api/client'

describe('ApiError', () => {
  it('creates ApiError with code, message and status', () => {
    const err = new ApiError('bad_target', 'Target out of bounds', 422)
    expect(err.code).toBe('bad_target')
    expect(err.message).toBe('Target out of bounds')
    expect(err.status).toBe(422)
    expect(err.name).toBe('ApiError')
  })
})

describe('Schema Conformance', () => {
  it('validates candidate where predicted has NO governing_failure and verified has governing_failure', () => {
    const candidateData = {
      id: 'd_a47b310b',
      rank: 1,
      match_error_pct: 0.88,
      matches_targets: true,
      rel_density: 0.05,
      mass_g: 14.2,
      lattice: {
        format: 'octant27',
        nodes: [
          [0.0, 0.0, 0.0],
          [0.5, 0.0, 0.0],
          [0.5, 0.5, 0.0],
        ],
        edges: [
          [8, 12],
          [1, 4],
        ],
        cell_size_mm: 10.0,
        strut_radius_mm: 0.29672,
      },
      predicted: {
        stiffness_gpa: { x: 0.456, y: 0.496, z: 0.423 },
        yield_strength_mpa: { x: 3.7, y: 3.44, z: 3.03 },
        buckling_strength_mpa: { x: 4.11, y: 4.5, z: 4.02 },
        strength_mpa: { x: 3.7, y: 3.44, z: 3.03 },
        // NO governing_failure
      },
      verified: {
        stiffness_gpa: { x: 0.467, y: 0.5, z: 0.403 },
        yield_strength_mpa: { x: 3.6, y: 2.7, z: 2.59 },
        buckling_strength_mpa: { x: 4.06, y: 4.35, z: 3.5 },
        strength_mpa: { x: 3.6, y: 2.7, z: 2.59 },
        governing_failure: { x: 'yield', y: 'yield', z: 'yield' },
      },
      extra_backend_field: 'safe with passthrough',
    }

    const parsed = candidateSchema.safeParse(candidateData)
    expect(parsed.success).toBe(true)
    if (parsed.success) {
      expect(parsed.data.predicted.governing_failure).toBeUndefined()
      expect(parsed.data.verified.governing_failure?.x).toBe('yield')
    }
  })

  it('validates Job example with rounds and reach', () => {
    const jobData = {
      job_id: 'j_01',
      status: 'running',
      stage: 'verify',
      round: 2,
      k: 300,
      progress: 0.45,
      message: 'Round 2 of up to 3: checking 180 of 400 designs',
      rounds: [
        {
          round: 1,
          k: 100,
          best_error_pct: 11.8,
          matched: false,
          n_candidates: 240,
          round_seconds: 10.1,
          elapsed_seconds: 10.1,
        },
      ],
      infeasible: false,
      warnings: [],
      reach: { level: 'covered', distance_pct: 3.2 },
      candidates: [],
    }

    const parsed = jobSchema.safeParse(jobData)
    expect(parsed.success).toBe(true)
  })

  it('validates ReachResponse example', () => {
    const reachData = {
      level: 'extended',
      distance_pct: 17.3,
      density: 0.15,
      requested: { stiffness_gpa: [2.0, 1.7, 2.2], strength_mpa: [13, 12, 13] },
      nearest: {
        stiffness_gpa: [1.9, 1.6, 2.0],
        strength_mpa: [11.5, 10.8, 12.1],
        lattice_id: 123456,
      },
      bounds: { stiffness_sum_max_gpa: 17.1, strength_max_mpa: 45.3 },
      message: 'No stored lattice is within 10%. The search will try to design a new one.',
    }

    const parsed = reachResponseSchema.safeParse(reachData)
    expect(parsed.success).toBe(true)
  })

  it('passthrough preserves unknown extra backend fields', () => {
    const raw = {
      job_id: 'j_99',
      status: 'done',
      progress: 1,
      message: 'Done',
      candidates: [],
      extra_unknown_server_metric: 42,
    }

    const res = parseResponse(jobSchema, raw, 'test')
    expect((res as Record<string, unknown>).extra_unknown_server_metric).toBe(42)
  })
})
