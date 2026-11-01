/**
 * One WebGL renderer shared by every candidate thumbnail.
 *
 * A results page can show up to 20 designs; one WebGL context each would hit the browser's context limit and
 * stall the page. Instead a single offscreen renderer draws each visible design in turn and copies the frame into
 * that card's own 2D canvas. Designs that are off screen, or a hidden tab, cost nothing.
 */
import * as THREE from 'three'
import type { Lattice } from '@/api/types'
import { buildTiledLattice } from '@/components/LatticeViewer/geometry'

const SIZE = 512 // render target in pixels; each card scales it into its own canvas
const Y_AXIS = new THREE.Vector3(0, 1, 0)

export interface ThumbHandle {
  setHover: (hover: boolean) => void
  dispose: () => void
}

interface Sub {
  canvas: HTMLCanvasElement
  ctx: CanvasRenderingContext2D
  model: THREE.Group
  visible: boolean
  hover: boolean
  angle: number
  speed: number
  onLost: () => void
}

let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene
let camera: THREE.PerspectiveCamera
let lost = false
const subs = new Set<Sub>()
let raf = 0
let last = 0

const sharedCylinder = new THREE.CylinderGeometry(1, 1, 1, 10, 1)
const sharedSphere = new THREE.SphereGeometry(1, 12, 10)

export function webglAvailable(): boolean {
  if (typeof document === 'undefined') return false
  try {
    const c = document.createElement('canvas')
    return !!(c.getContext('webgl2') || c.getContext('webgl'))
  } catch {
    return false
  }
}

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

function ensureRenderer(): boolean {
  if (lost) return false
  if (renderer) return true
  if (!webglAvailable()) return false
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: false })
    renderer.setPixelRatio(1)
    renderer.setSize(SIZE, SIZE, false)
    renderer.setClearColor(0x000000, 0)
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.domElement.addEventListener('webglcontextlost', (e) => {
      e.preventDefault()
      lost = true
      subs.forEach((s) => s.onLost())
      stop()
    })
    scene = new THREE.Scene()
    camera = new THREE.PerspectiveCamera(32, 1, 0.1, 50)
    camera.position.set(0, 2.0, 9.4)
    camera.lookAt(0, -0.15, 0)
    // studio lighting: soft sky/ground fill, one key light, one cool rim from behind
    scene.add(new THREE.HemisphereLight(0xdfeaff, 0x1a2230, 1.05))
    const key = new THREE.DirectionalLight(0xffffff, 2.1)
    key.position.set(4, 6, 5)
    scene.add(key)
    const rim = new THREE.DirectionalLight(0x7dd3fc, 1.2)
    rim.position.set(-5, 2, -4)
    scene.add(rim)
    return true
  } catch {
    lost = true
    return false
  }
}

function accentColor(): THREE.Color {
  const css = getComputedStyle(document.documentElement).getPropertyValue('--color-accent').trim()
  try {
    return new THREE.Color(css || '#22d3ee')
  } catch {
    return new THREE.Color('#22d3ee')
  }
}

/** The lattice as instanced struts and joints, centred on the origin and scaled to fit the frame. */
function buildModel(lattice: Lattice): THREE.Group {
  const { struts, nodes, strutRadius } = buildTiledLattice(lattice, 1)
  const color = accentColor()
  const strutMat = new THREE.MeshStandardMaterial({ color, roughness: 0.34, metalness: 0.35 })
  const jointMat = new THREE.MeshStandardMaterial({ color: color.clone().multiplyScalar(0.8), roughness: 0.4, metalness: 0.35 })

  const strutMesh = new THREE.InstancedMesh(sharedCylinder, strutMat, struts.length)
  const dummy = new THREE.Object3D()
  const dir = new THREE.Vector3()
  struts.forEach((s, i) => {
    dummy.position.set(...s.midpoint)
    dummy.quaternion.setFromUnitVectors(Y_AXIS, dir.set(...s.direction))
    dummy.scale.set(strutRadius, s.length, strutRadius)
    dummy.updateMatrix()
    strutMesh.setMatrixAt(i, dummy.matrix)
  })
  const jointMesh = new THREE.InstancedMesh(sharedSphere, jointMat, nodes.length)
  nodes.forEach((n, i) => {
    dummy.position.set(...n.position)
    dummy.quaternion.identity()
    dummy.scale.setScalar(strutRadius * 1.25)
    dummy.updateMatrix()
    jointMesh.setMatrixAt(i, dummy.matrix)
  })

  // unit-cell outline: a faint box so the part reads as a cell, not a floating tangle
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.BoxGeometry(2, 2, 2)),
    new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.22 }),
  )
  const g = new THREE.Group()
  g.add(strutMesh, jointMesh, edges)
  g.scale.setScalar(1.02)
  return g
}

function drawSub(sub: Sub): void {
  const r = renderer!
  sub.model.rotation.set(0.5, sub.angle, 0.12)
  scene.add(sub.model)
  r.render(scene, camera)
  scene.remove(sub.model)
  const { width, height } = sub.canvas
  sub.ctx.clearRect(0, 0, width, height)
  sub.ctx.drawImage(r.domElement, 0, 0, SIZE, SIZE, 0, 0, width, height)
}

function frame(t: number): void {
  raf = 0
  if (!renderer || document.hidden) return
  const dt = Math.min(0.05, (t - last) / 1000 || 0.016)
  last = t
  let any = false
  subs.forEach((s) => {
    if (!s.visible) return
    any = true
    s.angle += dt * s.speed * (s.hover ? 2.6 : 1)
    drawSub(s)
  })
  if (any) raf = requestAnimationFrame(frame)
}

function start(): void {
  if (!raf && !document.hidden) {
    last = performance.now()
    raf = requestAnimationFrame(frame)
  }
}

function stop(): void {
  if (raf) cancelAnimationFrame(raf)
  raf = 0
}

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => (document.hidden ? stop() : start()))
}

/**
 * Show `lattice` rotating in `canvas`. Returns null when WebGL is not available (the caller shows a fallback).
 * With reduced motion the design is drawn once and never animated.
 */
export function attachThumbnail(
  canvas: HTMLCanvasElement,
  lattice: Lattice,
  seed: number,
  onLost: () => void,
): ThumbHandle | null {
  if (!ensureRenderer()) return null
  const ctx = canvas.getContext('2d')
  if (!ctx) return null
  const model = buildModel(lattice)
  const reduce = prefersReducedMotion()
  const sub: Sub = {
    canvas,
    ctx,
    model,
    visible: false,
    hover: false,
    angle: 0.6 + (seed % 628) / 100, // every card starts at its own angle, so a grid never rotates in lockstep
    speed: 0.55 + ((seed >> 3) % 20) / 100,
    onLost,
  }
  subs.add(sub)

  const io = new IntersectionObserver(
    (entries) => {
      sub.visible = entries.some((e) => e.isIntersecting)
      if (sub.visible) {
        if (reduce) drawSub(sub)
        else start()
      }
    },
    { rootMargin: '80px' },
  )
  io.observe(canvas)

  return {
    setHover: (h) => {
      sub.hover = h
    },
    dispose: () => {
      io.disconnect()
      subs.delete(sub)
      model.traverse((o) => {
        const m = o as THREE.Mesh
        if (m.isMesh || (o as THREE.LineSegments).isLineSegments) {
          const mat = (m as THREE.Mesh).material as THREE.Material | THREE.Material[]
          ;(Array.isArray(mat) ? mat : [mat]).forEach((x) => x.dispose())
          if ((o as THREE.LineSegments).isLineSegments) (m.geometry as THREE.BufferGeometry).dispose()
        }
        if ((o as THREE.InstancedMesh).isInstancedMesh) (o as THREE.InstancedMesh).dispose()
      })
    },
  }
}
