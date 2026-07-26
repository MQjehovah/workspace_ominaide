import * as THREE from 'three'

export class Room {
  readonly group = new THREE.Group()
  private objects: Map<string, THREE.Object3D> = new Map()

  build(scene: THREE.Scene) {
    // Floor
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(6, 6),
      new THREE.MeshStandardMaterial({ color: 0x8B7355, roughness: 0.8, metalness: 0.05 })
    )
    floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true
    floor.name = 'floor'; this.group.add(floor)

    // Rug
    const rug = new THREE.Mesh(
      new THREE.CircleGeometry(1.2, 32),
      new THREE.MeshStandardMaterial({ color: 0x6B4C8B, roughness: 0.9, side: THREE.DoubleSide })
    )
    rug.rotation.x = -Math.PI / 2; rug.position.set(0, 0.01, 0); rug.name = 'rug'
    this.group.add(rug)

    // Walls
    const wallMat = new THREE.MeshStandardMaterial({ color: 0xE8E0D8, roughness: 0.6 })
    const wallH = 2.8
    // Back wall
    const bw = new THREE.Mesh(new THREE.BoxGeometry(6, wallH, 0.1), wallMat)
    bw.position.set(0, wallH / 2, -3); bw.name = 'wall_back'; this.group.add(bw)
    // Left wall
    const lw = new THREE.Mesh(new THREE.BoxGeometry(0.1, wallH, 6), wallMat)
    lw.position.set(-3, wallH / 2, 0); lw.name = 'wall_left'; this.group.add(lw)
    // Right wall
    const rw = new THREE.Mesh(new THREE.BoxGeometry(0.1, wallH, 6), wallMat)
    rw.position.set(3, wallH / 2, 0); rw.name = 'wall_right'; this.group.add(rw)

    // Desk
    const deskMat = new THREE.MeshStandardMaterial({ color: 0x5C4033, roughness: 0.7 })
    const deskTop = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.05, 0.8), deskMat)
    deskTop.position.set(0, 0.75, -1.2); deskTop.receiveShadow = true; deskTop.castShadow = true; deskTop.name = 'desk'
    this.group.add(deskTop)
    // Desk legs
    const legMat = new THREE.MeshStandardMaterial({ color: 0x333333, metalness: 0.5, roughness: 0.3 })
    ;[[-0.7, 0.4], [0.7, 0.4], [-0.7, -0.4], [0.7, -0.4]].forEach(([x, z]) => {
      const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.7, 8), legMat)
      leg.position.set(x, 0.35, z - 1.2); leg.name = 'desk_leg'; this.group.add(leg)
    })

    // Lamp on desk
    const lampBase = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.1, 0.02, 12), new THREE.MeshStandardMaterial({ color: 0x888888, metalness: 0.6 }))
    lampBase.position.set(0.5, 0.78, -1); this.group.add(lampBase)
    const lampArm = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.02, 0.25, 8), new THREE.MeshStandardMaterial({ color: 0x666666, metalness: 0.5 }))
    lampArm.position.set(0.5, 0.9, -1); this.group.add(lampArm)
    const lampShade = new THREE.Mesh(new THREE.ConeGeometry(0.12, 0.1, 12), new THREE.MeshStandardMaterial({ color: 0xFFE4B5, emissive: 0xFFE4B5, emissiveIntensity: 0.1 }))
    lampShade.position.set(0.5, 1.05, -1); this.group.add(lampShade)
    const lampLight = new THREE.PointLight(0xFFE4B5, 0.3, 2)
    lampLight.position.set(0.5, 1.0, -1); this.group.add(lampLight)

    // Chair
    const chairMat = new THREE.MeshStandardMaterial({ color: 0x4A4A4A, roughness: 0.5 })
    const seat = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.05, 0.4), chairMat)
    seat.position.set(0.8, 0.4, -0.5); seat.castShadow = true; seat.name = 'chair'
    this.group.add(seat)
    const back = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.35, 0.03), chairMat)
    back.position.set(0.8, 0.6, -0.32); this.group.add(back)
    ;[[-0.15, -0.15], [0.15, -0.15], [-0.15, 0.15], [0.15, 0.15]].forEach(([x, z]) => {
      const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.4, 6), legMat)
      leg.position.set(0.8 + x, 0.2, -0.5 + z); this.group.add(leg)
    })

    // Bookshelf
    const shelfMat = new THREE.MeshStandardMaterial({ color: 0x6B4226, roughness: 0.7 })
    const shelf = new THREE.Mesh(new THREE.BoxGeometry(0.6, 1.2, 0.2), shelfMat)
    shelf.position.set(-1.5, 0.6, -2.8); shelf.name = 'bookshelf'
    this.group.add(shelf)
    // Shelves
    ;[0.2, 0.6, 1.0].forEach(y => {
      const s = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.02, 0.15), new THREE.MeshStandardMaterial({ color: 0x8B6340 }))
      s.position.set(-1.5, y, -2.7); this.group.add(s)
    })
    // Books
    const bookColors = [0xCC4444, 0x44AA44, 0x4444CC, 0xCCCC44]
    for (let i = 0; i < 8; i++) {
      const b = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.1 + Math.random() * 0.08, 0.06), new THREE.MeshStandardMaterial({ color: bookColors[i % 4] }))
      b.position.set(-1.5 + (Math.random() - 0.5) * 0.4, 0.3 + Math.random() * 0.8, -2.6); b.rotation.y = (Math.random() - 0.5) * 0.2
      this.group.add(b)
    }

    // Picture frame on wall
    const frame = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.35, 0.03), new THREE.MeshStandardMaterial({ color: 0x8B6340 }))
    frame.position.set(1.2, 1.5, -2.94); this.group.add(frame)
    const pic = new THREE.Mesh(new THREE.PlaneGeometry(0.42, 0.28), new THREE.MeshStandardMaterial({ color: 0x87CEEB }))
    pic.position.set(1.2, 1.5, -2.92); this.group.add(pic)

    // Plant
    const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.08, 0.12, 8), new THREE.MeshStandardMaterial({ color: 0xCC6633 }))
    pot.position.set(-0.8, 0.06, 1.2); pot.name = 'plant'; this.group.add(pot)
    const soil = new THREE.Mesh(new THREE.CircleGeometry(0.08, 8), new THREE.MeshStandardMaterial({ color: 0x3B2314 }))
    soil.rotation.x = -Math.PI / 2; soil.position.set(-0.8, 0.12, 1.2); this.group.add(soil)
    for (let i = 0; i < 5; i++) {
      const leaf = new THREE.Mesh(new THREE.ConeGeometry(0.03, 0.1 + Math.random() * 0.05, 6), new THREE.MeshStandardMaterial({ color: 0x44AA44 }))
      leaf.position.set(-0.8 + (Math.random() - 0.5) * 0.06, 0.15 + Math.random() * 0.08, 1.2 + (Math.random() - 0.5) * 0.06)
      leaf.rotation.x = (Math.random() - 0.5) * 0.3; leaf.rotation.z = (Math.random() - 0.5) * 0.3
      this.group.add(leaf)
    }

    // Baseboard
    const bbMat = new THREE.MeshStandardMaterial({ color: 0x5C4033 })
    const bb = new THREE.Mesh(new THREE.BoxGeometry(6, 0.08, 0.05), bbMat)
    bb.position.set(0, 0.04, -2.97); this.group.add(bb)

    scene.add(this.group)
  }

  getObject(name: string): THREE.Object3D | undefined {
    return this.group.getObjectByName(name)
  }

  setWallColor(color: number) {
    const wallMat = new THREE.MeshStandardMaterial({ color, roughness: 0.6 })
    ;['wall_back', 'wall_left', 'wall_right'].forEach(name => {
      const obj = this.getObject(name)
      if (obj && obj instanceof THREE.Mesh) obj.material = wallMat
    })
  }

  setFloorColor(color: number) {
    const obj = this.getObject('floor')
    if (obj && obj instanceof THREE.Mesh) (obj.material as THREE.MeshStandardMaterial).color.setHex(color)
  }
}
