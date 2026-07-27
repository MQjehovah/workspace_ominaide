import * as THREE from 'three'
import { Engine } from './core/Engine'
import { AnimationSystem } from './core/AnimationSystem'
import { Character } from './character/Character'
import { StateMachine, type StateName } from './fsm/StateMachine'
import { InteractionSystem } from './interaction/Interaction'
import { HUDSystem } from './ui/HUD'
import { VFXSystem } from './VFX'
import { Room } from './environment/Room'
import { PhysicsSystem } from './physics/Physics'
import { BehaviorSystem } from './behavior/Behavior'
import type { PetState, PetMood } from './types'

export interface PetEngineConfig {
  modelUrl?: string
  useDog: boolean
  environment: 'room' | 'none'
  enablePhysics: boolean
  enableBehavior: boolean
  onReady?: () => void
}

export class PetEngine {
  engine!: Engine
  character!: Character
  fsm!: StateMachine
  interaction!: InteractionSystem
  hud!: HUDSystem
  vfx!: VFXSystem
  room!: Room
  physics!: PhysicsSystem
  behavior!: BehaviorSystem

  private container: HTMLElement
  private config: PetEngineConfig
  private physicsBody: import('./physics/Physics').PhysicsBody | null = null
  private currentMoveTarget: { x: number; z: number } | null = null
  private petHitTestInterval: any = null
  private petBoundsInterval: any = null
  private time = 0
  private initialized = false

  constructor(container: HTMLElement, config: PetEngineConfig) {
    this.container = container
    this.config = config
  }

  async init() {
    this.engine = new Engine(this.container)
    this.character = new Character()
    this.fsm = new StateMachine()
    this.vfx = new VFXSystem(this.engine.scene)
    this.hud = new HUDSystem({ target: this.character.group, offset: new THREE.Vector3(0, 1.8, 0) })
    this.physics = new PhysicsSystem()
    this.behavior = new BehaviorSystem()
    this.room = new Room()

    if (this.config.environment === 'room') {
      this.room.build(this.engine.scene)
    }

    this.addLights()

    // Load model FIRST so we know the actual animation clip names
    let loaded = false
    if (this.config.modelUrl) {
      loaded = await this.character.loadFromUrl(this.config.modelUrl)
    }
    if (!loaded) {
      this.character.buildDogProcedural()
      loaded = true
    }

    this.character.group.position.y = 0.3
    this.engine.scene.add(this.character.group)

    // Setup states AFTER model is loaded (to map actual clip names)
    this.setupStatesWithClips()

    this.behavior.fsm = this.fsm
    this.setupPhysics()
    this.setupBehavior()
    this.setupInteraction()

    // Play initial animation
    if (this.character.animator) {
      const clipNames = this.character.clipNames
      const idleClip = this.findClip(['Idle', 'idle', 'IDLE', 'stand', 'Stand', 'neutral'])
      if (idleClip) {
        this.character.animator.play(idleClip, 0.3, 1)
      } else if (clipNames.length > 0) {
        this.character.animator.play(clipNames[0], 0.3, 1)
      }
    }

    this.vfx = new VFXSystem(this.engine.scene)

    this.initialized = true
    this.engine.startLoop((dt) => this.update(dt))
    this.config.onReady?.()
  }

  private findClip(keywords: string[]): string | null {
    const clipNames = this.character.clipNames
    if (clipNames.length === 0) return null
    for (const name of clipNames) {
      for (const kw of keywords) {
        if (name.toLowerCase() === kw.toLowerCase()) return name
      }
    }
    for (const name of clipNames) {
      for (const kw of keywords) {
        if (name.toLowerCase().includes(kw.toLowerCase())) return name
      }
    }
    return clipNames[0]
  }

  private setupStatesWithClips() {
    const clipNames = this.character.clipNames
    const c = (keywords: string[]) => {
      const found = this.findClip(keywords)
      console.log(`[pet] mapping ${keywords[0]} -> ${found}`)
      return found || keywords[0]
    }
    const states: PetState[] = [
      { id: 'idle', name: 'Idle', animation: c(['Idle', 'idle', 'IDLE', 'stand', 'Stand', 'neutral']), blendIn: 0.3, blendOut: 0.3, loop: true, speed: 1 },
      { id: 'walk', name: 'Walk', animation: c(['Walking', 'Walk', 'walk', 'Run', 'run']), blendIn: 0.2, blendOut: 0.3, loop: true, speed: 1.2 },
      { id: 'happy', name: 'Happy', animation: c(['Dance', 'dance', 'Jump', 'jump', 'Happy', 'happy']), blendIn: 0.15, blendOut: 0.2, loop: false, speed: 1.2 },
      { id: 'sad', name: 'Sad', animation: c(['Sit', 'sit', 'Sad', 'sad', 'Death', 'death']), blendIn: 0.3, blendOut: 0.4, loop: false, speed: 0.8 },
      { id: 'sleep', name: 'Sleep', animation: c(['Sit', 'sit', 'Sleep', 'sleep', 'Idle', 'idle']), blendIn: 0.5, blendOut: 0.5, loop: true, speed: 0.3 },
      { id: 'work', name: 'Work', animation: c(['Idle', 'idle', 'IDLE']), blendIn: 0.3, blendOut: 0.3, loop: true, speed: 1 },
      { id: 'eat', name: 'Eat', animation: c(['Idle', 'idle']), blendIn: 0.2, blendOut: 0.2, loop: false, speed: 0.8 },
      { id: 'wave', name: 'Wave', animation: c(['Idle', 'idle']), blendIn: 0.15, blendOut: 0.2, loop: false, speed: 1 },
    ]
    states.forEach(s => this.fsm.register(s))

    this.fsm.onStateChange = (from, to) => {
      const animName = this.fsm.getState(to)?.animation
      if (animName) {
        const speed = this.fsm.getState(to)?.speed || 1
        this.character.animator?.play(animName, 0.2, speed)
      }
    }
  }

  private setupPhysics() {
    if (!this.config.enablePhysics) return
    this.physicsBody = this.physics.createBody(new THREE.Vector3(0, 0.3, 0), 0.25, 1.5)
    this.physics.attachSpring(this.physicsBody, {
      position: new THREE.Vector3(0, 0.3, 0),
      stiffness: 3,
      damping: 0.6,
    })
  }

  private setupBehavior() {
    if (!this.config.enableBehavior) return

    this.behavior.onAction = (action) => {
      if (action.state) {
        this.fsm.transition(action.state)
        setTimeout(() => {
          if (this.fsm.current === action.state) this.fsm.transition('idle')
        }, action.duration)
      }
      if (action.emoji) {
        this.hud.showEmotion(action.emoji, action.duration)
      }
      if (action.text) {
        this.hud.showBubble(action.text, action.duration)
      }
      if (action.vfx === 'hearts') {
        this.vfx.burstHearts(this.character.group, new THREE.Vector3(0, 1, 0.3))
      }
      if (action.vfx === 'stars') {
        this.vfx.burstStars(this.character.group, new THREE.Vector3(0, 1, 0.3))
      }
      if (action.moveTo && this.physicsBody) {
        this.currentMoveTarget = { x: action.moveTo.x, z: action.moveTo.z }
        if (!action.state || action.state === 'walk') {
          this.fsm.transition('walk')
        }
      }
    }

    this.behavior.onMoodChange = (mood: PetMood) => {
      if (mood === 'sleepy') this.hud.showEmotion('💤', 2000)
    }
  }

  private dragActive = false

  private setupInteraction() {
    this.interaction = new InteractionSystem(
      this.engine.renderer.domElement,
      this.engine.camera,
      this.engine.scene,
    )

    this.interaction.onClick = () => {
      this.behavior.pet()
      this.vfx.burstHearts(this.character.group, new THREE.Vector3(0, 1, 0.3))
    }

    this.interaction.onMenu = (x, y) => {
      // Context menu handled by Vue layer
    }

    // Make character meshes draggable
    this.interaction.dragTargets = this.character.getMeshes()

    // Drag: move physics target to follow mouse
    this.interaction.onDragStart = () => {
      this.dragActive = true
    }

    this.interaction.onDragMove = (worldX: number, worldZ: number) => {
      if (this.config.enablePhysics && this.physicsBody) {
        this.physics.setTargetPosition(this.physicsBody,
          new THREE.Vector3(worldX, 0.3, worldZ))
      } else {
        this.character.group.position.x = worldX
        this.character.group.position.z = worldZ
      }
    }

    this.interaction.onDragEnd = () => {
      this.dragActive = false
    }

    // Polling-based raycaster hit test for precise mouse passthrough
    const mqbox = (window as any).mqbox
    if (mqbox?.mouse?.getPosition && mqbox?.pet?.setHitTest) {
      let lastSent = false
      let bounds = { x: 0, y: 0, w: 280, h: 340 }

      this.petBoundsInterval = setInterval(async () => {
        try {
          const b = await mqbox.window.getBounds()
          if (b) bounds = { x: b.x, y: b.y, w: b.width, h: b.height }
        } catch {}
      }, 1000)

      this.petHitTestInterval = setInterval(async () => {
        try {
          const p = await mqbox.mouse.getPosition()
          if (!p) return
          const localX = p.x - bounds.x
          const localY = p.y - bounds.y
          const inside = localX >= 0 && localX < bounds.w && localY >= 0 && localY < bounds.h
          if (!inside) {
            if (lastSent) { lastSent = false; mqbox.pet.setHitTest(false) }
            return
          }
          const rect = this.engine.renderer.domElement.getBoundingClientRect()
          this.engine.pointer.x = ((localX - rect.left) / rect.width) * 2 - 1
          this.engine.pointer.y = -((localY - rect.top) / rect.height) * 2 + 1
          this.engine.raycaster.setFromCamera(this.engine.pointer, this.engine.camera)
          const meshes = this.character.getMeshes()
          const intersects = this.engine.raycaster.intersectObjects(meshes, false)
          const hit = intersects.length > 0
          // Keep mouse events enabled during drag
          if (!this.dragActive && hit !== lastSent) { lastSent = hit; mqbox.pet.setHitTest(hit) }
          this.engine.renderer.domElement.style.cursor = hit ? 'grab' : 'default'
        } catch {}
      }, 50)
    }
  }

  private addLights() {
    const scene = this.engine.scene
    scene.add(new THREE.HemisphereLight(0x8888ff, 0x444422, 0.4))
    const sun = new THREE.DirectionalLight(0xffeedd, 0.8)
    sun.position.set(3, 5, 4)
    sun.castShadow = true
    sun.shadow.mapSize.set(1024, 1024)
    scene.add(sun)
    scene.add(new THREE.DirectionalLight(0x8888ff, 0.2))
    const fill = new THREE.DirectionalLight(0x8888ff, 0.3)
    fill.position.set(-2, 1, -3)
    scene.add(fill)
    const rim = new THREE.DirectionalLight(0xccddff, 0.2)
    rim.position.set(-1, 2, -5)
    scene.add(rim)
  }

  private update(dt: number) {
    this.time += dt

    this.fsm.update(dt)
    this.character.animator?.update(dt)
    this.behavior.update(dt)

    if (this.config.enablePhysics && this.physicsBody) {
      if (this.fsm.current === 'walk' && this.currentMoveTarget) {
        this.physics.setTargetPosition(this.physicsBody,
          new THREE.Vector3(this.currentMoveTarget.x, 0.3, this.currentMoveTarget.z))
        const dx = this.physicsBody.position.x - this.currentMoveTarget.x
        const dz = this.physicsBody.position.z - this.currentMoveTarget.z
        const dist = Math.sqrt(dx * dx + dz * dz)
        if (dist < 0.1) {
          this.currentMoveTarget = null
          this.fsm.transition('idle')
        }
      }

      this.physics.update(dt)
      const body = this.physics.getBody(0)
      if (body) {
        this.character.group.position.x = body.position.x
        this.character.group.position.z = body.position.z
      }
    }

    this.character.updateProcedural(dt, this.time, this.fsm.current, this.currentMoveTarget)

    this.vfx.update(dt, this.time)
  }

  getBehaviorSystem(): BehaviorSystem { return this.behavior }
  getFSM(): StateMachine { return this.fsm }
  getCharacter(): Character { return this.character }

  dispose() {
    if (this.petHitTestInterval) { clearInterval(this.petHitTestInterval); this.petHitTestInterval = null }
    if (this.petBoundsInterval) { clearInterval(this.petBoundsInterval); this.petBoundsInterval = null }
    this.physics.dispose()
    this.vfx.dispose()
    this.hud.dispose()
    this.interaction.dispose()
    this.engine.stop()
  }
}
