import type { Axis } from '@/api/types'

export interface MeshTransformConfig {
  units: 'mm' | 'm' | 'inch'
  axis: Axis
  flip: boolean
}

export const UNIT_SCALE_FACTORS: Record<'mm' | 'm' | 'inch', number> = {
  mm: 1.0,
  m: 1000.0,
  inch: 25.4,
}

export interface BoundingBox {
  min: [number, number, number]
  max: [number, number, number]
}

/**
 * Scale a 3D vector by the given unit factor to millimeters.
 */
export function scaleToMm(
  point: [number, number, number],
  units: 'mm' | 'm' | 'inch',
): [number, number, number] {
  const scale = UNIT_SCALE_FACTORS[units]
  return [point[0] * scale, point[1] * scale, point[2] * scale]
}

/**
 * Transform a 3D coordinate according to units, selected long axis, and flip.
 * Pure, unit-tested.
 */
export function transformPoint(
  point: [number, number, number],
  config: MeshTransformConfig,
): [number, number, number] {
  // 1. Scale to mm
  const scaled = scaleToMm(point, config.units)

  // 2. Re-order so chosen long axis is primary (Z-up orientation for slicing)
  let reordered: [number, number, number]
  switch (config.axis) {
    case 'x':
      // Rotate X to Z: [y, z, x]
      reordered = [scaled[1], scaled[2], scaled[0]]
      break
    case 'y':
      // Rotate Y to Z: [x, z, y]
      reordered = [scaled[0], scaled[2], scaled[1]]
      break
    case 'z':
    default:
      reordered = [scaled[0], scaled[1], scaled[2]]
      break
  }

  // 3. Apply flip along the chosen axis (now Z)
  if (config.flip) {
    reordered[2] = -reordered[2]
  }

  return reordered
}

/**
 * Transform bounding box coordinates to mm and aligned coordinate space.
 */
export function transformBoundingBox(
  bbox: BoundingBox,
  config: MeshTransformConfig,
): BoundingBox {
  const p1 = transformPoint(bbox.min, config)
  const p2 = transformPoint(bbox.max, config)

  return {
    min: [
      Math.min(p1[0], p2[0]),
      Math.min(p1[1], p2[1]),
      Math.min(p1[2], p2[2]),
    ],
    max: [
      Math.max(p1[0], p2[0]),
      Math.max(p1[1], p2[1]),
      Math.max(p1[2], p2[2]),
    ],
  }
}

/**
 * Extracts the extent/size along each axis in millimeters.
 */
export function getTransformedSize(
  bbox: BoundingBox,
  config: MeshTransformConfig,
): [number, number, number] {
  const transformed = transformBoundingBox(bbox, config)
  return [
    Math.abs(transformed.max[0] - transformed.min[0]),
    Math.abs(transformed.max[1] - transformed.min[1]),
    Math.abs(transformed.max[2] - transformed.min[2]),
  ]
}

