import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { AnimationSystem } from '../core/AnimationSystem'

export class Character {
  readonly group = new THREE.Group()
  animator: AnimationSystem | null = null
  modelRoot: THREE.Object3D | null = null
  private mixamoRoot: THREE.Object3D | null = null

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
          }
        })
        this.group.add(model)
        this.modelRoot = model
        this.mixamoRoot = model

        this.animator = new AnimationSystem(model)
        if (gltf.animations?.length) {
          gltf.animations.forEach(clip => this.animator!.addClip(clip))
        }
        resolve(true)
      }, undefined, () => resolve(false))
    })
  }

  buildProcedural() {
    const bodyMat = new THREE.MeshStandardMaterial({ color: 0x6C63FF, roughness: 0.25, metalness: 0.05 })
    const darkMat = new THREE.MeshStandardMaterial({ color: 0x5A52D4, roughness: 0.35 })

    // Body
    const body = new THREE.Mesh(new THREE.SphereGeometry(0.55, 24, 24), bodyMat)
    body.position.y = 0.7; body.scale.set(1, 0.9, 0.85); body.castShadow = true; body.name = 'body'
    this.group.add(body)

    // Head (attached to body as a group for animation)
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.35, 24, 24), bodyMat)
    head.position.set(0, 1.05, 0); head.scale.set(0.9, 0.85, 0.8); head.name = 'head'
    this.group.add(head)

    // Eyes
    const eyeW = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.1 })
    const eyeP = new THREE.MeshStandardMaterial({ color: 0x1a1a2e, roughness: 0 })
    ;[-0.12, 0.12].forEach(x => {
      const w = new THREE.Mesh(new THREE.SphereGeometry(0.12, 16, 16), eyeW)
      w.position.set(x, 1.15, 0.45); w.scale.set(1, 0.8, 0.3); this.group.add(w)
      const p = new THREE.Mesh(new THREE.SphereGeometry(0.06, 12, 12), eyeP)
      p.position.set(x, 1.13, 0.53); p.scale.set(1, 0.9, 0.5); this.group.add(p)
      const h = new THREE.Mesh(new THREE.SphereGeometry(0.02, 6, 6), new THREE.MeshBasicMaterial({ color: 0xffffff }))
      h.position.set(x + 0.03, 1.16, 0.56); this.group.add(h)
    })

    // Ears
    ;[-0.25, 0.25].forEach((x, i) => {
      const e = new THREE.Mesh(new THREE.ConeGeometry(0.1, 0.18, 8), darkMat)
      e.position.set(x, 1.38, 0); e.rotation.z = i === 0 ? 0.3 : -0.3; e.name = 'ear'; this.group.add(e)
      const ie = new THREE.Mesh(new THREE.ConeGeometry(0.05, 0.08, 6), new THREE.MeshBasicMaterial({ color: 0xFFB8B8 }))
      ie.position.set(x, 1.34, 0); ie.rotation.z = i === 0 ? 0.3 : -0.3; this.group.add(ie)
    })

    // Cheeks
    ;[-0.3, 0.3].forEach(x => {
      const c = new THREE.Mesh(new THREE.SphereGeometry(0.06, 8, 8), new THREE.MeshBasicMaterial({ color: 0xFFB0A0, transparent: true, opacity: 0.3 }))
      c.position.set(x, 0.95, 0.42); c.scale.set(1.3, 0.55, 0.15); this.group.add(c)
    })

    // Mouth
    const mp: THREE.Vector3[] = []
    for (let i = -0.08; i <= 0.08; i += 0.015) mp.push(new THREE.Vector3(i, 0.88 + Math.sin(i * 18) * 0.015, 0.48))
    this.group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(mp), new THREE.LineBasicMaterial({ color: 0x4a4a6a })))

    // Arms
    ;[-1, 1].forEach(x => {
      const a = new THREE.Mesh(new THREE.SphereGeometry(0.07, 8, 8), bodyMat)
      a.position.set(x * 0.7, 0.6, 0.35); a.scale.set(0.5, 0.7, 0.5); a.name = 'arm'; this.group.add(a)
    })

    // Feet
    ;[-1, 1].forEach(x => {
      const f = new THREE.Mesh(new THREE.SphereGeometry(0.08, 8, 8), darkMat)
      f.position.set(x * 0.2, 0.05, 0); f.scale.set(0.8, 0.4, 0.6); this.group.add(f)
    })

    // Core glow
    const core = new THREE.Mesh(new THREE.SphereGeometry(0.06, 8, 8), new THREE.MeshBasicMaterial({ color: 0x8888FF }))
    core.position.set(0, 0.6, 0.45); core.name = 'core'; this.group.add(core)

    this.group.position.y = 0
    this.animator = new AnimationSystem(this.group)
    this.generateProceduralClips()
  }

  private generateProceduralClips() {
    // Since we don't have skeletal animations for procedural characters,
    // we create dummy clips. The actual animation is done in the update loop.
    const dummyClip = new THREE.AnimationClip('idle', 1, [])
    this.animator?.addClip(dummyClip)
    const happyClip = new THREE.AnimationClip('happy', 0.5, [])
    this.animator?.addClip(happyClip)
    const sleepClip = new THREE.AnimationClip('sleep', 2, [])
    this.animator?.addClip(sleepClip)
  }

  getAnimator() { return this.animator }

  getHeadBone(): THREE.Object3D | null {
    return this.group.getObjectByName('head')
  }

  getArmBones(): { left: THREE.Object3D | null; right: THREE.Object3D | null } {
    const arms = this.group.children.filter(c => c.name === 'arm')
    return { left: arms[0] || null, right: arms[1] || null }
  }

  getEarBones(): { left: THREE.Object3D | null; right: THREE.Object3D | null } {
    const ears = this.group.children.filter(c => c.name === 'ear')
    return { left: ears[0] || null, right: ears[1] || null }
  }

  getCoreMesh(): THREE.Mesh | null {
    return (this.group.getObjectByName('core') as THREE.Mesh) || null
  }
}
