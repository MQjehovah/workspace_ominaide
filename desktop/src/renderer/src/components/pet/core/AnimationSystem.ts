import * as THREE from 'three'
import type { StateName } from '../fsm/StateMachine'

export interface AnimationClipData {
  name: string
  duration: number
  loop: boolean
  speed?: number
}

export class AnimationSystem {
  private mixer: THREE.AnimationMixer
  private clips = new Map<string, THREE.AnimationClip>()
  private actions = new Map<string, THREE.AnimationAction>()
  private currentAction: THREE.AnimationAction | null = null
  private previousAction: THREE.AnimationAction | null = null

  constructor(root: THREE.Object3D) {
    this.mixer = new THREE.AnimationMixer(root)
  }

  addClip(clip: THREE.AnimationClip) {
    this.clips.set(clip.name, clip)
    const action = this.mixer.clipAction(clip)
    this.actions.set(clip.name, action)
  }

  addClipsFromModel(model: THREE.Object3D) {
    if (model.animations) {
      model.animations.forEach(clip => this.addClip(clip))
    }
  }

  play(name: string, blendDuration = 0.2, speed = 1) {
    const action = this.actions.get(name)
    if (!action) return

    if (this.currentAction === action) return

    this.previousAction = this.currentAction
    this.currentAction = action

    action.reset()
    action.setEffectiveTimeScale(speed)
    action.play()

    if (this.previousAction) {
      this.previousAction.crossFadeTo(action, blendDuration, true)
    }
  }

  update(dt: number) {
    this.mixer.update(dt)
  }

  getMixer() { return this.mixer }
  getClip(name: string) { return this.clips.get(name) }
  getAction(name: string) { return this.actions.get(name) }
}
