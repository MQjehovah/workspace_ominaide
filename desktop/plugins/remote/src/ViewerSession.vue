<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { openSignal, newPeer, getServer, getAuthHeaders, getIceServers } from './webrtc'

const props = defineProps<{ data?:any; execute?:(a:string,args?:any)=>Promise<any>; refresh?:()=>void; close?:()=>void; room?:string }>()
const videoRef = ref<HTMLVideoElement|null>(null)
const status = ref('')
const connected = ref(false)
const screens = ref<any[]>([])
const activeScreenId = ref('')

let ws: WebSocket | null = null
let pc: RTCPeerConnection | null = null
let dc: RTCDataChannel | null = null
let pendingIce: any[] = []
let connectionEnded = false
let cachedNorm: { cw: number; ch: number; vw: number; vh: number; scale: number; rw: number; rh: number; ox: number; oy: number } | null = null
function invalidateNormCache() { cachedNorm = null }

async function connect(roomId: string) {
  connectionEnded = false
  if (ws || pc) {
    cleanup()
    if (ws) { try { ws.close() } catch {} ; ws = null }
  }
  status.value = '连接中…'
  try {
    ws = await openSignal(roomId, onSignal)
    ws.onclose = () => { if (!connectionEnded) status.value = '信令断开'; cleanup() }
    ws.onerror = () => { status.value = '信令错误' }
    pc = newPeer(await getIceServers())
    ws.send(JSON.stringify({ type: 'requestControl', target_id: roomId, name: 'OmniAide 桌面端' }))
    status.value = '等待被控端授权…'
  } catch (e: any) {
    status.value = e?.message || String(e)
    cleanup()
    if (ws) { try { ws.close() } catch {} ; ws = null }
  }
}

function determineQuality() {
  const el = videoRef.value
  if (!el) return
  const w = el.clientWidth, h = el.clientHeight
  let maxWidth = 1920, maxHeight = 1080, maxFrameRate = 30
  if (w <= 800 || h <= 600) { maxWidth = 800; maxHeight = 600; maxFrameRate = 15 }
  else if (w <= 1280 || h <= 720) { maxWidth = 1280; maxHeight = 720; maxFrameRate = 24 }
  sendInput({ type: 'setQuality', maxWidth, maxHeight, maxFrameRate })
}

async function startOffering() {
  if (!pc || !ws) return
  dc = pc.createDataChannel('input')
  dc.onopen = () => determineQuality()
  dc.onmessage = (msg) => {
    try {
      const ev = JSON.parse(msg.data)
      if (ev.type === 'screens') { screens.value = ev.list || []; return }
      if (ev.type === 'activeScreen') { activeScreenId.value = ev.id; return }
    } catch {}
  }
  pc.addTransceiver('video', { direction: 'recvonly' })
  pc.ontrack = (e) => {
    if (videoRef.value) videoRef.value.srcObject = e.streams[0]
    status.value = '已连接（可控制）'
    connected.value = true
    setTimeout(() => determineQuality(), 500)
  }
  pc.onicecandidate = (e) => { if (e.candidate) ws!.send(JSON.stringify({ type: 'ice', payload: e.candidate })) }
  pc.oniceconnectionstatechange = () => {
    if (!pc) return
    const st = pc.iceConnectionState
    if (st === 'failed') { if (!connectionEnded) status.value = '连接失败（ICE）'; connected.value = false; cleanup() }
    else if (st === 'disconnected') { if (!connectionEnded) status.value = '连接中断，尝试恢复…' }
    else if (st === 'closed') { connected.value = false }
  }
  const offer = await pc.createOffer()
  await pc.setLocalDescription(offer)
  ws.send(JSON.stringify({ type: 'offer', payload: offer }))
  status.value = '等待画面…'
}

async function onSignal(m: any) {
  if (m.type === 'controlAllowed') {
    await startOffering()
  } else if (m.type === 'controlDenied') {
    connectionEnded = true
    status.value = m.reason === 'busy' ? '被控端忙（已有连接）' : '被控端拒绝'
    cleanup()
    if (ws) { try { ws.close() } catch {} ; ws = null }
  } else if (m.type === 'revoked') {
    connectionEnded = true
    status.value = '被控端断开了控制'
    cleanup()
  } else if (m.type === 'answer' && pc) {
    try {
      await pc.setRemoteDescription({ type: 'answer', sdp: m.payload.sdp })
      for (const c of pendingIce) { try { await pc.addIceCandidate(c) } catch {} }
      pendingIce = []
    } catch (e: any) { status.value = '连接失败: ' + (e?.message || e) }
  } else if (m.type === 'ice') {
    if (pc && pc.remoteDescription) { try { await pc.addIceCandidate(m.payload) } catch {} }
    else pendingIce.push(m.payload)
  } else if (m.type === 'error') {
    status.value = '被控端错误: ' + (m.message || '未知')
  }
}

function switchScreen(sourceId: string) {
  if (dc && dc.readyState === 'open') { try { dc.send(JSON.stringify({type:'switchScreen',sourceId})) } catch {} }
}

function sendInput(ev: any) {
  if (dc && dc.readyState === 'open') {
    try { dc.send(JSON.stringify(ev)) } catch {}
  }
}

function normVideo(e: MouseEvent) {
  const el = e.currentTarget as HTMLVideoElement
  const cw = el.clientWidth, ch = el.clientHeight
  const vw = el.videoWidth || cw, vh = el.videoHeight || ch
  if (cachedNorm && cachedNorm.cw === cw && cachedNorm.ch === ch && cachedNorm.vw === vw && cachedNorm.vh === vh) {
    const x = cachedNorm.rw > 0 ? (e.offsetX - cachedNorm.ox) / cachedNorm.rw : 0
    const y = cachedNorm.rh > 0 ? (e.offsetY - cachedNorm.oy) / cachedNorm.rh : 0
    return { x: Math.max(0, Math.min(1, x)), y: Math.max(0, Math.min(1, y)) }
  }
  const scale = Math.min(cw / vw, ch / vh)
  const rw = vw * scale, rh = vh * scale
  const ox = (cw - rw) / 2, oy = (ch - rh) / 2
  cachedNorm = { cw, ch, vw, vh, scale, rw, rh, ox, oy }
  const x = rw > 0 ? (e.offsetX - ox) / rw : 0
  const y = rh > 0 ? (e.offsetY - oy) / rh : 0
  return { x: Math.max(0, Math.min(1, x)), y: Math.max(0, Math.min(1, y)) }
}

function onMouseMove(e: MouseEvent) {
  const { x, y } = normVideo(e)
  sendInput({ type: 'mouseMove', x, y })
}

function onMouseDown(e: MouseEvent) {
  const button = e.button === 2 ? 'right' : e.button === 1 ? 'middle' : 'left'
  sendInput({ type: 'mouseDown', button })
}

function onMouseUp(e: MouseEvent) {
  const button = e.button === 2 ? 'right' : e.button === 1 ? 'middle' : 'left'
  sendInput({ type: 'mouseUp', button })
}

function onWheel(e: WheelEvent) {
  e.preventDefault()
  sendInput({ type: 'wheel', deltaY: e.deltaY })
}

function isIgnoredKey(code: string): boolean {
  return code === 'F5' || code === 'F11' || code === 'F12'
}

function onKeyDown(e: KeyboardEvent) {
  if (!connected.value) return
  if (e.code && !isIgnoredKey(e.code)) {
    e.preventDefault()
    sendInput({ type: 'keyDown', code: e.code })
  }
}

function onKeyUp(e: KeyboardEvent) {
  if (!connected.value) return
  if (e.code && !isIgnoredKey(e.code)) {
    e.preventDefault()
    sendInput({ type: 'keyUp', code: e.code })
  }
}

function cleanup() {
  connected.value = false
  if (dc) { try { dc.close() } catch {} ; dc = null }
  if (pc) { try { pc.close() } catch {} ; pc = null }
  pendingIce = []
  if (videoRef.value) videoRef.value.srcObject = null
}

function backToMenu() {
  connectionEnded = false
  cleanup()
  if (ws) { try { ws.close() } catch {} ; ws = null }
  props.close?.()
}

onMounted(() => {
  if (props.room && props.room !== 'undefined' && props.room !== '') connect(props.room)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
  window.removeEventListener('resize', invalidateNormCache)
  cleanup()
  if (ws) { try { ws.close() } catch {} ; ws = null }
})
</script>

<template>
  <div class="viewer" tabindex="0">
    <div class="toolbar" v-if="screens.length > 1">
      <button v-for="s in screens" :key="s.id" class="screen-btn" :class="{ active: s.id === activeScreenId }" @click="switchScreen(s.id)">{{ s.name }}</button>
    </div>
    <video ref="videoRef" autoplay playsinline class="video"
      @mousemove="onMouseMove" @mousedown="onMouseDown" @mouseup="onMouseUp"
      @wheel.prevent="onWheel" @contextmenu.prevent></video>
    <p v-if="status" class="status">{{ status }}</p>
  </div>
</template>

<style scoped>
.viewer { height:100vh; background:#212529; display:flex; flex-direction:column; position:relative; }
.toolbar { display:flex; gap:4px; padding:6px 12px; background:rgba(0,0,0,.4); justify-content:center; flex-shrink:0; }
.screen-btn { padding:4px 10px; border-radius:4px; border:none; background:rgba(255,255,255,.1); color:#fff; font-size:11px; cursor:pointer; }
.screen-btn.active { background:#e91e63; color:#fff; }
.screen-btn:hover { background:rgba(255,255,255,.2); }
.video { flex:1; object-fit:contain; }
.status { position:fixed; top:12px; left:50%; transform:translateX(-50%); margin:0; padding:6px 14px; background:rgba(0,0,0,.6); color:#fff; font-size:12px; border-radius:16px; z-index:10; }
</style>
