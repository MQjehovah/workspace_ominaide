import type { StateName, StateMachine } from '../fsm/StateMachine'
import type { PetMood } from '../types'

export interface BehaviorAction {
  type: 'state' | 'emoji' | 'bubble' | 'vfx' | 'move'
  state?: StateName
  emoji?: string
  text?: string
  vfx?: 'hearts' | 'stars'
  moveTo?: { x: number; z: number }
  duration: number
  priority: number
}

export interface MoodConfig {
  name: PetMood
  decayRate: number
  minActions: number
  maxActions: number
  actions: BehaviorAction[]
}

export class BehaviorSystem {
  fsm: StateMachine | null = null

  private mood: PetMood = 'neutral'
  private moodValues: Record<PetMood, number> = {
    happy: 70, sad: 10, sleepy: 20, excited: 40, neutral: 60,
  }
  private time = 0
  private actionTimer = 0
  private nextActionTime = 5 + Math.random() * 8
  private currentAction: BehaviorAction | null = null
  private actionProgress = 0
  private locked = false

  onAction?: (action: BehaviorAction) => void
  onMoodChange?: (mood: PetMood) => void

  private readonly moods: MoodConfig[] = [
    {
      name: 'neutral', decayRate: 1, minActions: 3, maxActions: 6,
      actions: [
        { type: 'bubble', text: '喵~', duration: 3000, priority: 1 },
        { type: 'emoji', emoji: '😊', duration: 2000, priority: 1 },
        { type: 'state', state: 'idle', duration: 2000, priority: 0 },
        { type: 'move', moveTo: { x: 0.5, z: 0.5 }, duration: 2000, priority: 2 },
      ],
    },
    {
      name: 'happy', decayRate: 2, minActions: 4, maxActions: 8,
      actions: [
        { type: 'emoji', emoji: '😊', duration: 2000, priority: 1 },
        { type: 'emoji', emoji: '❤️', duration: 2000, priority: 1 },
        { type: 'bubble', text: '好开心！', duration: 3000, priority: 1 },
        { type: 'state', state: 'happy', duration: 1500, priority: 2 },
        { type: 'vfx', vfx: 'hearts', duration: 1000, priority: 3 },
        { type: 'move', moveTo: { x: 1, z: 0 }, duration: 1500, priority: 2 },
      ],
    },
    {
      name: 'sad', decayRate: 3, minActions: 2, maxActions: 4,
      actions: [
        { type: 'emoji', emoji: '😢', duration: 2500, priority: 1 },
        { type: 'bubble', text: '有点无聊...', duration: 3000, priority: 1 },
        { type: 'state', state: 'sad', duration: 2000, priority: 2 },
      ],
    },
    {
      name: 'sleepy', decayRate: 4, minActions: 1, maxActions: 3,
      actions: [
        { type: 'emoji', emoji: '💤', duration: 3000, priority: 1 },
        { type: 'state', state: 'sleep', duration: 4000, priority: 3 },
        { type: 'bubble', text: '好困...', duration: 2000, priority: 1 },
      ],
    },
    {
      name: 'excited', decayRate: 5, minActions: 3, maxActions: 6,
      actions: [
        { type: 'emoji', emoji: '✨', duration: 1500, priority: 1 },
        { type: 'emoji', emoji: '🌟', duration: 1500, priority: 1 },
        { type: 'vfx', vfx: 'stars', duration: 800, priority: 3 },
        { type: 'state', state: 'happy', duration: 1000, priority: 2 },
        { type: 'move', moveTo: { x: -0.5, z: -0.5 }, duration: 1000, priority: 2 },
      ],
    },
  ]

  setMood(mood: PetMood) {
    if (this.mood === mood) return
    this.mood = mood
    this.onMoodChange?.(mood)
  }

  modifyMood(delta: Partial<Record<PetMood, number>>) {
    for (const [key, val] of Object.entries(delta)) {
      const mood = key as PetMood
      this.moodValues[mood] = Math.max(0, Math.min(100, this.moodValues[mood] + val))
    }
    this.recalculateMood()
  }

  private recalculateMood() {
    let maxVal = 0
    let maxMood: PetMood = 'neutral'
    for (const [mood, val] of Object.entries(this.moodValues)) {
      if (val > maxVal) { maxVal = val; maxMood = mood as PetMood }
    }
    this.setMood(maxMood)
  }

  forceAction(action: BehaviorAction) {
    if (this.locked) return
    this.currentAction = action
    this.actionProgress = 0
    this.locked = true
    this.onAction?.(action)
    setTimeout(() => {
      this.locked = false
      this.currentAction = null
    }, action.duration)
  }

  pet() {
    this.forceAction({ type: 'vfx', vfx: 'hearts', duration: 1200, priority: 3 })
    this.modifyMood({ happy: 15, excited: 10 })
    if (this.fsm) this.fsm.transition('happy')
    setTimeout(() => { if (this.fsm) this.fsm.transition('idle') }, 1200)
  }

  feed() {
    this.forceAction({ type: 'bubble', text: '🍖 好吃！', duration: 2000, priority: 2 })
    this.modifyMood({ happy: 10, sleepy: 5 })
  }

  scare() { this.forceAction({ type: 'state', state: 'sad', duration: 1500, priority: 2 })
    this.modifyMood({ sad: 15, happy: -10 })
  }

  update(dt: number) {
    this.time += dt
    this.actionTimer += dt

    for (const mood of Object.keys(this.moodValues) as PetMood[]) {
      const config = this.moods.find(m => m.name === mood)
      if (config) {
        this.moodValues[mood] = Math.max(0, this.moodValues[mood] - config.decayRate * dt)
      }
    }
    this.recalculateMood()

    if (this.locked) {
      this.actionProgress += dt * 1000
      return
    }

    if (this.actionTimer >= this.nextActionTime) {
      this.actionTimer = 0
      this.nextActionTime = 5 + Math.random() * 10
      this.triggerRandomAction()
    }
  }

  private triggerRandomAction() {
    const config = this.moods.find(m => m.name === this.mood)
    if (!config || config.actions.length === 0) return

    const totalWeight = config.actions.reduce((sum, a) => sum + a.priority + 1, 0)
    let r = Math.random() * totalWeight
    for (const action of config.actions) {
      r -= action.priority + 1
      if (r <= 0) {
        this.forceAction(action)
        return
      }
    }
  }

  getCurrentMood(): PetMood { return this.mood }
  isLocked(): boolean { return this.locked }

  dispose() {
    this.currentAction = null
    this.locked = false
  }
}
