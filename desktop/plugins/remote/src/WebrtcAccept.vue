<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { newPeer, getIceServers, setCodecPreferencesH264 } from './webrtc'

const props = defineProps<{ data?: any; execute?: (a: string, args?: any) => Promise<any> }>()

const collapsed = ref(true)
const status = ref('连接中…')
const connected = ref(false)
const hasPeer = ref(false)

let pc: RTCPeerConnection | null = null
let stream: MediaStream | null = null
let pendingIce: any[] = []
let moveScheduled = false
let pendingMove: any = null
let currentDisplay: any = null
let currentSourceId = ''
let currentDataChannel: any = null

const qualityConfig = { maxWidth: 1920, maxHeight: 1080, maxFrameRate: 30 }
let cachedSources: any[] | null = null
let cachedDisplays: any[] | null = null
let cacheTime = 0
const CACHE_TTL = 5000

const win = window as any

async function getCachedSources() {
  const now = Date.now()
  if (cachedSources && now - cacheTime < CACHE_TTL) return { sources: cachedSources, displays: cachedDisplays }
  cachedSources = await win.mqbox.remote.getDesktopSources()
  cachedDisplays = await win.mqbox.remote.getAllDisplays()
  cacheTime = now
  return { sources: cachedSources, displays: cachedDisplays }
}

function matchDisplay(src: any, displays: any[]) {
  if (!src) return displays[0] || null
  return displays.find((d: any) => String(d.id) === String(src.display_id)) || displays[0] || null
}

function sendToChild(type: string, payload: any) {
  props.execute?.('sendSignal', { type, payload })
}

function cleanup() {
  if (pc) { try { pc.close() } catch {} ; pc = null }
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
  stream = null
  pendingIce = []
  currentDataChannel = null
}

async function flushMove() {
  if (!pendingMove || !currentDisplay) return
  const m = pendingMove
  pendingMove = null
  const d = currentDisplay
  const sf = d.scaleFactor || 1
  const x = Math.round((d.bounds.x + (Number(m.x) || 0) * d.bounds.width) * sf)
  const y = Math.round((d.bounds.y + (Number(m.y) || 0) * d.bounds.height) * sf)
  await win.mqbox.remote.injectInput({ type: 'mouseMove', x, y })
}

async function handleInput(ev: any) {
  try {
    if (ev.type === 'mouseMove') {
      pendingMove = ev
      if (!moveScheduled) {
        moveScheduled = true
        requestAnimationFrame(async () => {
          moveScheduled = false
          await flushMove()
        })
      }
    } else if (ev.type === 'mouseDown' || ev.type === 'mouseUp' || ev.type === 'wheel' || ev.type === 'keyDown' || ev.type === 'keyUp') {
      await win.mqbox.remote.injectInput(ev)
    }
  } catch {}
}

async function startConnection() {
  try {
    const st = await props.execute?.('getState')
    const offer = st?.hostState?.pendingOffer
    if (!offer) { status.value = '无连接请求'; return }
    pendingIce = st.hostState.pendingIce || []

    const { sources: srcList, displays: allDisplays } = await getCachedSources()
    if (!srcList.length) { status.value = '无屏幕源'; return }
    currentDisplay = matchDisplay(srcList[0], allDisplays)
    currentSourceId = srcList[0].id

    stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        mandatory: {
          chromeMediaSource: 'desktop',
          chromeMediaSourceId: srcList[0].id,
          maxFrameRate: qualityConfig.maxFrameRate,
          maxWidth: qualityConfig.maxWidth,
          maxHeight: qualityConfig.maxHeight,
        } as any,
      },
    })

    pc = newPeer(await getIceServers())

    pc.ondatachannel = (e) => {
      currentDataChannel = e.channel
      e.channel.onmessage = async (msg) => {
        try {
          const ev = JSON.parse(msg.data)
          if (ev.type === 'switchScreen') { await switchScreen(ev.sourceId); return }
          if (ev.type === 'setQuality') {
            Object.assign(qualityConfig, ev)
            const ns = await navigator.mediaDevices.getUserMedia({
              audio: false, video: { mandatory: { chromeMediaSource: 'desktop', chromeMediaSourceId: currentSourceId, maxFrameRate: qualityConfig.maxFrameRate, maxWidth: qualityConfig.maxWidth, maxHeight: qualityConfig.maxHeight } } as any,
            })
            const sender = pc?.getSenders().find((s: any) => s.track?.kind === 'video')
            if (sender && pc) await sender.replaceTrack(ns.getVideoTracks()[0])
            if (stream) stream.getTracks().forEach(t => t.stop())
            stream = ns
            return
          }
          await handleInput(ev)
        } catch {}
      }
    }

    stream.getTracks().forEach(t => pc!.addTrack(t, stream!))
    await pc.setRemoteDescription({ type: 'offer', sdp: offer.sdp })
    for (const c of pendingIce) { try { await pc.addIceCandidate(c) } catch {} }
    pendingIce = []

    const answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    sendToChild('answer', answer)

    pc.onicecandidate = (e) => {
      if (e.candidate) sendToChild('ice', e.candidate)
    }

    pc.oniceconnectionstatechange = () => {
      if (!pc) return
      const st = pc.iceConnectionState
      if (st === 'connected' || st === 'completed') {
        connected.value = true
        status.value = '推流中'
        hasPeer.value = true
      } else if (st === 'failed' || st === 'closed') {
        connected.value = false
        hasPeer.value = false
        status.value = '连接断开'
        cleanup()
        setTimeout(() => window.close(), 2000)
      }
    }

    status.value = '推流中'
    connected.value = true
    hasPeer.value = true
    props.execute?.('syncHostState', { peerConnected: true })
  } catch (e: any) {
    status.value = '连接失败: ' + (e?.message || '')
  }
}

async function switchScreen(sourceId: string) {
  try {
    const ns = await navigator.mediaDevices.getUserMedia({
      audio: false, video: { mandatory: { chromeMediaSource: 'desktop', chromeMediaSourceId: sourceId, maxFrameRate: qualityConfig.maxFrameRate, maxWidth: qualityConfig.maxWidth, maxHeight: qualityConfig.maxHeight } } as any,
    })
    const sender = pc?.getSenders().find((s: any) => s.track?.kind === 'video')
    if (sender && pc) await sender.replaceTrack(ns.getVideoTracks()[0])
    if (stream) stream.getTracks().forEach(t => t.stop())
    stream = ns
    currentSourceId = sourceId
    const { sources: srcs, displays: allDisplays } = await getCachedSources()
    currentDisplay = matchDisplay(srcs.find((s: any) => s.id === sourceId), allDisplays)
    currentDataChannel?.send(JSON.stringify({ type: 'activeScreen', id: sourceId }))
  } catch {}
}

function disconnect() {
  if (pc) { try { pc.close() } catch {} ; pc = null }
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
  stream = null
  connected.value = false
  hasPeer.value = false
  status.value = '已断开'
  props.execute?.('syncHostState', { peerConnected: false })
  setTimeout(() => window.close(), 500)
}

// --- Window drag + collapse ---
let dragStartX = 0, dragStartY = 0, dragMoved = false

function onBarMouseDown(e: MouseEvent) {
  if ((e.target as HTMLElement)?.closest?.('.close-btn, .btn-icon, .disconnect-btn')) return
  dragStartX = e.screenX
  dragStartY = e.screenY
  dragMoved = false
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragEnd)
}

function onDragMove(e: MouseEvent) {
  const dx = e.screenX - dragStartX
  const dy = e.screenY - dragStartY
  if (Math.abs(dx) > 2 || Math.abs(dy) > 2) {
    dragMoved = true
    win.mqbox?.window.move(dx, dy)
    dragStartX = e.screenX
    dragStartY = e.screenY
  }
}

function onDragEnd() {
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
  if (!dragMoved) toggleCollapse()
}

function toggleCollapse() {
  collapsed.value = !collapsed.value
  const h = collapsed.value ? 40 : 130
  win.mqbox?.window.resize(280, h)
}

function closeWindow(e: MouseEvent) {
  e.stopPropagation()
  disconnect()
}

onMounted(() => {
  startConnection()
})

onUnmounted(() => {
  cleanup()
})
</script>

<template>
  <div class="container">
    <div v-if="collapsed" class="bar" @mousedown="onBarMouseDown">
      <span class="dot" :class="{ active: connected }"></span>
      <span class="bar-text">远程控制中</span>
      <button class="close-btn" @click="closeWindow">×</button>
    </div>

    <div v-else class="panel">
      <div class="panel-hd" @mousedown="onBarMouseDown">
        <span class="panel-title">远程控制</span>
        <button class="btn-icon" @click.stop="toggleCollapse">−</button>
      </div>
      <div class="body">
        <div class="row"><span class="label">状态</span><span class="val" :class="{ ok: connected }">{{ status }}</span></div>
        <div class="row" v-if="hasPeer"><span class="label">分辨率</span><span class="val">{{ qualityConfig.maxWidth }}×{{ qualityConfig.maxHeight }}</span></div>
      </div>
      <button v-if="hasPeer" class="disconnect-btn" @click="disconnect">断开</button>
    </div>
  </div>
</template>

<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:#1a1a1a; overflow:hidden; }

.bar {
  display:flex; align-items:center; gap:6px; padding:8px 12px;
  background:#1a1a1a; cursor:pointer; user-select:none;
}
.dot { width:8px;height:8px;border-radius:50%;background:#666;flex-shrink:0; }
.dot.active { background:#28a745; }
.bar-text { flex:1; font-size:12px; color:#ccc; white-space:nowrap; }
.close-btn { width:18px;height:18px;border:none;border-radius:4px;background:transparent;color:#666;cursor:pointer;font-size:14px;line-height:1;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.close-btn:hover { background:#333;color:#fff; }

.panel { background:#1a1a1a; padding:10px; user-select:none; }
.panel-hd { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; cursor:pointer; }
.panel-title { font-size:12px; font-weight:600; color:#eee; }
.btn-icon { width:20px;height:20px;border:none;border-radius:4px;background:transparent;color:#999;cursor:pointer;font-size:14px;line-height:1; }
.btn-icon:hover { background:#333;color:#fff; }

.body { display:flex; flex-direction:column; gap:4px; margin-bottom:6px; }
.row { display:flex; justify-content:space-between; font-size:11px; }
.label { color:#888; }
.val { color:#ccc; }
.val.ok { color:#28a745; }

.disconnect-btn { width:100%; padding:5px; border:none;border-radius:6px;background:#c62828;color:#fff;font-size:11px;cursor:pointer; }
.disconnect-btn:hover { background:#e53935; }
</style>
