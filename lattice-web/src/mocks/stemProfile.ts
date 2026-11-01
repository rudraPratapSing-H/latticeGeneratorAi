/**
 * Procedural femoral hip stem profile and 3D geometry generator.
 * Used for mock implant workflow and "Use sample stem" feature.
 * Generates a curved, tapered hip stem (~160 mm long, 25-45 mm wide).
 */

export interface StemSlice {
  zMm: number
  radiusMm: number
  areaMm2: number
  stressMpa: number
  targetStiffnessGpa: number
  targetStrengthMpa: number
}

/**
 * Returns procedural cross-sectional properties along the stem axis (0 to 160 mm).
 */
export function getStemSlice(zMm: number): StemSlice {
  const clampedZ = Math.max(0, Math.min(160, zMm))
  // Normalized position: 0 is tip, 1 is neck
  const t = clampedZ / 160

  // Radius tapers from 6mm at distal tip to 18mm at proximal metaphysis/neck
  const radius = 6 + 12 * Math.pow(t, 1.2)
  const area = Math.PI * radius * radius

  // Typical patient load ~2400 N joint reaction force
  // Distal stress is moderate, proximal stress is high
  const forceN = 2400
  const stress = (forceN / area) * (1.2 + 0.8 * (1 - t))

  // Bone matching target: cortical bone is stiffer proximally (~12-18 GPa), softer distally
  const targetStiff = 4 + 10 * t
  const targetStrength = 30 + 50 * t

  return {
    zMm: clampedZ,
    radiusMm: Math.round(radius * 10) / 10,
    areaMm2: Math.round(area * 10) / 10,
    stressMpa: Math.round(stress * 10) / 10,
    targetStiffnessGpa: Math.round(targetStiff * 10) / 10,
    targetStrengthMpa: Math.round(targetStrength * 10) / 10,
  }
}

/**
 * Generates an ASCII STL string for the sample femoral stem.
 * Can be parsed by STLLoader or downloaded directly.
 */
export function generateSampleStemStl(): string {
  const steps = 16
  const radialSegments = 12
  const facets: string[] = []

  const rings: [number, number, number][][] = []

  for (let i = 0; i <= steps; i++) {
    const z = (i / steps) * 160
    const slice = getStemSlice(z)
    // Curvature: hip stem curves in coronal plane (X)
    const curveX = Math.sin((i / steps) * Math.PI * 0.7) * 15

    const ring: [number, number, number][] = []
    for (let j = 0; j < radialSegments; j++) {
      const angle = (j / radialSegments) * Math.PI * 2
      const x = curveX + Math.cos(angle) * slice.radiusMm
      const y = Math.sin(angle) * slice.radiusMm * 0.8 // slight elliptical cross section
      ring.push([x, y, z])
    }
    rings.push(ring)
  }

  // Connect adjacent rings with quad facets (split into 2 triangles)
  for (let i = 0; i < steps; i++) {
    const ring1 = rings[i]
    const ring2 = rings[i + 1]

    for (let j = 0; j < radialSegments; j++) {
      const nextJ = (j + 1) % radialSegments

      const v1 = ring1[j]
      const v2 = ring1[nextJ]
      const v3 = ring2[j]
      const v4 = ring2[nextJ]

      // Triangle 1: v1, v2, v3
      facets.push(
        `facet normal 0 0 1\n  outer loop\n    vertex ${v1[0].toFixed(2)} ${v1[1].toFixed(2)} ${v1[2].toFixed(2)}\n    vertex ${v2[0].toFixed(2)} ${v2[1].toFixed(2)} ${v2[2].toFixed(2)}\n    vertex ${v3[0].toFixed(2)} ${v3[1].toFixed(2)} ${v3[2].toFixed(2)}\n  endloop\nendfacet`,
      )
      // Triangle 2: v2, v4, v3
      facets.push(
        `facet normal 0 0 1\n  outer loop\n    vertex ${v2[0].toFixed(2)} ${v2[1].toFixed(2)} ${v2[2].toFixed(2)}\n    vertex ${v4[0].toFixed(2)} ${v4[1].toFixed(2)} ${v4[2].toFixed(2)}\n    vertex ${v3[0].toFixed(2)} ${v3[1].toFixed(2)} ${v3[2].toFixed(2)}\n  endloop\nendfacet`,
      )
    }
  }

  return `solid femoral_stem\n${facets.join('\n')}\nendsolid femoral_stem`
}

