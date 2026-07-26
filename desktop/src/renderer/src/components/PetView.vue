<template>
  <div class="pet-wrap" ref="container"
    @dragover.prevent="onDragOver" @dragleave="onDragLeave" @drop.prevent="onDrop">
    <div v-if="dropActive" class="drop-zone">📂 放下文件</div>

    <!-- Side panel -->
    <div v-if="panel.show" class="side-panel" :class="{ active: panel.show }">
      <div class="panel-hd">
        <span class="panel-title">✨ 桌宠</span>
        <button class="panel-close" @click="panel.show = false">✕</button>
      </div>
      <div class="panel-body">
        <button class="panel-btn" @click="doAction('pet')">✋ 摸头</button>
        <button class="panel-btn" @click="doAction('feed')">🍎 喂食</button>
        <button class="panel-btn" @click="doAction('chat')">💬 聊天</button>
        <button class="panel-btn" @click="doAction('work')">💻 工作</button>
        <button class="panel-btn" @click="doAction('sleep')">💤 睡觉</button>
        <button class="panel-btn" @click="doAction('mood')">😊 换心情</button>
        <button class="panel-btn" @click="doAction('close')">✕ 隐藏</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

const container = ref<HTMLDivElement>()
const dropActive = ref(false)
const panel = ref({ show: false, x: 0, y: 0 })

// === Three.js ===
let scene: THREE.Scene, camera: THREE.PerspectiveCamera, renderer: THREE.WebGLRenderer
let clock = new THREE.Clock(), animId = 0, time = 0
let modelRoot: THREE.Object3D | null = null
let shadow: THREE.Mesh
let bubbleEl: HTMLElement, emotionEl: HTMLElement

// === State ===
type State = 'idle' | 'wake' | 'happy' | 'sad' | 'sleep' | 'work'
let currentState: State = 'idle'
let stateTimer = 0

// === Proximity ===
let globalMX = 0, globalMY = 0
let windowBounds = { x: 0, y: 0, w: 280, h: 340 }
let proximity = 0 // 0=hidden, 1=visible
let awayTimer = 0
const PROXIMITY_RADIUS = 100 // px from window edge to trigger wake
const AWAY_TIMEOUT = 3 // seconds before hiding

const MODEL_URLS = [
  'https://threejs.org/examples/models/gltf/RobotExpressive/RobotExpressive.gltf',
  'https://threejs.org/examples/models/gltf/Xbot.glb',
]
const ANIM_MAP: Record<string, State> = {
  'Idle': 'idle', 'idle': 'idle',
  'Walking': 'wake', 'Walk': 'wake',
  'Happy': 'happy', 'Jump': 'happy',
  'Sad': 'sad', 'Sad': 'sad',
  'Sleep': 'sleep', 'Sleeping': 'sleep', 'sleep': 'sleep',
}

async function init() {
  const el = container.value!
  const w = el.clientWidth || 280, h = el.clientHeight || 340

  scene = new THREE.Scene()
  camera = new THREE.PerspectiveCamera(35, w / h, 0.1, 20)
  camera.position.set(0, 1.8, 3.8); camera.lookAt(0, 0.4, 0)

  renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true })
  renderer.setSize(w, h); renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
  renderer.shadowMap.enabled = true; renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 0.7
  el.prepend(renderer.domElement)

  // Lights
  scene.add(new THREE.HemisphereLight(0x8888ff, 0x444422, 0.4))
  const sun = new THREE.DirectionalLight(0xffeedd, 0.8)
  sun.position.set(2, 4, 3); sun.castShadow = true
  sun.shadow.mapSize.set(512, 512)
  scene.add(sun)
  scene.add(new THREE.DirectionalLight(0x8888ff, 0.2).position.set(-2, 1, -3))

  // Ground
  const ground = new THREE.Mesh(new THREE.CircleGeometry(1.2, 24),
    new THREE.MeshStandardMaterial({ color: 0x6C5B4B, roughness: 0.8 }))
  ground.rotation.x = -Math.PI / 2; ground.position.y = -0.02; ground.receiveShadow = true
  scene.add(ground)

  // Shadow
  shadow = new THREE.Mesh(new THREE.CircleGeometry(0.35, 12),
    new THREE.MeshBasicMaterial({ color: 0, transparent: true, opacity: 0.1, depthWrite: false }))
  shadow.rotation.x = -Math.PI / 2; shadow.position.y = 0.001
  scene.add(shadow)

  // Load model
  const loader = new GLTFLoader()
  for (const url of MODEL_URLS) {
    try {
      const gltf = await new Promise<any>((resolve, reject) =>
        loader.load(url, resolve, undefined, () => reject(new Error('fail'))))
      const m = gltf.scene
      m.scale.set(0.5, 0.5, 0.5); m.position.y = 0
      m.traverse(c => { if (c instanceof THREE.Mesh) { c.castShadow = true; c.receiveShadow = true } })
      scene.add(m); modelRoot = m
      if (gltf.animations?.length) {
        const mixer = new THREE.AnimationMixer(m)
        const first = gltf.animations[0]
        const action = mixer.clipAction(first)
        action.play()
      }
      break
    } catch {}
  }
  if (!modelRoot) modelRoot = buildProcedural()

  // Bubble & emotion
  bubbleEl = document.createElement('div')
  bubbleEl.style.cssText = 'position:absolute;top:8px;left:50%;transform:translateX(-50%);background:rgba(255,255,255,0.95);color:#333;padding:6px 12px;border-radius:10px;font-size:11px;max-width:200px;text-align:center;box-shadow:0 2px 10px rgba(0,0,0,0.1);pointer-events:none;z-index:10;opacity:0;transition:opacity 0.3s;font-family:sans-serif;'
  el.appendChild(bubbleEl)
  emotionEl = document.createElement('div')
  emotionEl.style.cssText = 'position:absolute;top:40px;left:50%;transform:translateX(-50%);font-size:22px;pointer-events:none;z-index:11;opacity:0;transition:opacity 0.3s;'
  el.appendChild(emotionEl)

  function showBubble(t: string, d = 0) {
    bubbleEl.textContent = t; bubbleEl.style.opacity = '1'
    if (d) setTimeout(() => { if (bubbleEl.textContent === t) bubbleEl.style.opacity = '0' }, d)
  }
  function showEmoji(e: string, d = 0) {
    emotionEl.textContent = e; emotionEl.style.opacity = '1'
    if (d) setTimeout(() => { if (emotionEl.textContent === e) emotionEl.style.opacity = '0' }, d)
  }

  // Proximity & mouse tracking
  const mqbox = (window as any).mqbox
  if (mqbox?.mouse?.getPosition) {
    setInterval(async () => {
      try {
        const p = await mqbox.mouse.getPosition()
        if (p) { globalMX = p.x; globalMY = p.y }
      } catch {}
    }, 50)
  }
  if (mqbox?.window?.getBounds) {
    const updateBounds = async () => {
      try {
        const b = await mqbox.window.getBounds()
        if (b) windowBounds = { x: b.x, y: b.y, w: b.width, h: b.height }
      } catch {}
    }
    updateBounds(); setInterval(updateBounds, 1000)
  }

  // Welcome
  setTimeout(() => { showBubble('鼠标靠近我 🐾', 3000); showEmoji('😊', 2000) }, 300)

  // === Render loop ===
  const loop = () => {
    animId = requestAnimationFrame(loop)
    const dt = Math.min(clock.getDelta(), 0.05)
    time += dt; stateTimer += dt

    // Proximity calculation
    const cx = windowBounds.x + windowBounds.w / 2
    const cy = windowBounds.y + windowBounds.h / 2
    const dist = Math.sqrt((globalMX - cx) ** 2 + (globalMY - cy) ** 2)
    const nearEdge = dist < PROXIMITY_RADIUS + Math.max(windowBounds.w, windowBounds.h) / 2

    if (nearEdge && currentState !== 'wake') {
      changeState('wake')
      awayTimer = 0
    } else if (!nearEdge && currentState === 'wake') {
      awayTimer += dt
      if (awayTimer > AWAY_TIMEOUT) changeState('idle')
    }

    // Container opacity based on state
    el.style.opacity = String(currentState === 'idle' ? 0.3 : 1)

    // State FSM
    updateFSM(dt)

    // Shadow
    if (modelRoot) {
      shadow.position.x = modelRoot.position.x
      shadow.position.z = modelRoot.position.z
    }

    renderer.render(scene, camera)
  }
  loop()
}

function changeState(s: State) {
  if (s === currentState) return
  const prev = currentState
  currentState = s; stateTimer = 0
  if (s === 'wake' && prev === 'idle') {
    showEmoji('✨', 1500)
  }
  if (s === 'sleep') showEmoji('💤', 3000)
  if (s === 'happy') showEmoji('😊', 1500)
}

function updateFSM(dt: number) {
  if (!modelRoot) return
  switch (currentState) {
    case 'idle':
      modelRoot.position.y = 0
      modelRoot.scale.setScalar(0.5)
      break
    case 'wake':
      modelRoot.position.y = Math.sin(time * 1.5) * 0.02
      modelRoot.rotation.y += (Math.sin(time * 0.5) * 0.3 - modelRoot.rotation.y) * 0.05
      if (!nearEdge()) setTimeout(() => changeState('idle'), 3000)
      break
    case 'happy':
      modelRoot.position.y = Math.sin(time * 6) * 0.04
      if (stateTimer > 1.5) changeState('wake')
      break
    case 'sleep':
      modelRoot.rotation.x = 0.3
      modelRoot.position.y = -0.02
      break
    case 'sad':
      modelRoot.position.y = -Math.abs(Math.sin(time * 2)) * 0.015
      if (stateTimer > 2) changeState('wake')
      break
    case 'work':
      modelRoot.rotation.y += dt * 2
      break
  }
}

function nearEdge(): boolean {
  const cx = windowBounds.x + windowBounds.w / 2
  const cy = windowBounds.y + windowBounds.h / 2
  const dist = Math.sqrt((globalMX - cx) ** 2 + (globalMY - cy) ** 2)
  return dist < PROXIMITY_RADIUS + Math.max(windowBounds.w, windowBounds.h) / 2
}

let dragCount = 0
function onDragOver() { dropActive.value = true; dragCount++; changeState('wake') }
function onDragLeave() { dragCount--; if (dragCount <= 0) { dragCount = 0; dropActive.value = false } }
function onDrop(e: DragEvent) {
  dragCount = 0; dropActive.value = false
  changeState('happy')
  const files = e.dataTransfer?.files
  if (!files || files.length === 0) return
  for (const f of Array.from(files)) {
    bubbleEl.textContent = `📎 ${f.name}`; bubbleEl.style.opacity = '1'
    setTimeout(() => { bubbleEl.style.opacity = '0' }, 2000)
    const path = (f as any).path
    if (path) (window as any).mqbox?.shell?.moveToTrash(path)
      .then((r: any) => { bubbleEl.textContent = r?.success ? '已移到回收站 ♻️' : '删除失败'; bubbleEl.style.opacity = '1'; setTimeout(() => bubbleEl.style.opacity = '0', 2000) })
      .catch(() => {})
  }
}

function doAction(a: string) {
  panel.value.show = false
  switch (a) {
    case 'pet': changeState('happy'); break
    case 'feed': bubbleEl.textContent = '🍎 好吃！'; bubbleEl.style.opacity = '1'; setTimeout(() => bubbleEl.style.opacity = '0', 2000); changeState('happy'); break
    case 'chat': doChat(); break
    case 'work': changeState('work'); bubbleEl.textContent = '💻 工作中'; bubbleEl.style.opacity = '1'; setTimeout(() => bubbleEl.style.opacity = '0', 2000); break
    case 'sleep': changeState('sleep'); break
    case 'mood': changeState(['happy', 'sad', 'sleep'][Math.floor(Math.random() * 3)] as State); break
    case 'close': (window as any).mqbox?.window?.hide(); break
  }
}

async function doChat() {
  bubbleEl.textContent = '让我想想...'; bubbleEl.style.opacity = '1'
  try {
    const cfg = JSON.parse(localStorage.getItem('ai_chat_config') || '{}')
    const msg = ['心情怎么样？', '讲个笑话', '你在干什么？'][Math.floor(Math.random() * 3)]
    let reply: string
    if (cfg.mode === 'backend') {
      const token = await (window as any).mqbox?.config?.get('token') || ''
      const su = await (window as any).mqbox?.config?.get('serverUrl') || 'http://localhost:8000'
      const r = await fetch(`${su}/api/chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
        body: JSON.stringify({ message: msg, history: [] }),
      })
      const data = await r.json()
      reply = data.reply || data.response || `喵`
    } else reply = `喵~ ${msg}`
    bubbleEl.textContent = reply; setTimeout(() => bubbleEl.style.opacity = '0', 4000)
  } catch { bubbleEl.textContent = '网络不太好...'; setTimeout(() => bubbleEl.style.opacity = '0', 2000) }
}

function buildProcedural(): THREE.Group {
  const g = new THREE.Group()
  const bm = new THREE.MeshStandardMaterial({ color: 0x6C63FF, roughness: 0.25 })
  const body = new THREE.Mesh(new THREE.SphereGeometry(0.3, 16, 16), bm)
  body.position.y = 0.35; g.add(body)
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.18, 16, 16), bm)
  head.position.set(0, 0.56, 0.04); g.add(head)
  ;[-0.06, 0.06].forEach(x => {
    const w = new THREE.Mesh(new THREE.SphereGeometry(0.05, 8, 8), new THREE.MeshStandardMaterial({ color: 0xffffff }))
    w.position.set(x, 0.6, 0.22); g.add(w)
    const p = new THREE.Mesh(new THREE.SphereGeometry(0.025, 6, 6), new THREE.MeshStandardMaterial({ color: 0x1a1a2e }))
    p.position.set(x, 0.595, 0.25); g.add(p)
  })
  return g
}

onMounted(() => init())
onUnmounted(() => { cancelAnimationFrame(animId); renderer?.dispose() })
</script>

<style>
*{margin:0;padding:0;box-sizing:border-box;user-select:none}
.pet-wrap{width:100vw;height:100vh;position:relative;overflow:hidden;background:transparent;-webkit-app-region:drag;transition:opacity 0.5s}
canvas{display:block;-webkit-app-region:no-drag}

.drop-zone{position:absolute;inset:8px;border:2px dashed rgba(68,255,136,0.5);border-radius:14px;background:rgba(68,255,136,0.06);display:flex;align-items:center;justify-content:center;font-size:14px;color:rgba(68,255,136,0.7);z-index:50;pointer-events:none;backdrop-filter:blur(3px);-webkit-app-region:no-drag}

.side-panel{position:absolute;left:-180px;top:0;width:180px;height:100%;background:rgba(255,255,255,0.92);backdrop-filter:blur(12px);border-right:1px solid rgba(0,0,0,0.06);z-index:100;transition:transform 0.25s ease;transform:translateX(0);-webkit-app-region:no-drag}
.side-panel:not(.active){transform:translateX(100%)}
.panel-hd{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;border-bottom:1px solid #eee}
.panel-title{font-size:13px;font-weight:600;color:#333}
.panel-close{width:22px;height:22px;border:none;border-radius:5px;background:transparent;cursor:pointer;font-size:14px;color:#999;display:flex;align-items:center;justify-content:center}
.panel-close:hover{background:#f0f0f0;color:#333}
.panel-body{display:flex;flex-direction:column;gap:4px;padding:10px}
.panel-btn{padding:9px 12px;border:none;border-radius:8px;background:transparent;color:#444;font-size:12px;cursor:pointer;text-align:left;display:flex;align-items:center;gap:8px}
.panel-btn:hover{background:#f0f4ff;color:#333}
</style>
