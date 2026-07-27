import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { AnimationSystem } from '../core/AnimationSystem'

export class Character {
  readonly group = new THREE.Group()
  animator: AnimationSystem | null = null
  modelRoot: THREE.Object3D | null = null
  private meshes: THREE.Mesh[] = []
  private isDog = false
  clipNames: string[] = []

  tailBone: THREE.Object3D | null = null
  headBone: THREE.Object3D | null = null
  earBones: THREE.Object3D[] = []
  armBones: THREE.Object3D[] = []
  legBones: THREE.Object3D[] = []

  async loadFromUrl(url: string): Promise<boolean> {
    return new Promise(resolve => {
      const loader = new GLTFLoader()
      loader.load(url, gltf => {
        const model = gltf.scene
        model.scale.set(0.8, 0.8, 0.8)
        model.position.set(0, 0, 0)
        model.traverse(child => {
          if (child instanceof THREE.Mesh) {
            child.castShadow = true
            child.receiveShadow = true
            this.meshes.push(child)
          }
        })
        this.group.add(model)
        this.modelRoot = model

        this.animator = new AnimationSystem(model)
        if (gltf.animations?.length) {
          gltf.animations.forEach(clip => {
            this.animator!.addClip(clip)
            this.clipNames.push(clip.name)
          })
        }
        this.isDog = false
        resolve(true)
      }, undefined, () => resolve(false))
    })
  }

  buildDogProcedural() {
    this.isDog = true
    const fur = new THREE.MeshStandardMaterial({ color: 0xD4A574, roughness: 0.7, metalness: 0 })
    const furDark = new THREE.MeshStandardMaterial({ color: 0x8B6914, roughness: 0.8 })
    const furLight = new THREE.MeshStandardMaterial({ color: 0xF0D5B0, roughness: 0.7 })
    const noseMat = new THREE.MeshStandardMaterial({ color: 0x2C1810, roughness: 0.9 })
    const eyeMat = new THREE.MeshStandardMaterial({ color: 0x1a1a2e, roughness: 0 })
    const eyeW = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.1 })

    // Body - elongated, lower to ground
    const body = new THREE.Mesh(new THREE.SphereGeometry(0.45, 24, 24), fur)
    body.position.set(0, 0.55, 0)
    body.scale.set(1.2, 0.85, 0.9)
    body.castShadow = true
    body.name = 'body'
    this.group.add(body)
    this.meshes.push(body)

    // Chest (lighter fur)
    const chest = new THREE.Mesh(new THREE.SphereGeometry(0.3, 16, 16), furLight)
    chest.position.set(0.2, 0.45, 0.55)
    chest.scale.set(0.7, 0.8, 0.5)
    chest.name = 'chest'
    this.group.add(chest)
    this.meshes.push(chest)

    // Head
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.3, 24, 24), fur)
    head.position.set(0, 0.85, 0.55)
    head.scale.set(0.9, 0.85, 0.8)
    head.name = 'head'
    this.group.add(head)
    this.headBone = head
    this.meshes.push(head)

    // Snout / muzzle
    const snout = new THREE.Mesh(new THREE.SphereGeometry(0.16, 16, 16), furLight)
    snout.position.set(0, 0.78, 0.78)
    snout.scale.set(0.7, 0.55, 0.6)
    snout.name = 'snout'
    this.group.add(snout)
    this.meshes.push(snout)

    // Nose
    const nose = new THREE.Mesh(new THREE.SphereGeometry(0.045, 8, 8), noseMat)
    nose.position.set(0, 0.78, 0.9)
    nose.name = 'nose'
    this.group.add(nose)
    this.meshes.push(nose)

    // Eyes
    ;[-0.1, 0.1].forEach(x => {
      const w = new THREE.Mesh(new THREE.SphereGeometry(0.08, 12, 12), eyeW)
      w.position.set(x, 0.92, 0.72)
      w.scale.set(1, 0.85, 0.35)
      this.group.add(w)
      this.meshes.push(w)

      const p = new THREE.Mesh(new THREE.SphereGeometry(0.045, 8, 8), eyeMat)
      p.position.set(x, 0.91, 0.76)
      p.scale.set(1, 0.9, 0.5)
      this.group.add(p)
      this.meshes.push(p)

      const h = new THREE.Mesh(new THREE.SphereGeometry(0.015, 6, 6), new THREE.MeshBasicMaterial({ color: 0xffffff }))
      h.position.set(x + 0.02, 0.93, 0.78)
      this.group.add(h)
      this.meshes.push(h)
    })

    // Ears - floppy dog ears
    ;[-1, 1].forEach(side => {
      const ear = new THREE.Mesh(new THREE.SphereGeometry(0.08, 8, 8), furDark)
      ear.position.set(side * 0.22, 1.05, 0.55)
      ear.scale.set(0.6, 1.2, 0.3)
      ear.name = 'ear'
      this.group.add(ear)
      this.earBones.push(ear)
      this.meshes.push(ear)
    })

    // Tail
    const tailGroup = new THREE.Group()
    tailGroup.position.set(-0.45, 0.6, -0.1)
    tailGroup.name = 'tail'
    const tailSeg1 = new THREE.Mesh(new THREE.SphereGeometry(0.04, 8, 8), fur)
    tailSeg1.position.set(0, 0.06, 0)
    tailSeg1.scale.set(1, 1.3, 0.7)
    tailGroup.add(tailSeg1)
    const tailSeg2 = new THREE.Mesh(new THREE.SphereGeometry(0.035, 8, 8), furDark)
    tailSeg2.position.set(0, 0.13, 0)
    tailSeg2.scale.set(0.8, 1.2, 0.6)
    tailGroup.add(tailSeg2)
    const tailTip = new THREE.Mesh(new THREE.SphereGeometry(0.03, 8, 8), furLight)
    tailTip.position.set(0, 0.2, 0)
    tailGroup.add(tailTip)
    this.group.add(tailGroup)
    this.tailBone = tailGroup

    // Legs
    ;[[-0.25, 0.25], [0.25, 0.25], [-0.25, -0.25], [0.25, -0.25]].forEach(([x, z], i) => {
      const leg = new THREE.Mesh(new THREE.SphereGeometry(0.06, 8, 8), fur)
      leg.position.set(x, 0.15, z)
      leg.scale.set(0.6, 1.5, 0.6)
      leg.name = 'leg'
      this.group.add(leg)
      this.legBones.push(leg)
      this.meshes.push(leg)

      const paw = new THREE.Mesh(new THREE.SphereGeometry(0.05, 8, 8), furLight)
      paw.position.set(x, 0.03, z)
      paw.scale.set(0.8, 0.4, 0.7)
      paw.name = 'paw'
      this.group.add(paw)
      this.meshes.push(paw)
    })

    this.group.position.y = 0
    this.animator = new AnimationSystem(this.group)
    this.generateDogClips()
  }

  private generateDogClips() {
    const dummyClip = new THREE.AnimationClip('idle', 1, [])
    this.animator?.addClip(dummyClip)
    const happyClip = new THREE.AnimationClip('happy', 0.5, [])
    this.animator?.addClip(happyClip)
    const sleepClip = new THREE.AnimationClip('sleep', 2, [])
    this.animator?.addClip(sleepClip)
    const walkClip = new THREE.AnimationClip('walk', 1, [])
    this.animator?.addClip(walkClip)
    const sadClip = new THREE.AnimationClip('sad', 1.5, [])
    this.animator?.addClip(sadClip)
  }

  updateProcedural(dt: number, time: number, stateName: string, moveTarget?: { x: number; z: number } | null) {
    if (!this.isDog) return

    const breathe = Math.sin(time * 1.5) * 0.008
    this.group.position.y = breathe

    // Tail wag
    if (this.tailBone) {
      const wagSpeed = stateName === 'happy' ? 8 : stateName === 'sad' ? 0.5 : stateName === 'sleep' ? 0.2 : 3
      const wagAmount = stateName === 'happy' ? 0.5 : stateName === 'sad' ? 0.05 : stateName === 'sleep' ? 0.02 : 0.2
      this.tailBone.rotation.z = Math.sin(time * wagSpeed) * wagAmount
    }

    // Ear flop
    this.earBones.forEach((ear, i) => {
      const baseRot = i === 0 ? 0.15 : -0.15
      ear.rotation.z = baseRot + Math.sin(time * 2.5 + i) * 0.05
      if (stateName === 'happy') ear.rotation.z = baseRot + Math.sin(time * 4 + i) * 0.08
      if (stateName === 'sad') ear.rotation.z = baseRot - 0.1 + Math.sin(time * 1 + i) * 0.02
    })

    // Head tilt
    if (this.headBone) {
      if (stateName === 'happy') {
        this.headBone.rotation.z = Math.sin(time * 2) * 0.05
      } else if (stateName === 'sad') {
        this.headBone.rotation.z = 0.08
        this.headBone.rotation.x = 0.1
      } else if (stateName === 'sleep') {
        this.headBone.rotation.x = 0.4
        this.headBone.rotation.z = 0.1
      } else {
        this.headBone.rotation.z = Math.sin(time * 0.8) * 0.02
        this.headBone.rotation.x = 0
      }
    }

    // Leg animation (walk cycle / idle)
    this.legBones.forEach((leg, i) => {
      if (stateName === 'walk' && moveTarget) {
        const phase = i * Math.PI / 2
        leg.rotation.x = Math.sin(time * 4 + phase) * 0.2
      } else if (stateName === 'happy') {
        leg.position.y = 0.15 + Math.sin(time * 6 + i * 1.5) * 0.04
      } else if (stateName === 'sleep') {
        leg.rotation.x = -0.3
        leg.position.y = 0.05
      } else {
        leg.rotation.x = Math.sin(time * 1.2 + i) * 0.03
      }
    })
  }

  getAnimator() { return this.animator }
  getMeshes(): THREE.Mesh[] { return this.meshes }
  getIsDog(): boolean { return this.isDog }
}
