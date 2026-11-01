import { useMemo, Suspense } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Center } from '@react-three/drei'
import * as THREE from 'three'
import type { Lattice } from '@/api/types'

interface LatticeSceneProps {
  lattice: Lattice
  tiles?: number
  renderMode?: 'solid' | 'wireframe'
  colorByAxis?: boolean
}

function getStrutColor(
  start: [number, number, number],
  end: [number, number, number],
  colorByAxis?: boolean,
): string {
  if (!colorByAxis) return '#6366f1' // Accent indigo
  const dx = Math.abs(end[0] - start[0])
  const dy = Math.abs(end[1] - start[1])
  const dz = Math.abs(end[2] - start[2])
  if (dx >= dy && dx >= dz) return '#ef4444' // X = Red
  if (dy >= dx && dy >= dz) return '#22c55e' // Y = Green
  return '#3b82f6' // Z = Blue
}

function Strut({
  start,
  end,
  radius,
  color,
}: {
  start: [number, number, number]
  end: [number, number, number]
  radius: number
  color: string
}) {
  const { mid, quat, len } = useMemo(() => {
    const pA = new THREE.Vector3(...start)
    const pB = new THREE.Vector3(...end)
    const dir = new THREE.Vector3().subVectors(pB, pA)
    const len = dir.length()
    const mid = new THREE.Vector3().addVectors(pA, pB).multiplyScalar(0.5)
    const quat = new THREE.Quaternion().setFromUnitVectors(
      new THREE.Vector3(0, 1, 0),
      dir.clone().normalize(),
    )
    return { mid, quat, len }
  }, [start, end])

  if (len < 0.0001) return null

  return (
    <mesh position={mid} quaternion={quat} castShadow receiveShadow>
      <cylinderGeometry args={[radius, radius, len, 12]} />
      <meshStandardMaterial color={color} metalness={0.4} roughness={0.3} />
    </mesh>
  )
}

function LatticeMesh({ lattice, tiles = 1, renderMode = 'solid', colorByAxis }: LatticeSceneProps) {
  const { struts, nodesList, wireframePositions } = useMemo(() => {
    const baseNodes = lattice.nodes
    const baseEdges = lattice.edges

    // Find bounding box to normalize spacing
    let minX = Infinity,
      minY = Infinity,
      minZ = Infinity
    let maxX = -Infinity,
      maxY = -Infinity,
      maxZ = -Infinity
    for (const [x, y, z] of baseNodes) {
      if (x < minX) minX = x
      if (y < minY) minY = y
      if (z < minZ) minZ = z
      if (x > maxX) maxX = x
      if (y > maxY) maxY = y
      if (z > maxZ) maxZ = z
    }
    const sizeX = maxX - minX || 1
    const sizeY = maxY - minY || 1
    const sizeZ = maxZ - minZ || 1

    const allStruts: Array<{
      start: [number, number, number]
      end: [number, number, number]
      color: string
    }> = []

    const uniqueNodes = new Map<string, [number, number, number]>()
    const lineCoords: number[] = []

    // Tile across 3D
    const t = Math.max(1, Math.min(5, tiles))
    for (let tx = 0; tx < t; tx++) {
      for (let ty = 0; ty < t; ty++) {
        for (let tz = 0; tz < t; tz++) {
          const offsetX = tx * sizeX
          const offsetY = ty * sizeY
          const offsetZ = tz * sizeZ

          for (const [iA, iB] of baseEdges) {
            const nA = baseNodes[iA]
            const nB = baseNodes[iB]
            if (!nA || !nB) continue

            const start: [number, number, number] = [
              nA[0] + offsetX,
              nA[1] + offsetY,
              nA[2] + offsetZ,
            ]
            const end: [number, number, number] = [
              nB[0] + offsetX,
              nB[1] + offsetY,
              nB[2] + offsetZ,
            ]

            const color = getStrutColor(start, end, colorByAxis)
            allStruts.push({ start, end, color })

            // Nodes
            uniqueNodes.set(`${start[0]},${start[1]},${start[2]}`, start)
            uniqueNodes.set(`${end[0]},${end[1]},${end[2]}`, end)

            // Wireframe
            lineCoords.push(...start, ...end)
          }
        }
      }
    }

    return {
      struts: allStruts,
      nodesList: Array.from(uniqueNodes.values()),
      wireframePositions: new Float32Array(lineCoords),
    }
  }, [lattice, tiles, colorByAxis])

  // Normalized strut radius for rendering
  const strutRadius = useMemo(() => {
    const rawR = lattice.strut_radius_mm
    const cellSize = lattice.cell_size_mm || 10
    const ratio = rawR / cellSize
    return Math.max(0.02, Math.min(0.08, ratio * 0.5))
  }, [lattice])

  if (renderMode === 'wireframe') {
    return (
      <Center>
        <lineSegments>
          <bufferGeometry>
            <bufferAttribute
              attach="attributes-position"
              args={[wireframePositions, 3]}
            />
          </bufferGeometry>
          <lineBasicMaterial color={colorByAxis ? '#a5b4fc' : '#6366f1'} linewidth={2} />
        </lineSegments>
      </Center>
    )
  }

  return (
    <Center>
      <group>
        {/* Render struts */}
        {struts.map((s, idx) => (
          <Strut key={idx} start={s.start} end={s.end} radius={strutRadius} color={s.color} />
        ))}

        {/* Render node spheres */}
        {nodesList.map((pos, idx) => (
          <mesh key={`node-${idx}`} position={pos}>
            <sphereGeometry args={[strutRadius * 1.3, 12, 12]} />
            <meshStandardMaterial
              color={colorByAxis ? '#818cf8' : '#4f46e5'}
              metalness={0.5}
              roughness={0.2}
            />
          </mesh>
        ))}
      </group>
    </Center>
  )
}

export function LatticeScene({
  lattice,
  tiles = 1,
  renderMode = 'solid',
  colorByAxis = false,
}: LatticeSceneProps) {
  return (
    <div className="relative h-full w-full select-none">
      <Canvas
        camera={{ position: [2.5, 2.5, 3.5], fov: 45 }}
        style={{ background: 'transparent' }}
      >
        <ambientLight intensity={0.8} />
        <directionalLight position={[10, 15, 10]} intensity={1.2} />
        <directionalLight position={[-10, -10, -5]} intensity={0.4} />
        <pointLight position={[0, 5, 0]} intensity={0.5} />

        <Suspense fallback={null}>
          <LatticeMesh
            lattice={lattice}
            tiles={tiles}
            renderMode={renderMode}
            colorByAxis={colorByAxis}
          />
        </Suspense>

        <OrbitControls
          makeDefault
          enableDamping
          dampingFactor={0.05}
          minDistance={1}
          maxDistance={25}
        />
      </Canvas>

      {/* Orbit & Pan hint banner */}
      <div className="bg-surface/80 border-line text-muted pointer-events-none absolute right-2 bottom-2 rounded-md border px-2.5 py-1 text-[11px] backdrop-blur-sm">
        Left-click: Rotate · Right-click: Pan · Scroll: Zoom
      </div>
    </div>
  )
}

