import * as THREE from 'three'

export interface Interactable {
  object: THREE.Object3D
  onHover?: () => void
  onUnhover?: () => void
  onClick?: () => void
  onRightClick?: () => void
}

export class InteractionSystem {
  private raycaster: THREE.Raycaster
  private pointer: THREE.Vector2
  private camera: THREE.PerspectiveCamera
  private scene: THREE.Scene
  private interactables: Map<string, Interactable> = new Map()
  private hovered: string | null = null
  private domElement: HTMLElement
  private isDragging = false
  private dragObject: THREE.Object3D | null = null
  private dragPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0)
  private dragOffset = new THREE.Vector3()
  private intersectPoint = new THREE.Vector3()

  onMenu?: (x: number, y: number) => void
  onClick?: () => void

  constructor(domElement: HTMLElement, camera: THREE.PerspectiveCamera, scene: THREE.Scene) {
    this.domElement = domElement
    this.camera = camera
    this.scene = scene
    this.raycaster = new THREE.Raycaster()
    this.pointer = new THREE.Vector2()

    domElement.addEventListener('pointermove', (e) => this.onPointerMove(e))
    domElement.addEventListener('pointerdown', (e) => this.onPointerDown(e))
    domElement.addEventListener('pointerup', () => this.onPointerUp())
    domElement.addEventListener('contextmenu', (e) => {
      e.preventDefault()
      this.onMenu?.(e.clientX, e.clientY)
    })
  }

  register(name: string, interactable: Interactable) {
    this.interactables.set(name, interactable)
  }

  unregister(name: string) {
    this.interactables.delete(name)
  }

  private onPointerMove(e: PointerEvent) {
    const rect = this.domElement.getBoundingClientRect()
    this.pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
    this.pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1

    if (this.isDragging && this.dragObject) {
      this.raycaster.setFromCamera(this.pointer, this.camera)
      const intersect = this.raycaster.ray.intersectPlane(this.dragPlane, this.intersectPoint)
      if (intersect) {
        this.dragObject.position.x = intersect.x - this.dragOffset.x
        this.dragObject.position.z = intersect.z - this.dragOffset.z
      }
      return
    }

    this.raycaster.setFromCamera(this.pointer, this.camera)
    const meshes: THREE.Object3D[] = []
    this.interactables.forEach((_, name) => {
      const obj = this.findMesh(this.scene.getObjectByName(name))
      if (obj) meshes.push(obj)
    })
    if (meshes.length === 0) return

    const intersects = this.raycaster.intersectObjects(meshes)
    if (intersects.length > 0) {
      const hit = intersects[0].object
      for (const [name, inter] of this.interactables) {
        if (hit === this.findMesh(this.scene.getObjectByName(name))) {
          if (this.hovered !== name) {
            if (this.hovered) this.interactables.get(this.hovered)?.onUnhover?.()
            this.hovered = name
            inter.onHover?.()
          }
          return
        }
      }
    }
    if (this.hovered) {
      this.interactables.get(this.hovered)?.onUnhover?.()
      this.hovered = null
    }
  }

  private onPointerDown(e: PointerEvent) {
    if (e.button === 2) return
    this.onClick?.()

    this.raycaster.setFromCamera(this.pointer, this.camera)
    for (const [name, inter] of this.interactables) {
      const obj = this.findMesh(this.scene.getObjectByName(name))
      if (obj && this.raycaster.intersectObject(obj).length > 0) {
        inter.onClick?.()

        // Start drag for draggable objects
        if (obj.userData.draggable) {
          this.isDragging = true
          this.dragObject = obj
          this.dragPlane.setFromNormalAndCoplanarPoint(
            new THREE.Vector3(0, 1, 0),
            obj.position
          )
          this.raycaster.ray.intersectPlane(this.dragPlane, this.intersectPoint)
          if (this.intersectPoint) {
            this.dragOffset.copy(this.intersectPoint).sub(obj.position)
          }
        }
        return
      }
    }
  }

  private onPointerUp() {
    this.isDragging = false
    this.dragObject = null
  }

  private findMesh(obj: THREE.Object3D | null): THREE.Object3D | null {
    if (!obj) return null
    if (obj instanceof THREE.Mesh) return obj
    let result: THREE.Object3D | null = null
    obj.traverse(child => { if (child instanceof THREE.Mesh && !result) result = child })
    return result
  }

  dispose() {
    this.interactables.clear()
  }
}
