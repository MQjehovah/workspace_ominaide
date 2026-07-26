import type { PetState } from '../types'

export type StateName = 'idle' | 'walk' | 'happy' | 'sad' | 'sleep' | 'work' | 'eat' | 'wave'

export class StateMachine {
  private states = new Map<StateName, PetState>()
  private currentState: StateName = 'idle'
  private previousState: StateName = 'idle'
  private _elapsed = 0
  private transitionProgress = 1
  private _transitioning = false
  private _fromState: StateName = 'idle'
  private _toState: StateName = 'idle'

  onStateChange?: (from: StateName, to: StateName) => void

  register(state: PetState) {
    this.states.set(state.id as StateName, state)
  }

  transition(to: StateName) {
    if (to === this.currentState || this._transitioning) return
    const fromState = this.currentState
    const toState = this.states.get(to)
    if (!toState) return

    this.previousState = this.currentState
    this._fromState = this.currentState
    this._toState = to
    this._transitioning = true
    this.transitionProgress = 0

    this.states.get(fromState)?.onExit?.()
    toState.onEnter?.()

    this.onStateChange?.(fromState, to)
  }

  update(dt: number): { from: StateName; to: StateName; blend: number } {
    this._elapsed += dt
    const state = this.states.get(this.currentState)
    if (!state) return { from: 'idle', to: 'idle', blend: 1 }

    // Handle transitions
    if (this._transitioning) {
      const blendDuration = Math.max(
        this.states.get(this._fromState)?.blendOut || 0.2,
        this.states.get(this._toState)?.blendIn || 0.2
      )
      this.transitionProgress += dt / blendDuration
      if (this.transitionProgress >= 1) {
        this.transitionProgress = 1
        this._transitioning = false
        this.currentState = this._toState
      }
      return { from: this._fromState, to: this._toState, blend: Math.min(this.transitionProgress, 1) }
    }

    return { from: this.currentState, to: this.currentState, blend: 1 }
  }

  get current(): StateName { return this.currentState }
  get previous(): StateName { return this.previousState }
  get elapsed(): number { return this._elapsed }
  get transitioning(): boolean { return this._transitioning }

  getAnimationName(): string {
    const state = this.states.get(this.currentState)
    return state?.animation || 'idle'
  }

  getState(name: StateName): PetState | undefined {
    return this.states.get(name)
  }
}
