import { useMemo, useRef, useEffect, useState } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import type { Lattice } from '@/api/types'
import { buildTiledLattice, type Strut3D } from '@/components/LatticeViewer/geometry'
import { cn } from '@/lib/cn'
import { Play, Pause, RotateCcw } from 'lucide-react'

interface LatticeCanvasProps {
  lattice: Lattice
  tiles?: number
  renderMode?: 'solid' | 'wireframe'
  colorByAxis?: boolean
  className?: string
  onError?: (err: Error) => void
}

const Y_AXIS = new THREE.Vector3(0, 1, 0)

const AXIS_COLORS: Record<'x' | 'y' | 'z', THREE.Color> = {
  x: new THREE.Color('#f43f5e'), // rose
  y: new THREE.Color('#10b981'), // emerald
  z: new THREE.Color('#06b6d4'), // cyan
}
const DEFAULT_COLOR = new THREE.Color('#2dd4bf') // teal accent

/**
 * 3D Mesh rendering the tiled lattice struts and nodes
 */
function LatticeMesh({
  lattice,
  tiles,
  renderMode,
  colorByAxis,
}: {
  lattice: Lattice
  tiles: number
  renderMode: 'solid' | 'wireframe'
  colorByAxis: boolean
}) {
  const { struts, nodes, strutRadius } = useMemo(
    () => buildTiledLattice(lattice, tiles),
    [lattice, tiles],
  )

  const cylinderGeo = useMemo(() => new THREE.CylinderGeometry(1, 1, 1, 12), [])
  const sphereGeo = useMemo(() => new THREE.SphereGeometry(1, 12, 12), [])

  const strutInstancedRef = useRef<THREE.InstancedMesh>(null)
  const nodeInstancedRef = useRef<THREE.InstancedMesh>(null)

  // Configure strut instances
  useEffect(() => {
    if (renderMode !== 'solid' || !strutInstancedRef.current) return
    const mesh = strutInstancedRef.current
    const dummy = new THREE.Object3D()
    const dir = new THREE.Vector3()

    struts.forEach((strut: Strut3D, i: number) => {
      dummy.position.set(...strut.midpoint)

      dir.set(...strut.direction)
      dummy.quaternion.setFromUnitVectors(Y_AXIS, dir)

      dummy.scale.set(strutRadius, strut.length, strutRadius)
      dummy.updateMatrix()
      mesh.setMatrixAt(i, dummy.matrix)

      const col = colorByAxis ? AXIS_COLORS[strut.dominantAxis] : DEFAULT_COLOR
      mesh.setColorAt(i, col)
    })

    mesh.instanceMatrix.needsUpdate = true
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
  }, [struts, strutRadius, renderMode, colorByAxis])

  // Configure node joint instances
  useEffect(() => {
    if (renderMode !== 'solid' || !nodeInstancedRef.current) return
    const mesh = nodeInstancedRef.current
    const dummy = new THREE.Object3D()
    const jointRadius = strutRadius * 1.15

    nodes.forEach((node, i) => {
      dummy.position.set(...node.position)
      dummy.scale.set(jointRadius, jointRadius, jointRadius)
      dummy.updateMatrix()
      mesh.setMatrixAt(i, dummy.matrix)

      // Neutral metallic color for node balls
      mesh.setColorAt(i, DEFAULT_COLOR)
    })

    mesh.instanceMatrix.needsUpdate = true
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
  }, [nodes, strutRadius, renderMode])

  // Wireframe geometry buffer
  const wireframeGeometry = useMemo(() => {
    if (renderMode !== 'wireframe') return null
    const positions = new Float32Array(struts.length * 6)
    const colors = new Float32Array(struts.length * 6)

    struts.forEach((strut, i) => {
      const idx = i * 6
      positions[idx] = strut.start[0]
      positions[idx + 1] = strut.start[1]
      positions[idx + 2] = strut.start[2]
      positions[idx + 3] = strut.end[0]
      positions[idx + 4] = strut.end[1]
      positions[idx + 5] = strut.end[2]

      const c = colorByAxis ? AXIS_COLORS[strut.dominantAxis] : DEFAULT_COLOR
      colors[idx] = c.r
      colors[idx + 1] = c.g
      colors[idx + 2] = c.b
      colors[idx + 3] = c.r
      colors[idx + 4] = c.g
      colors[idx + 5] = c.b
    })

    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    return geo
  }, [struts, renderMode, colorByAxis])

  if (renderMode === 'wireframe' && wireframeGeometry) {
    return (
      <lineSegments geometry={wireframeGeometry}>
        <lineBasicMaterial
          vertexColors={colorByAxis}
          color={colorByAxis ? undefined : '#14b8a6'}
          linewidth={2}
        />
      </lineSegments>
    )
  }

  return (
    <group>
      {/* Volumetric Struts */}
      <instancedMesh
        ref={strutInstancedRef}
        args={[cylinderGeo, undefined, struts.length]}
      >
        <meshStandardMaterial roughness={0.34} metalness={0.35} />
      </instancedMesh>

      {/* Spherical Joints at Nodes */}
      <instancedMesh
        ref={nodeInstancedRef}
        args={[sphereGeo, undefined, nodes.length]}
      >
        <meshStandardMaterial roughness={0.4} metalness={0.35} />
      </instancedMesh>
    </group>
  )
}

/**
 * Camera controller that smoothly adapts to tiles changes and supports reset
 */
function CameraController({
  tiles,
  controlsRef,
}: {
  tiles: number
  controlsRef: React.RefObject<OrbitControlsImpl | null>
}) {
  const { camera } = useThree()

  useEffect(() => {
    const dist = tiles * 2.8 + 1.5
    camera.position.set(dist * 0.8, dist * 0.6, dist)
    camera.lookAt(0, 0, 0)
    if (controlsRef.current) {
      controlsRef.current.target.set(0, 0, 0)
      controlsRef.current.update()
    }
  }, [tiles, camera, controlsRef])

  return null
}

export function LatticeCanvas({
  lattice,
  tiles = 1,
  renderMode = 'solid',
  colorByAxis = false,
  className,
  onError,
}: LatticeCanvasProps) {
  const [autoRotate, setAutoRotate] = useState(true)
  const controlsRef = useRef<OrbitControlsImpl>(null)

  const handleResetCamera = () => {
    if (controlsRef.current) {
      const dist = tiles * 2.8 + 1.5
      controlsRef.current.object.position.set(dist * 0.8, dist * 0.6, dist)
      controlsRef.current.target.set(0, 0, 0)
      controlsRef.current.update()
    }
  }

  return (
    <div
      className={cn(
        'relative h-full w-full overflow-hidden select-none touch-none bg-surface-2',
        className,
      )}
    >
      <Canvas
        camera={{ position: [4, 3, 5], fov: 45 }}
        gl={{ antialias: true, alpha: true }}
        onCreated={({ gl }) => {
          gl.domElement.addEventListener('webglcontextlost', (e) => {
            e.preventDefault()
            onError?.(new Error('WebGL context lost'))
          })
        }}
      >
        {/* Studio Lighting */}
        <hemisphereLight args={['#dfeaff', '#1a2230', 1.1]} />
        <ambientLight intensity={0.45} />
        <directionalLight position={[10, 15, 10]} intensity={1.3} />
        <directionalLight position={[-10, -10, -5]} intensity={0.4} />
        <pointLight position={[0, 10, 0]} intensity={0.5} />

        {/* Dynamic Lattice Model */}
        <LatticeMesh
          lattice={lattice}
          tiles={tiles}
          renderMode={renderMode}
          colorByAxis={colorByAxis}
        />

        {/* Orbit Controls with 3D Motion */}
        <OrbitControls
          ref={controlsRef}
          enableDamping
          dampingFactor={0.05}
          autoRotate={autoRotate}
          autoRotateSpeed={1.8}
          minDistance={1}
          maxDistance={tiles * 12}
          makeDefault
        />

        <CameraController tiles={tiles} controlsRef={controlsRef} />
      </Canvas>

      {/* Floating 3D Control Overlay */}
      <div className="absolute top-3 right-3 flex items-center gap-1.5 z-10">
        <button
          type="button"
          onClick={() => setAutoRotate(!autoRotate)}
          className={cn(
            'flex h-8 items-center gap-1.5 rounded-lg px-3 text-xs font-medium shadow-sm transition-[background-color,color,border-color] duration-200 backdrop-blur-md',
            autoRotate
              ? 'bg-accent/15 border border-accent/40 text-accent'
              : 'bg-surface/80 border border-line text-muted hover:text-text hover:border-faint/60',
          )}
          title={autoRotate ? 'Pause 3D rotation' : 'Start 3D rotation motion'}
          aria-label={autoRotate ? 'Pause 3D rotation' : 'Start 3D rotation motion'}
        >
          {autoRotate ? (
            <>
              <Pause className="h-3 w-3" />
              <span className="hidden sm:inline">Motion</span>
            </>
          ) : (
            <>
              <Play className="h-3 w-3" />
              <span className="hidden sm:inline">Motion</span>
            </>
          )}
        </button>

        <button
          type="button"
          onClick={handleResetCamera}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-xs font-medium bg-surface/80 border border-line text-muted hover:text-text hover:border-faint/60 shadow-sm transition-[color,border-color] duration-200 backdrop-blur-md"
          title="Reset 3D camera"
          aria-label="Reset 3D camera"
        >
          <RotateCcw className="h-3 w-3" />
        </button>
      </div>

      {/* Hint overlay */}
      <div className="pointer-events-none absolute bottom-2 left-3 z-10 text-[10px] text-faint flex items-center gap-2">
        <span>Drag to rotate · Scroll or pinch to zoom</span>
      </div>
    </div>
  )
}

