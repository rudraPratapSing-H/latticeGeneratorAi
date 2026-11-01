import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import { Spinner } from '@/components/feedback/Spinner'
import { Button } from '@/components/ui/button'
import type { Lattice } from '@/api/types'
import { buildShell, buildZoneStruts, sectionAt, type ShapeZone } from '@/lib/implantGeometry'

interface ImplantModel3DProps {
  zones: ShapeZone[]
  /** The chosen lattice cell of each lattice zone, by zone id. */
  lattices: Record<string, Lattice>
  lengthMm: number
  /** The lattice cells are still being fetched. */
  pending?: boolean
  /** Show only this zone, framed close up (the zone previews). */
  onlyZoneId?: string
  /** Smaller canvas, no toolbar. */
  compact?: boolean
}

/** One colour per zone, in the order of the zone strip (cyan, green, amber, purple). */
const ZONE_COLORS = ['#22d3ee', '#34d399', '#fbbf24', '#a78bfa', '#fb7185', '#60a5fa']
const BUILD_STEPS = [
  'Meshing the solid zones',
  'Tiling lattice cells into the zones',
  'Building the 3D view',
]

function hasWebGL(): boolean {
  try {
    const canvas = document.createElement('canvas')
    return !!(canvas.getContext('webgl') || canvas.getContext('experimental-webgl'))
  } catch {
    return false
  }
}

function Shell({
  data,
  color,
  opacity,
}: {
  data: ReturnType<typeof buildShell>
  color: string
  opacity: number
}) {
  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(data.positions, 3))
    g.setIndex(new THREE.BufferAttribute(data.indices, 1))
    g.computeVertexNormals()
    return g
  }, [data])
  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial
        color={color}
        side={THREE.DoubleSide}
        metalness={opacity >= 1 ? 0.3 : 0.1}
        roughness={opacity >= 1 ? 0.45 : 0.6}
        transparent={opacity < 1}
        opacity={opacity}
        depthWrite={opacity >= 1}
      />
    </mesh>
  )
}

function StrutField({
  struts,
  radius,
  color,
}: {
  struts: Float32Array
  radius: number
  color: string
}) {
  const ref = useRef<THREE.InstancedMesh>(null)
  const count = struts.length / 6

  useLayoutEffect(() => {
    const mesh = ref.current
    if (!mesh) return
    const a = new THREE.Vector3()
    const b = new THREE.Vector3()
    const dir = new THREE.Vector3()
    const mid = new THREE.Vector3()
    const scale = new THREE.Vector3()
    const quat = new THREE.Quaternion()
    const up = new THREE.Vector3(0, 1, 0)
    const m = new THREE.Matrix4()
    for (let i = 0; i < count; i++) {
      a.set(struts[i * 6], struts[i * 6 + 1], struts[i * 6 + 2])
      b.set(struts[i * 6 + 3], struts[i * 6 + 4], struts[i * 6 + 5])
      dir.subVectors(b, a)
      const len = dir.length()
      mid.addVectors(a, b).multiplyScalar(0.5)
      quat.setFromUnitVectors(up, len > 1e-9 ? dir.divideScalar(len) : up)
      scale.set(radius, Math.max(len, 1e-6), radius)
      m.compose(mid, quat, scale)
      mesh.setMatrixAt(i, m)
    }
    mesh.instanceMatrix.needsUpdate = true
  }, [struts, radius, count])

  if (count === 0) return null
  return (
    <instancedMesh ref={ref} args={[undefined, undefined, count]} frustumCulled={false}>
      <cylinderGeometry args={[1, 1, 1, 6, 1]} />
      <meshStandardMaterial color={color} metalness={0.2} roughness={0.5} />
    </instancedMesh>
  )
}

/** The assembled implant in 3D: smooth metal for solid zones, the chosen lattice cell tiled through lattice zones. */
export default function ImplantModel3D({
  zones,
  lattices,
  lengthMm,
  pending,
  onlyZoneId,
  compact,
}: ImplantModel3DProps) {
  const [webgl] = useState(hasWebGL)
  const [showShell, setShowShell] = useState(true)
  const [spin, setSpin] = useState(true)
  const [step, setStep] = useState(0)
  const [minTimeDone, setMinTimeDone] = useState(false)

  // A short build sequence so the model appears the way a real mesh would, not instantly.
  useEffect(() => {
    const timers = [
      window.setTimeout(() => setStep(1), compact ? 300 : 600),
      window.setTimeout(() => setStep(2), compact ? 600 : 1200),
      window.setTimeout(() => setMinTimeDone(true), compact ? 900 : 1800),
    ]
    return () => timers.forEach(window.clearTimeout)
  }, [compact])

  const built = useMemo(() => {
    return zones
      .map((zone, i) => ({ zone, i }))
      .filter(({ zone }) => !onlyZoneId || zone.id === onlyZoneId)
      .map(({ zone, i }) => {
        const shell = buildShell(zones, zone.startMm, zone.endMm, lengthMm, {
          capStart: !!onlyZoneId || i === 0,
          capEnd: !!onlyZoneId || i === zones.length - 1,
        })
        const lattice = zone.kind === 'lattice' ? lattices[zone.id] : undefined
        const struts = lattice ? buildZoneStruts(lattice, zones, zone, lengthMm) : null
        return { zone, shell, lattice, struts, color: ZONE_COLORS[i % ZONE_COLORS.length] }
      })
  }, [zones, lattices, lengthMm, onlyZoneId])

  // Where the camera looks and from where: the whole stem, or one zone close up.
  const view = useMemo(() => {
    const focus = onlyZoneId ? zones.find((z) => z.id === onlyZoneId) : undefined
    if (!focus) {
      return {
        target: [6, lengthMm / 2, 0] as [number, number, number],
        position: [170, 125, 290] as [number, number, number],
      }
    }
    const yMid = (focus.startMm + focus.endMm) / 2
    const sec = sectionAt(zones, yMid, lengthMm)
    const d = Math.max(focus.endMm - focus.startMm, 2.4 * sec.rx) * 1.7
    return {
      target: [sec.cx, yMid, 0] as [number, number, number],
      position: [sec.cx + d * 0.55, yMid + d * 0.3, d * 0.85] as [number, number, number],
    }
  }, [zones, lengthMm, onlyZoneId])

  const ready = minTimeDone && !pending
  const strutCount = built.reduce((n, b) => n + (b.struts ? b.struts.length / 6 : 0), 0)

  if (!webgl) {
    return (
      <div className="border-line bg-surface text-muted flex h-72 items-center justify-center rounded-xl border text-xs">
        The 3D view needs WebGL, which is not available in this browser.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div
        className={`border-line bg-surface-2 relative overflow-hidden rounded-xl border ${compact ? 'h-72' : 'h-[28rem]'}`}
      >
        <Canvas camera={{ position: view.position, fov: 35, near: 1, far: 3000 }} dpr={[1, 2]}>
          <ambientLight intensity={1.1} />
          <hemisphereLight args={['#ffffff', '#64748b', 0.6]} />
          <directionalLight position={[120, 220, 160]} intensity={1.6} />
          <directionalLight position={[-160, 60, -120]} intensity={0.6} />
          <group visible={ready}>
            {built.map(({ zone, shell, lattice, struts, color }) =>
              zone.kind === 'lattice' ? (
                <group key={zone.id}>
                  {showShell && (
                    <Shell data={shell} color={color} opacity={lattice ? 0.12 : 0.35} />
                  )}
                  {lattice && struts && (
                    <StrutField struts={struts} radius={lattice.strut_radius_mm} color={color} />
                  )}
                </group>
              ) : (
                <Shell key={zone.id} data={shell} color={color} opacity={1} />
              ),
            )}
          </group>
          <OrbitControls
            makeDefault
            enableDamping
            dampingFactor={0.06}
            target={view.target}
            autoRotate={spin && ready}
            autoRotateSpeed={1.4}
            minDistance={60}
            maxDistance={700}
          />
        </Canvas>

        {!ready && (
          <div className="bg-surface-2/90 text-muted absolute inset-0 flex flex-col items-center justify-center gap-3 text-xs">
            <Spinner size="lg" />
            <div className="text-text font-medium">
              {pending ? 'Loading the chosen lattice cells' : BUILD_STEPS[step]}
            </div>
            <div className="bg-line h-1 w-48 overflow-hidden rounded-full">
              <div
                className="bg-accent h-full transition-all duration-500"
                style={{
                  width: `${pending ? 20 : ((step + 1) / BUILD_STEPS.length) * 100}%`,
                }}
              />
            </div>
          </div>
        )}

        {ready && !compact && (
          <div className="border-line bg-surface/80 text-muted pointer-events-none absolute right-2 bottom-2 rounded-md border px-2.5 py-1 text-[11px] backdrop-blur-sm">
            Drag: rotate · Right-drag: pan · Scroll: zoom
          </div>
        )}
      </div>

      {!compact && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-muted flex flex-wrap items-center gap-3 text-[11px]">
            {built.map(({ zone }, i) => (
              <span key={zone.id} className="flex items-center gap-1.5">
                <span
                  className="h-2.5 w-2.5 rounded-sm"
                  style={{ background: ZONE_COLORS[i % ZONE_COLORS.length] }}
                />
                {zone.name} ({zone.kind})
              </span>
            ))}
            <span className="font-mono">{strutCount.toLocaleString()} struts drawn</span>
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setShowShell((v) => !v)}>
              {showShell ? 'Hide outer shell' : 'Show outer shell'}
            </Button>
            <Button size="sm" variant="outline" onClick={() => setSpin((v) => !v)}>
              {spin ? 'Stop rotating' : 'Rotate'}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
