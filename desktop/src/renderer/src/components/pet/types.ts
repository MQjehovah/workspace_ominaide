export interface PetState {
  id: string
  name: string
  animation: string
  blendIn: number
  blendOut: number
  loop: boolean
  speed: number
  layer?: number
  onEnter?: () => void
  onExit?: () => void
}

export interface PetConfig {
  modelUrl?: string
  environment: 'room' | 'outdoor'
  stats: { hunger: number; happiness: number; energy: number }
  accessories: string[]
}

export interface AnimationClipData {
  name: string
  duration: number
  blendIn: number
  blendOut: number
  loop: boolean
  speed: number
}

export type PetMood = 'happy' | 'sad' | 'sleepy' | 'excited' | 'neutral'

export interface InteractionEvent {
  type: 'click' | 'rightclick' | 'dragstart' | 'drag' | 'dragend' | 'hover'
  target?: string
  position?: THREE.Vector3
}

export interface CharacterAnimations {
  idle: AnimationClipData
  walk: AnimationClipData
  happy: AnimationClipData
  sad: AnimationClipData
  sleep: AnimationClipData
  work: AnimationClipData
  eat: AnimationClipData
  wave: AnimationClipData
}
