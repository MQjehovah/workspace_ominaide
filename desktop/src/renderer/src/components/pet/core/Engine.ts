import * as THREE from 'three'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js'
import { CSS2DRenderer, CSS2DObject } from 'three/examples/jsm/renderers/CSS2DRenderer.js'

export class Engine {
  scene: THREE.Scene
  camera: THREE.PerspectiveCamera
  renderer: THREE.WebGLRenderer
  composer: EffectComposer
  labelRenderer: CSS2DRenderer
  clock: THREE.Clock
  raycaster: THREE.Raycaster
  pointer: THREE.Vector2

  private container: HTMLElement
  private animId = 0

  constructor(container: HTMLElement) {
    this.container = container
    const w = container.clientWidth || window.innerWidth
    const h = container.clientHeight || window.innerHeight

    // Scene
    this.scene = new THREE.Scene()
    this.scene.fog = new THREE.Fog(0x87CEEB, 8, 20)

    // Camera
    this.camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 100)
    this.camera.position.set(3, 2.5, 5)
    this.camera.lookAt(0, 1, 0)

    // WebGL Renderer
    this.renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true })
    this.renderer.setSize(w, h)
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 1.0
    container.prepend(this.renderer.domElement)

    // CSS2D Label Renderer (for HUD)
    this.labelRenderer = new CSS2DRenderer()
    this.labelRenderer.setSize(w, h)
    this.labelRenderer.domElement.style.position = 'absolute'
    this.labelRenderer.domElement.style.top = '0'
    this.labelRenderer.domElement.style.pointerEvents = 'none'
    container.appendChild(this.labelRenderer.domElement)

    // Post-processing
    this.composer = new EffectComposer(this.renderer)
    this.composer.addPass(new RenderPass(this.scene, this.camera))
    const bloom = new UnrealBloomPass(new THREE.Vector2(w, h), 0.15, 0.2, 0.05)
    this.composer.addPass(bloom)
    this.composer.addPass(new OutputPass())

    // Helpers
    this.clock = new THREE.Clock()
    this.raycaster = new THREE.Raycaster()
    this.pointer = new THREE.Vector2()

    // Resize
    window.addEventListener('resize', () => this.resize())
  }

  resize() {
    const w = this.container.clientWidth || window.innerWidth
    const h = this.container.clientHeight || window.innerHeight
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
    this.renderer.setSize(w, h)
    this.composer.setSize(w, h)
    this.labelRenderer.setSize(w, h)
  }

  startLoop(callback: (dt: number) => void) {
    const loop = () => {
      this.animId = requestAnimationFrame(loop)
      const dt = Math.min(this.clock.getDelta(), 0.05)
      callback(dt)
      this.composer.render()
      this.labelRenderer.render(this.scene, this.camera)
    }
    loop()
  }

  stop() {
    cancelAnimationFrame(this.animId)
    this.renderer.dispose()
    this.labelRenderer.domElement.remove()
  }

  getContainerSize() {
    return { w: this.container.clientWidth || window.innerWidth, h: this.container.clientHeight || window.innerHeight }
  }
}
