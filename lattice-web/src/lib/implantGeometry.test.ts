import { describe, expect, it } from 'vitest'
import candidates from '@/mocks/fixtures/real/implant/candidates_z3.json'
import zoneTable from '@/mocks/fixtures/real/implant/zones.json'
import type { Lattice } from '@/api/types'
import {
  buildShell,
  buildZoneStruts,
  sectionAt,
  stemRadiusAt,
  type ShapeZone,
} from '@/lib/implantGeometry'

const zones: ShapeZone[] = zoneTable.zones.map((z) => ({
  id: z.id,
  name: z.name,
  kind: z.kind,
  startMm: z.range_mm[0],
  endMm: z.range_mm[1],
  areaMm2: z.area_mm2,
}))
const lattice = candidates.candidates[0].lattice as unknown as Lattice
const LENGTH = 160

describe('implant geometry', () => {
  it('the radius follows each zone’s area at the zone middle', () => {
    for (const z of zones) {
      const mid = (z.startMm + z.endMm) / 2
      expect(stemRadiusAt(zones, mid)).toBeCloseTo(Math.sqrt(z.areaMm2 / Math.PI), 6)
    }
  })

  it('a section keeps the zone’s area', () => {
    const s = sectionAt(zones, 80, LENGTH)
    expect(Math.PI * s.rx * s.ry).toBeCloseTo(Math.PI * stemRadiusAt(zones, 80) ** 2, 6)
  })

  it('the shell is a closed ring tube with caps only where asked', () => {
    const open = buildShell(zones, 0, 44, LENGTH, { segments: 12, stepMm: 4 })
    const capped = buildShell(zones, 0, 44, LENGTH, {
      segments: 12,
      stepMm: 4,
      capStart: true,
      capEnd: true,
    })
    expect(open.positions.length / 3).toBe(12 * 12)
    expect(capped.indices.length - open.indices.length).toBe(2 * 12 * 3)
  })

  it('a lattice zone is filled with struts that stay inside the stem outline', () => {
    const zone = zones.find((z) => z.id === 'z3')!
    const struts = buildZoneStruts(lattice, zones, zone, LENGTH)
    expect(struts.length % 6).toBe(0)
    expect(struts.length / 6).toBeGreaterThan(500)
    for (let i = 0; i < struts.length; i += 6) {
      expect(struts[i + 1]).toBeGreaterThanOrEqual(zone.startMm - 1e-3)
      expect(struts[i + 4]).toBeLessThanOrEqual(zone.endMm + 1e-3)
    }
  })

  it('no strut is drawn twice', () => {
    const zone = zones.find((z) => z.id === 'z3')!
    const s = buildZoneStruts(lattice, zones, zone, LENGTH)
    const keys = new Set<string>()
    for (let i = 0; i < s.length; i += 6)
      keys.add(
        Array.from(s.slice(i, i + 6))
          .map((v) => v.toFixed(2))
          .join(','),
      )
    expect(keys.size).toBe(s.length / 6)
  })
})
