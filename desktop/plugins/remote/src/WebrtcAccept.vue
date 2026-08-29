<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { newPeer, getIceServers, applySenderParams } from './webrtc'

const props = defineProps<{ data?: any; execute?: (a: string, args?: any) => Promise<any> }>()
const viewerId = new URLSearchParams(window.location.search).get('viewer') || ''

const collapsed = ref(true)
const status = ref('连接中…')
const connected = ref(false)
const hasPeer = ref(false)

let pc: RTCPeerConnection | null = null
let stream: MediaStream | null = null
let pendingIce: any[] = []
let currentDisplay: any = null
let currentSourceId = ''
let currentDataChannel: any = null
let cleanupSignal: (() => void) | null = null
let bwTimer: any = null
let moveTimer: any = null
let wheelTimer: any = null
let lastWheel = 0
let hasPendingWheel = false

const qualityConfig = { maxWidth: 1280, maxHeight: 720, maxFrameRate: 30 }
const BITRATE_MIN = 300000
const BITRATE_MAX = 8000000
let currentMaxBitrate = 5000000
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
  const msg: any = { type, payload }
  if (viewerId) msg.target_deviceId = viewerId
  props.execute?.('sendSignal', msg)
}

function cleanup() {
  if (pc) { try { sendToChild('revoked', {}) } catch {} }
  if (pc) { try { pc.close() } catch {} ; pc = null }
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
  stream = null
  pendingIce = []
  if (bwTimer) { clearInterval(bwTimer); bwTimer = null }
  if (moveTimer) { clearInterval(moveTimer); moveTimer = null }
  if (wheelTimer) { clearTimeout(wheelTimer); wheelTimer = null }
  currentDataChannel = null
}

let pendingMove: { x: number; y: number } | null = null

function flushMove() {
  if (!pendingMove) return
  const p = pendingMove
  pendingMove = null
  win.mqbox.remote.injectInput({ type: 'mouseMove', x: p.x, y: p.y }).catch(() => {})
}

function flushWheel() {
  if (!hasPendingWheel) return
  hasPendingWheel = false
  win.mqbox.remote.injectInput({ type: 'wheel', deltaY: lastWheel }).catch(() => {})
}

function handleInput(ev: any) {
  try {
    if (ev.type === 'mouseMove') {
      if (!currentDisplay) return
      const d = currentDisplay
      const sf = d.scaleFactor || 1
      pendingMove = {
        x: Math.round((d.bounds.x + (Number(ev.x) || 0) * d.bounds.width) * sf),
        y: Math.round((d.bounds.y + (Number(ev.y) || 0) * d.bounds.height) * sf),
      }
      flushMove()
      if (!moveTimer) {
        moveTimer = setInterval(() => {
          flushMove()
          if (!pendingMove && !hasPendingWheel) {
            clearInterval(moveTimer)
            moveTimer = null
          }
        }, 8)
      }
    } else if (ev.type === 'wheel') {
      lastWheel = Number(ev.deltaY) || 0
      hasPendingWheel = true
      if (!wheelTimer) {
        wheelTimer = setTimeout(() => { wheelTimer = null; flushWheel() }, 16)
      }
    } else {
      win.mqbox.remote.injectInput(ev).catch(() => {})
    }
  } catch (e: any) { console.warn('[host] handleInput error:', e.message) }
}

function applyTrackSettings() {
  const sender = pc?.getSenders().find((s: any) => s.track?.kind === 'video')
  if (sender?.track) (sender.track as any).contentHint = 'detail'
  const tr = pc?.getTransceivers().find((t: any) => t.kind === 'video')
  // Keep the full frame even under load: prefer dropping framerate over
  // shrinking resolution (a shrunken image letterboxes into black bars).
  if (tr) (tr as any).degradationPreference = 'maintain-resolution'
  if (sender) {
    // Capture is native (no cropping). Scale via the encoder to a sane
    // ceiling (~1080p) while preserving the source aspect ratio.
    const sw = sender.track.getSettings?.().width || 0
    const sdb = sw > 0 ? Math.max(1, Math.ceil(sw / 1920)) : 1
    applySenderParams(sender, { maxBitrate: currentMaxBitrate, maxFramerate: qualityConfig.maxFrameRate, scaleResolutionDownBy: sdb })
  }
}

function startBandwidthMonitor() {
  clearInterval(bwTimer)
  bwTimer = setInterval(async () => {
    if (!pc) return
    try {
      const stats = await pc.getStats()
      let lost = 0, received = 0, rtt = 0
      stats.forEach((r: any) => {
        if (r.type === 'remote-inbound-rtp' && r.kind === 'video') {
          lost = r.packetsLost || 0
          received = r.packetsReceived || 0
        }
        if (r.type === 'candidate-pair' && r.state === 'succeeded') rtt = r.currentRoundTripTime || 0
      })
      const lossRate = (lost + received) > 0 ? lost / (lost + received) : 0
      let next = currentMaxBitrate
      if (lossRate > 0.03 || rtt > 0.3) next = Math.max(BITRATE_MIN, Math.round(currentMaxBitrate * 0.6))
      else if (lossRate < 0.005 && rtt < 0.15) next = Math.min(BITRATE_MAX, Math.round(currentMaxBitrate * 1.15))
      if (next !== currentMaxBitrate) {
        currentMaxBitrate = next
        const sender = pc?.getSenders().find((s: any) => s.track?.kind === 'video')
        if (sender) applySenderParams(sender, { maxBitrate: next })
      }
    } catch {}
  }, 2000)
}

function handleIce(m: any) {
  if (!pc) return
  if (!pc.remoteDescription) { pendingIce.push(m.payload); return }
  const ufrag = pc.localDescription?.sdp?.match(/a=ice-ufrag:(\S+)/)?.[1]
  if (m.payload?.usernameFragment && m.payload.usernameFragment === ufrag) return
  try { pc.addIceCandidate(m.payload) } catch { /* ignore */ }
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
        } as any,
      },
    })

    pc = newPeer(await getIceServers())

    pc.ondatachannel = (e) => {
      currentDataChannel = e.channel
      e.channel.onopen = () => {
        const { sources } = cachedSources ? { sources: cachedSources } : { sources: [] }
        e.channel.send(JSON.stringify({ type: 'screens', list: sources.map((s: any) => ({ id: s.id, name: s.name })) }))
      }
      e.channel.onmessage = (msg) => {
        try {
          const ev = JSON.parse(msg.data)
          if (ev.type === 'ping') { try { e.channel.send(JSON.stringify({ type: 'pong' })) } catch {}; return }
          if (ev.type === 'switchScreen') { switchScreen(ev.sourceId); return }
          if (ev.type === 'setQuality') { Object.assign(qualityConfig, ev); applyQualityChange(); return }
          handleInput(ev)
        } catch (e: any) { console.warn('[host] dc message error:', e.message) }
      }
    }

    // Standard WebRTC flow
    pc.onicecandidate = (e) => {
      if (e.candidate) {
        sendToChild('ice', e.candidate.toJSON())
      }
    }

    await pc.setRemoteDescription({ type: 'offer', sdp: offer.sdp })

    // Use addTrack to properly associate the track with a stream
    stream.getTracks().forEach(t => pc!.addTrack(t, stream!))

    const answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    sendToChild('answer', answer)

    // Drain ICE candidates that arrived before this window opened
    const localUfrag = pc.localDescription?.sdp?.match(/a=ice-ufrag:(\S+)/)?.[1]
    for (let i = 0; i < pendingIce.length; i++) {
      const ufrag = pendingIce[i]?.usernameFragment
      if (ufrag && ufrag === localUfrag) continue
      try { await pc.addIceCandidate(pendingIce[i]) }
      catch {}
    }
    pendingIce = []

    pc.oniceconnectionstatechange = () => {
      if (!pc) return
      const st = pc.iceConnectionState
      console.log('[host] ICE state:', st)
      if (st === 'connected' || st === 'completed') {
        connected.value = true
        status.value = '推流中'
        hasPeer.value = true
        applyTrackSettings()
        startBandwidthMonitor()
      } else if (st === 'failed') {
        connected.value = false
        hasPeer.value = false
        status.value = '连接断开'
        setTimeout(() => { cleanup(); window.close() }, 5000)
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
  if (sourceId === currentSourceId) return
  try {
    const ns = await navigator.mediaDevices.getUserMedia({
      audio: false, video: { mandatory: { chromeMediaSource: 'desktop', chromeMediaSourceId: sourceId, maxFrameRate: qualityConfig.maxFrameRate } } as any,
    })
    const sender = pc?.getSenders().find((s: any) => s.track?.kind === 'video')
    if (sender && pc) await sender.replaceTrack(ns.getVideoTracks()[0])
    if (stream) stream.getTracks().forEach(t => t.stop())
    stream = ns
    currentSourceId = sourceId
    applyTrackSettings()
    const { sources: srcs, displays: allDisplays } = await getCachedSources()
    currentDisplay = matchDisplay(srcs.find((s: any) => s.id === sourceId), allDisplays)
    currentDataChannel?.send(JSON.stringify({ type: 'activeScreen', id: sourceId }))
  } catch (e: any) { console.warn('[host] switchScreen error:', e.message) }
}

function applyQualityChange() {
  navigator.mediaDevices.getUserMedia({
    audio: false, video: { mandatory: { chromeMediaSource: 'desktop', chromeMediaSourceId: currentSourceId, maxFrameRate: qualityConfig.maxFrameRate } } as any,
  }).then(ns => {
    const sender = pc?.getSenders().find((s: any) => s.track?.kind === 'video')
    if (sender && pc) sender.replaceTrack(ns.getVideoTracks()[0])
    if (stream) stream.getTracks().forEach(t => t.stop())
    stream = ns
    applyTrackSettings()
  }).catch(() => {})
}

function disconnect() {
  sendToChild('revoked', {})
  if (bwTimer) { clearInterval(bwTimer); bwTimer = null }
  if (moveTimer) { clearInterval(moveTimer); moveTimer = null }
  if (wheelTimer) { clearTimeout(wheelTimer); wheelTimer = null }
  if (pc) { try { pc.close() } catch {} ; pc = null }
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
  stream = null
  connected.value = false
  hasPeer.value = false
  status.value = '已断开'
  props.execute?.('syncHostState', { peerConnected: false })
  setTimeout(() => window.close(), 500)
}

// --- Window collapse ---

function toggleCollapse() {
  collapsed.value = !collapsed.value
  const h = collapsed.value ? 40 : 130
  win.mqbox?.window?.resize(280, h)
}

function closeWindow(e: MouseEvent) {
  e.stopPropagation()
  disconnect()
}

onMounted(() => {
  win.mqbox?.window?.resize(280, 40)
  startConnection()
  window.addEventListener('beforeunload', () => { if (pc) sendToChild('revoked', {}) })
  const rm = win.mqbox?.remote?.onSignal?.(function(m: any) {
    if (m.type === 'ice') { handleIce(m); return }
    if (m.type === 'revoked' || m.type === 'error') {
      cleanup()
      window.close()
    }
  })
  cleanupSignal = typeof rm === 'function' ? rm : null
})

onUnmounted(() => {
  if (cleanupSignal) { cleanupSignal(); cleanupSignal = null }
  cleanup()
})
</script>

<template>
  <div class="container">
    <div v-if="collapsed" class="bar">
      <span class="dot" :class="{ active: connected }" @click="toggleCollapse"></span>
      <span class="bar-text">远程控制中</span>
      <button class="close-btn" @click="closeWindow">×</button>
    </div>

    <div v-else class="panel">
      <div class="panel-hd">
        <span class="dot" :class="{ active: connected }"></span>
        <span class="panel-title" @click="toggleCollapse">远程控制中</span>
        <button class="btn-icon" @click="toggleCollapse">−</button>
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
  display:flex; align-items:center; gap:6px; padding:0 12px;
  background:#1a1a1a; cursor:pointer; user-select:none; height:40px; -webkit-app-region:drag;
}
.dot { width:8px;height:8px;border-radius:50%;background:#666;flex-shrink:0; -webkit-app-region:no-drag; cursor:pointer; }
.dot.active { background:#28a745; }
.bar-text { flex:1; font-size:12px; color:#ccc; white-space:nowrap; line-height:1; }
.close-btn { width:18px;height:18px;border:none;border-radius:4px;background:transparent;color:#666;cursor:pointer;font-size:14px;line-height:1;display:flex;align-items:center;justify-content:center;flex-shrink:0; -webkit-app-region:no-drag; }
.close-btn:hover { background:#333;color:#fff; }

.panel { background:#1a1a1a; user-select:none; -webkit-app-region:drag; }
.panel-hd { display:flex; align-items:center; gap:6px; padding:0 12px; height:40px; }
.panel-title { flex:1; font-size:12px; font-weight:600; color:#ccc; line-height:1; -webkit-app-region:no-drag; cursor:pointer; }
.btn-icon { width:20px;height:20px;border:none;border-radius:4px;background:transparent;color:#999;cursor:pointer;font-size:14px;line-height:1; -webkit-app-region:no-drag; }
.btn-icon:hover { background:#333;color:#fff; }

.body { padding:0 12px 8px; display:flex; flex-direction:column; gap:4px; -webkit-app-region:no-drag; }
.row { display:flex; justify-content:space-between; font-size:11px; }
.label { color:#888; }
.val { color:#ccc; }
.val.ok { color:#28a745; }

.disconnect-btn { margin:0 12px 8px; width:calc(100% - 24px); padding:5px; border:none;border-radius:6px;background:#c62828;color:#fff;font-size:11px;cursor:pointer; -webkit-app-region:no-drag; }
.disconnect-btn:hover { background:#e53935; }
</style>
