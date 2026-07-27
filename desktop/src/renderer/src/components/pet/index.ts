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

    this.character.group.scale.set(0.5, 0.5, 0.5)
    this.engine.scene.add(this.character.group)
    // compute lowest vertex Y once (idle pose) for ground alignment
    const box = new THREE.Box3().setFromObject(this.character.group)
    this.lowestY = box.min.y
    // adjust HUD offset based on model height
    this.hud = new HUDSystem({ target: this.character.group, offset: new THREE.Vector3(0, (box.max.y - box.min.y) * 0.8, 0) })

    // Setup states AFTER model is loaded (to map actual clip names)
    this.setupStatesWithClips()

    this.behavior.fsm = this.fsm
    this.setupPhysicsBounds()
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
      { id: 'walk', name: 'Walk', animation: c(['Walking', 'Walk', 'walk', 'Run', 'run']), blendIn: 0.2, blendOut: 0.3, loop: true, speed: 0.8 },
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
    this.physics.gravity = -12
    this.physics.groundY = -1.5
    this.physicsBody = this.physics.createBody(new THREE.Vector3(0, -0.5, 0), 0.3, 1)
    this.physics.attachSpring(this.physicsBody, {
      position: new THREE.Vector3(0, -0.5, 0),
      stiffness: 1.2,
      damping: 1.5,
    })
  }

  private setupPhysicsBounds() {
    const { w, h } = this.engine.getContainerSize()
    const frustumHeight = 3
    const aspect = w / h
    const halfWidth = frustumHeight * aspect / 2
    this.physics.bounds = { minX: -halfWidth, maxX: halfWidth, minZ: -1, maxZ: 1 }
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
  private wanderTimer = 0
  private nextWanderTime = 3 + Math.random() * 5
  private lowestY = 0
  hitTestLocked = false

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

    this.interaction.onDragMove = (worldX: number, _worldZ: number) => {
      // constrain to X axis only; Z stays at 0 (screen plane)
      if (this.config.enablePhysics && this.physicsBody) {
        this.physics.setTargetPosition(this.physicsBody,
          new THREE.Vector3(worldX, -0.5, 0))
      } else {
        this.character.group.position.x = worldX
        this.character.group.position.z = 0
      }
    }

    this.interaction.onDragEnd = () => {
      this.dragActive = false
    }

    // Polling-based raycaster hit test for mouse passthrough
    const mqbox = (window as any).mqbox
    if (mqbox?.mouse?.getPosition && mqbox?.pet?.setHitTest) {
      let lastHit = false
      this.petHitTestInterval = setInterval(async () => {
        try {
          const p = await mqbox.mouse.getPosition()
          if (!p) return
          const rect = this.engine.renderer.domElement.getBoundingClientRect()
          this.engine.pointer.x = ((p.x - rect.left) / rect.width) * 2 - 1
          this.engine.pointer.y = -((p.y - rect.top) / rect.height) * 2 + 1
          this.engine.raycaster.setFromCamera(this.engine.pointer, this.engine.camera)
          const meshes = this.character.getMeshes()
          const intersects = this.engine.raycaster.intersectObjects(meshes, false)
          const onMesh = intersects.length > 0
          if (this.hitTestLocked) {
            if (!lastHit) { lastHit = true; mqbox.pet.setHitTest(true) }
          } else if (onMesh !== lastHit) { lastHit = onMesh; mqbox.pet.setHitTest(onMesh) }
          this.engine.renderer.domElement.style.cursor = onMesh ? 'grab' : 'default'
        } catch {}
      }, 50)
    }
  }

  private addLights() {
    const scene = this.engine.scene
    scene.add(new THREE.HemisphereLight(0xaaccff, 0x554433, 1.2))
    const sun = new THREE.DirectionalLight(0xffeedd, 2.5)
    sun.position.set(2, 3, 4)
    sun.castShadow = true
    sun.shadow.mapSize.set(1024, 1024)
    scene.add(sun)
    const fill = new THREE.DirectionalLight(0x88bbff, 1.0)
    fill.position.set(-2, 1, 3)
    scene.add(fill)
    const rim = new THREE.DirectionalLight(0xccddff, 0.6)
    rim.position.set(0, 1, -4)
    scene.add(rim)
    const top = new THREE.DirectionalLight(0xffffff, 0.8)
    top.position.set(0, 5, 0)
    scene.add(top)
    // subtle ground shadow
    const shadowGeo = new THREE.CircleGeometry(0.6, 32)
    const shadowMat = new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.08, depthWrite: false })
    const shadow = new THREE.Mesh(shadowGeo, shadowMat)
    shadow.rotation.x = -Math.PI / 2
    shadow.position.set(0, -1.5, 0)
    shadow.name = 'pet_shadow'
    scene.add(shadow)
  }

  private update(dt: number) {
    this.time += dt

    this.fsm.update(dt)
    this.character.animator?.update(dt)
    this.behavior.update(dt)

    // Auto-wander: periodically walk to a random X position
    if (this.fsm.current === 'idle' && !this.dragActive && !this.behavior.isLocked()) {
      this.wanderTimer += dt
      if (this.wanderTimer >= this.nextWanderTime) {
        this.wanderTimer = 0
        this.nextWanderTime = 4 + Math.random() * 8
        this.startWander()
      }
    }

    if (this.config.enablePhysics && this.physicsBody) {
      if (this.fsm.current === 'walk' && this.currentMoveTarget) {
        this.physics.setTargetPosition(this.physicsBody,
          new THREE.Vector3(this.currentMoveTarget.x, -0.5, 0))
        const dx = this.physicsBody.position.x - this.currentMoveTarget.x
        const dist = Math.abs(dx)
        if (dist < 0.1) {
          this.currentMoveTarget = null
          this.fsm.transition('idle')
        }
      }

      this.physics.update(dt)
      const body = this.physics.getBody(0)
      if (body) {
        this.character.group.position.x = body.position.x
        this.character.group.position.y = body.position.y - body.radius - this.lowestY
        this.character.group.position.z = 0
        // sync animation speed with actual movement velocity
        const animSpeed = Math.max(0.3, Math.min(Math.abs(body.velocity.x) * 1.0, 2))
        this.character.animator?.setTimeScale(animSpeed)
        this.character.updateProcedural(dt, this.time, this.fsm.current, this.currentMoveTarget, body.velocity.x)
      }
    } else {
      this.character.updateProcedural(dt, this.time, this.fsm.current, this.currentMoveTarget)
    }

    // soft shadow follows character
    const shadow = this.engine.scene.getObjectByName('pet_shadow')
    if (shadow) {
      shadow.position.x = this.character.group.position.x
    }

    // Face movement direction
    if (this.currentMoveTarget) {
      const dx = this.currentMoveTarget.x - this.character.group.position.x
      if (Math.abs(dx) > 0.05) {
        this.character.group.rotation.y = dx > 0 ? Math.PI / 2 : -Math.PI / 2
      }
    } else {
      // Smoothly return to facing forward when idle
      this.character.group.rotation.y *= 0.92
    }

    this.vfx.update(dt, this.time)
  }

  private startWander() {
    const { w, h } = this.engine.getContainerSize()
    const frustumHeight = 3
    const aspect = w / h
    const halfWidth = frustumHeight * aspect / 2 - 0.4
    // shorter hops: 0.5~2.5 units from current position
    const range = 0.5 + Math.random() * 2
    const dir = Math.random() > 0.5 ? 1 : -1
    let targetX = this.character.group.position.x + dir * range
    targetX = Math.max(-halfWidth, Math.min(halfWidth, targetX))
    this.currentMoveTarget = { x: targetX, z: 0 }
    this.fsm.transition('walk')
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
