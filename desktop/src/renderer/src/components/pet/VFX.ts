import * as THREE from 'three'

export class VFXSystem {
  private particles: THREE.Points[] = []
  private sparkles: THREE.Mesh[] = []
  private scene: THREE.Scene

  constructor(scene: THREE.Scene) {
    this.scene = scene
    this.createAmbientParticles()
  }

  private createAmbientParticles() {
    const count = 60
    const geo = new THREE.BufferGeometry()
    const pos = new Float32Array(count * 3)
    const sizes = new Float32Array(count)
    for (let i = 0; i < count; i++) {
      pos[i*3] = (Math.random() - 0.5) * 6
      pos[i*3+1] = Math.random() * 3
      pos[i*3+2] = (Math.random() - 0.5) * 6 - 1
      sizes[i] = Math.random() * 3 + 1
    }
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    geo.setAttribute('size', new THREE.BufferAttribute(sizes, 1))
    const mat = new THREE.PointsMaterial({
      color: 0x8888FF, size: 0.015, transparent: true, opacity: 0.3,
      blending: THREE.AdditiveBlending, depthWrite: false
    })
    const points = new THREE.Points(geo, mat)
    points.userData = { speeds: Array.from({length: count}, () => 0.002 + Math.random() * 0.004) }
    this.particles.push(points)
    this.scene.add(points)
  }

  burstHearts(parent: THREE.Object3D, position: THREE.Vector3, count = 8) {
    for (let i = 0; i < count; i++) {
      const h = new THREE.Mesh(
        new THREE.SphereGeometry(0.025, 6, 6),
        new THREE.MeshBasicMaterial({ color: 0xFF4080 })
      )
      h.position.copy(position)
      h.position.x += (Math.random() - 0.5) * 0.2
      h.position.y += (Math.random() - 0.5) * 0.2
      const dir = new THREE.Vector3((Math.random() - 0.5) * 0.04, 0.02 + Math.random() * 0.03, (Math.random() - 0.5) * 0.04)
      let age = 0
      const obj = h
      parent.add(obj)
      this.sparkles.push(obj)
      const anim = () => {
        age += 0.02
        if (age > 1) {
          parent.remove(obj)
          const idx = this.sparkles.indexOf(obj)
          if (idx >= 0) this.sparkles.splice(idx, 1)
          return
        }
        obj.position.add(dir)
        obj.scale.setScalar(1 - age * 0.7)
        requestAnimationFrame(anim)
      }
      anim()
    }
  }

  burstStars(parent: THREE.Object3D, position: THREE.Vector3, count = 6) {
    for (let i = 0; i < count; i++) {
      const s = new THREE.Mesh(
        new THREE.SphereGeometry(0.02, 6, 6),
        new THREE.MeshBasicMaterial({ color: 0xFFD700 })
      )
      s.position.copy(position)
      const dir = new THREE.Vector3((Math.random() - 0.5) * 0.05, 0.015 + Math.random() * 0.03, (Math.random() - 0.5) * 0.05)
      let age = 0
      parent.add(s)
      const anim = () => {
        age += 0.02
        if (age > 1) { parent.remove(s); return }
        s.position.add(dir)
        s.scale.setScalar(1 - age * 0.8)
        requestAnimationFrame(anim)
      }
      anim()
    }
  }

  update(dt: number, time: number) {
    // Animate ambient particles
    this.particles.forEach(points => {
      const pos = points.geometry.attributes.position.array as Float32Array
      const speeds = points.userData.speeds as number[]
      for (let i = 0; i < pos.length / 3; i++) {
        pos[i*3+1] += speeds[i] * dt * 60
        pos[i*3] += Math.sin(time + i) * 0.001
        if (pos[i*3+1] > 3) { pos[i*3+1] = 0; pos[i*3] = (Math.random() - 0.5) * 6 }
      }
      points.geometry.attributes.position.needsUpdate = true
    })
  }

  dispose() {
    this.particles.forEach(p => this.scene.remove(p))
    this.sparkles.forEach(s => s.parent?.remove(s))
    this.particles = []
    this.sparkles = []
  }
}
