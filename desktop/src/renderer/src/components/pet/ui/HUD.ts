import * as THREE from 'three'
import { CSS2DRenderer, CSS2DObject } from 'three/examples/jsm/renderers/CSS2DRenderer.js'

export interface HUDConfig {
  target: THREE.Object3D
  offset?: THREE.Vector3
}

export class HUDSystem {
  private speechBubble: CSS2DObject | null = null
  private emotionIcon: CSS2DObject | null = null
  private statusContainer: CSS2DObject | null = null
  private target: THREE.Object3D
  private offset: THREE.Vector3
  private bubbleTimer: ReturnType<typeof setTimeout> | null = null
  private emotionTimer: ReturnType<typeof setTimeout> | null = null

  constructor(config: HUDConfig) {
    this.target = config.target
    this.offset = config.offset || new THREE.Vector3(0, 1.6, 0)
  }

  showBubble(text: string, duration = 0) {
    this.hideBubble()
    const div = document.createElement('div')
    div.textContent = text
    div.style.cssText = `
      background: rgba(255,255,255,0.95); color: #333; padding: 6px 12px;
      border-radius: 10px; font-size: 11px; max-width: 180px; line-height: 1.4;
      white-space: pre-wrap; word-break: break-word; text-align: center;
      box-shadow: 0 2px 10px rgba(0,0,0,0.1); pointer-events: none;
      font-family: 'Segoe UI', sans-serif;
    `
    this.speechBubble = new CSS2DObject(div)
    this.speechBubble.position.copy(this.offset)
    this.speechBubble.position.y += 0.3
    this.target.add(this.speechBubble)

    if (duration > 0) {
      this.bubbleTimer = setTimeout(() => this.hideBubble(), duration)
    }
  }

  hideBubble() {
    if (this.bubbleTimer) { clearTimeout(this.bubbleTimer); this.bubbleTimer = null }
    if (this.speechBubble) { this.target.remove(this.speechBubble); this.speechBubble = null }
  }

  showEmotion(emoji: string, duration = 0) {
    this.hideEmotion()
    const div = document.createElement('div')
    div.textContent = emoji
    div.style.cssText = `font-size: 24px; pointer-events: none; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.2))`
    this.emotionIcon = new CSS2DObject(div)
    this.emotionIcon.position.copy(this.offset)
    this.emotionIcon.position.y += 0.7
    this.target.add(this.emotionIcon)

    if (duration > 0) {
      this.emotionTimer = setTimeout(() => this.hideEmotion(), duration)
    }
  }

  hideEmotion() {
    if (this.emotionTimer) { clearTimeout(this.emotionTimer); this.emotionTimer = null }
    if (this.emotionIcon) { this.target.remove(this.emotionIcon); this.emotionIcon = null }
  }

  showStatusBar(hunger: number, happiness: number, energy: number) {
    this.hideStatusBar()
    const div = document.createElement('div')
    div.style.cssText = `
      display: flex; gap: 8px; padding: 4px 8px; background: rgba(0,0,0,0.4);
      border-radius: 6px; backdrop-filter: blur(4px); pointer-events: none;
    `
    const bar = (label: string, value: number, color: string) => {
      const c = document.createElement('div')
      c.style.cssText = `display: flex; align-items: center; gap: 3px; font-size: 9px; color: #eee; font-family: sans-serif;`
      const l = document.createElement('span')
      l.textContent = label; c.appendChild(l)
      const bg = document.createElement('div')
      bg.style.cssText = `width: 30px; height: 4px; background: rgba(255,255,255,0.2); border-radius: 2px; overflow: hidden;`
      const fill = document.createElement('div')
      fill.style.cssText = `width: ${Math.max(0, value)}%; height: 100%; background: ${color}; border-radius: 2px; transition: width 0.3s;`
      bg.appendChild(fill); c.appendChild(bg); div.appendChild(c)
    }
    bar('🍽', hunger, '#4CAF50')
    bar('😊', happiness, '#FF9800')
    bar('⚡', energy, '#2196F3')

    this.statusContainer = new CSS2DObject(div)
    this.statusContainer.position.copy(this.offset)
    this.statusContainer.position.y -= 0.4
    this.target.add(this.statusContainer)
  }

  hideStatusBar() {
    if (this.statusContainer) { this.target.remove(this.statusContainer); this.statusContainer = null }
  }

  dispose() {
    this.hideBubble()
    this.hideEmotion()
    this.hideStatusBar()
  }
}
