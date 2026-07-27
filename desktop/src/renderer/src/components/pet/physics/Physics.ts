import * as THREE from 'three'

export interface PhysicsBody {
  position: THREE.Vector3
  velocity: THREE.Vector3
  mass: number
  radius: number
  grounded: boolean
  restitution: number
  friction: number
}

export interface SpringTarget {
  position: THREE.Vector3
  stiffness: number
  damping: number
}

export class PhysicsSystem {
  bodies: PhysicsBody[] = []
  private springs: Map<PhysicsBody, SpringTarget> = new Map()
  groundY = 0
  gravity = -12
  bounds = { minX: -2, maxX: 2, minZ: -2, maxZ: 2 }

  createBody(position: THREE.Vector3, radius = 0.3, mass = 1): PhysicsBody {
    const body: PhysicsBody = {
      position: position.clone(),
      velocity: new THREE.Vector3(),
      mass,
      radius,
      grounded: false,
      restitution: 0.3,
      friction: 0.8,
    }
    this.bodies.push(body)
    return body
  }

  attachSpring(body: PhysicsBody, target: SpringTarget) {
    this.springs.set(body, target)
  }

  removeSpring(body: PhysicsBody) {
    this.springs.delete(body)
  }

  applyForce(body: PhysicsBody, force: THREE.Vector3) {
    body.velocity.add(force.clone().divideScalar(body.mass))
  }

  impulse(body: PhysicsBody, force: THREE.Vector3) {
    const f = force.clone().multiplyScalar(0.5)
    this.applyForce(body, f)
  }

  setTargetPosition(body: PhysicsBody, target: THREE.Vector3) {
    const spring = this.springs.get(body)
    if (spring) {
      spring.position.copy(target)
    }
  }

  update(dt: number) {
    const subDt = Math.min(dt, 0.02)

    for (const body of this.bodies) {
      const spring = this.springs.get(body)

      if (spring) {
        const dx = spring.position.x - body.position.x
        const dz = spring.position.z - body.position.z
        const springForceX = dx * spring.stiffness - body.velocity.x * spring.damping
        const springForceZ = dz * spring.stiffness - body.velocity.z * spring.damping
        body.velocity.x += springForceX * subDt * 60
        body.velocity.z += springForceZ * subDt * 60
      }

      body.velocity.y += this.gravity * subDt
      body.position.x += body.velocity.x * subDt
      body.position.y += body.velocity.y * subDt
      body.position.z += body.velocity.z * subDt

      if (body.position.y < this.groundY + body.radius) {
        body.position.y = this.groundY + body.radius
        body.velocity.y *= -body.restitution
        if (Math.abs(body.velocity.y) < 0.3) body.velocity.y = 0
        body.grounded = true
      } else {
        body.grounded = false
      }

      body.velocity.x *= 1 - body.friction * subDt * 10
      body.velocity.z *= 1 - body.friction * subDt * 10

      if (body.position.x < this.bounds.minX + body.radius) {
        body.position.x = this.bounds.minX + body.radius
        body.velocity.x *= -0.5
      }
      if (body.position.x > this.bounds.maxX - body.radius) {
        body.position.x = this.bounds.maxX - body.radius
        body.velocity.x *= -0.5
      }
      if (body.position.z < this.bounds.minZ + body.radius) {
        body.position.z = this.bounds.minZ + body.radius
        body.velocity.z *= -0.5
      }
      if (body.position.z > this.bounds.maxZ - body.radius) {
        body.position.z = this.bounds.maxZ - body.radius
        body.velocity.z *= -0.5
      }
    }
  }

  getBody(index = 0): PhysicsBody | undefined {
    return this.bodies[index]
  }

  removeBody(body: PhysicsBody) {
    const idx = this.bodies.indexOf(body)
    if (idx >= 0) this.bodies.splice(idx, 1)
    this.springs.delete(body)
  }

  dispose() {
    this.bodies.length = 0
    this.springs.clear()
  }
}
