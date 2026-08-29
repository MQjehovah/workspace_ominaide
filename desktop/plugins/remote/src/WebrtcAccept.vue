<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { newPeer, getIceServers, applySenderParams } from './webrtc'

const props = defineProps<{ data?: any; execute?: (a: string, args?: any) => Promise<any> }>()
const viewerId = new URLSearchParams(window.location.search).get('viewer') || ''

const collapsed = ref(true)
const status = ref('连接中…')
const connected = ref(false)
const hasPeer = ref(false)
const fileProgress = ref<{ name: string; percent: number; dir: 'in' | 'out' } | null>(null)

let pc: RTCPeerConnection | null = null
let stream: MediaStream | null = null
let pendingIce: any[] = []
let currentDisplay: any = null
let currentSourceId = ''
let currentDataChannel: any = null
let fileChannel: any = null
let cleanupSignal: (() => void) | null = null
let bwTimer: any = null
let moveTimer: any = null
let wheelTimer: any = null
let lastWheel = 0
let hasPendingWheel = false
let clipboardTimer: any = null
let lastLocalClipboard = ''
let lastRemoteClipboard = ''

const qualityConfig = { maxWidth: 1280, maxHeight: 720, maxFrameRate: 30 }
const dispQuality = ref('720p')
let currentMaxBitrate = 4000000
let prevFramesEncoded = 0
let hasPrevFrames = false
let currentTierIndex = 1
let lastDir = 0
let dirSamples = 0
let lastTierChangeAt = 0
let staticFpsActive = false
let qualityLocked = false
let qualityLockHeight = 720
let qualityLockFps = 30
let lastInputAt = 0
let lastFrameSample = 0
let framesFrozen = 0
let lastReinitAt = 0
const TIER_COOLDOWN_MS = 10000
const UPGRADE_SAMPLES = 3
const DOWNGRADE_SAMPLES = 1
const STATIC_IDLE_MS = 5000
const TIERS = [
  { label: '540p', height: 540, bitrate: 2500000 },
  { label: '720p', height: 720, bitrate: 4000000 },
  { label: '1080p', height: 1080, bitrate: 6000000 },
]
const FILE_CHUNK = 64 * 1024
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
  if (clipboardTimer) { clearInterval(clipboardTimer); clipboardTimer = null }
  currentDataChannel = null
  fileChannel = null
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

/** Any viewer input wakes the stream from static (low-fps) mode. */
function kick() {
  lastInputAt = Date.now()
  if (staticFpsActive) {
    staticFpsActive = false
    if (!qualityLocked) applyTrackSettings(TIERS[currentTierIndex].height, 30)
  }
}

/** Watch for capture track mute/unmute (screen lock pauses desktop capture). */
function attachTrackEvents(track: any) {
  try {
    track.addEventListener('mute', () => {})
    track.addEventListener('unmute', () => {
      if (Date.now() - lastReinitAt < 3000) return
      lastReinitAt = Date.now()
      reinitCapture()
    })
  } catch {}
}

function handleInput(ev: any) {
  kick()
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

function physicalSourceWidth(): number {
  if (currentDisplay?.bounds?.width && currentDisplay?.scaleFactor) {
    return Math.round(currentDisplay.bounds.width * currentDisplay.scaleFactor)
  }
  const sender = pc?.getSenders().find((s: any) => s.track?.kind === 'video')
  return sender?.track?.getSettings?.()?.width || 1280
}

/** Smooth quality control: applyConstraints on the existing track (no re-capture). */
function applyTrackSettings(height: number, frameRate: number) {
  const sender = pc?.getSenders().find((s: any) => s.track?.kind === 'video')
  if (sender?.track) (sender.track as any).contentHint = 'detail'
  const tr = pc?.getTransceivers().find((t: any) => t.kind === 'video')
  if (tr) (tr as any).degradationPreference = 'maintain-resolution'
  if (sender?.track) {
    try { sender.track.applyConstraints({ height: { ideal: height }, frameRate: { ideal: frameRate } }).catch(() => {}) } catch {}
    applySenderParams(sender, { maxBitrate: currentMaxBitrate, maxFramerate: frameRate, scaleResolutionDownBy: 1 })
    dispQuality.value = height >= 1000 ? '1080p' : height >= 700 ? '720p' : '540p'
  }
}

/** Tiered adaptive controller + static-idle fps reduction. Runs every 2s. */
function startAdaptiveController() {
  clearInterval(bwTimer)
  prevFramesEncoded = 0
  hasPrevFrames = false
  lastDir = 0
  dirSamples = 0
  bwTimer = setInterval(async () => {
    if (!pc) return
    try {
      const stats = await pc.getStats()
      let lost = 0, received = 0, rtt = 0, framesEncoded = 0
      stats.forEach((r: any) => {
        if (r.type === 'remote-inbound-rtp' && r.kind === 'video') {
          lost = r.packetsLost || 0
          received = r.packetsReceived || 0
          rtt = r.roundTripTime || 0
        }
        if (r.type === 'outbound-rtp' && r.kind === 'video') framesEncoded = r.framesEncoded || 0
      })
      const lossRate = (lost + received) > 0 ? lost / (lost + received) : 0
      let encFps = 0
      if (hasPrevFrames) encFps = (framesEncoded - prevFramesEncoded) / 2
      prevFramesEncoded = framesEncoded
      hasPrevFrames = true

      // Frame-production watchdog: screen lock pauses desktop capture and it
      // often does not resume after unlock. Force a fresh capture when no
      // frames are being encoded for ~8s (throttled to once/15s).
      if (framesEncoded === lastFrameSample) framesFrozen++
      else framesFrozen = 0
      lastFrameSample = framesEncoded
      if (framesFrozen >= 4 && Date.now() - lastReinitAt > 15000) {
        lastReinitAt = Date.now()
        framesFrozen = 0
        console.warn('[host] frames frozen, re-initializing capture')
        reinitCapture()
        return
      }

      if (qualityLocked) {
        // Manual quality: only adapt bitrate, keep resolution/fps untouched.
        let next = currentMaxBitrate
        if (lossRate > 0.03 || rtt > 0.3) next = Math.max(1200000, Math.round(currentMaxBitrate * 0.6))
        else if (lossRate < 0.005 && rtt < 0.15) next = Math.min(8000000, Math.round(currentMaxBitrate * 1.1))
        if (next !== currentMaxBitrate) {
          currentMaxBitrate = next
          const sender = pc?.getSenders().find((s: any) => s.track?.kind === 'video')
          if (sender) applySenderParams(sender, { maxBitrate: next })
        }
        return
      }

      const netGood = lossRate < 0.01 && rtt < 0.15
      const netBad = lossRate > 0.03 || rtt > 0.3
      let desired = currentTierIndex
      if (encFps > 0 && encFps < 12) desired = currentTierIndex - 1
      else if (netBad) desired = currentTierIndex - 1
      else if (netGood && encFps >= 24 && currentTierIndex < TIERS.length - 1) desired = currentTierIndex + 1
      desired = Math.max(0, Math.min(TIERS.length - 1, desired))

      const dir = desired > currentTierIndex ? 1 : desired < currentTierIndex ? -1 : 0
      let tierChanged = false
      if (dir !== 0 && dir === lastDir) {
        dirSamples++
        const need = dir > 0 ? UPGRADE_SAMPLES : DOWNGRADE_SAMPLES
        if (dirSamples >= need && Date.now() - lastTierChangeAt >= TIER_COOLDOWN_MS) {
          currentTierIndex = desired
          currentMaxBitrate = TIERS[currentTierIndex].bitrate
          lastTierChangeAt = Date.now()
          dirSamples = 0
          tierChanged = true
        }
      } else {
        lastDir = dir
        dirSamples = dir !== 0 ? 1 : 0
      }

      // Static-idle fps reduction
      const idle = Date.now() - lastInputAt > STATIC_IDLE_MS
      const fpsTarget = idle ? 6 : 30
      const shouldIdle = idle && !staticFpsActive
      const shouldWake = !idle && staticFpsActive

      if (tierChanged || shouldIdle || shouldWake) {
        staticFpsActive = idle
        applyTrackSettings(TIERS[currentTierIndex].height, fpsTarget)
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

// ===== Clipboard sync =====

function startClipboardSync() {
  clearInterval(clipboardTimer)
  clipboardTimer = setInterval(async () => {
    if (!currentDataChannel || currentDataChannel.readyState !== 'open') return
    try {
      const text = (await win.mqbox.clipboard.readText()) || ''
      if (text && text !== lastLocalClipboard && text !== lastRemoteClipboard) {
        lastLocalClipboard = text
        try { currentDataChannel.send(JSON.stringify({ type: 'clipboard', text })) } catch {}
      }
    } catch {}
  }, 1500)
}

// ===== File transfer over reliable datachannel =====

interface FileRecv {
  id: string
  name: string
  size: number
  buf: Uint8Array
  received: number
}
let fileRecv: FileRecv | null = null

async function sendFileOverDc(dc: any, file: File, onProgress: (p: number) => void) {
  if (!dc || dc.readyState !== 'open') { status.value = '文件通道未就绪'; return }
  const id = 'f' + Date.now().toString(36)
  const size = file.size
  try {
    dc.send(JSON.stringify({ type: 'file-meta', id, name: file.name, size }))
    const buf = new Uint8Array(await file.arrayBuffer())
    let sent = 0
    while (sent < size) {
      if (dc.bufferedAmount > 4 * 1024 * 1024) {
        await new Promise<void>((res) => dc.addEventListener('bufferedamountlow', () => res(), { once: true }))
      }
      const chunk = buf.subarray(sent, sent + FILE_CHUNK)
      dc.send(chunk)
      sent += chunk.byteLength
      onProgress(size ? sent / size : 1)
    }
    dc.send(JSON.stringify({ type: 'file-done', id }))
  } catch (e: any) {
    console.warn('[host] sendFile error:', e.message)
  }
}

function setupFileChannel(dc: any) {
  fileChannel = dc
  dc.binaryType = 'arraybuffer'
  if (typeof dc.bufferedAmountLowThreshold === 'number') dc.bufferedAmountLowThreshold = 4 * 1024 * 1024
  dc.onmessage = (msg: any) => {
    try {
      if (typeof msg.data === 'string') {
        const ev = JSON.parse(msg.data)
        if (ev.type === 'file-meta') {
          fileRecv = { id: ev.id, name: ev.name, size: ev.size || 0, buf: new Uint8Array(ev.size || 0), received: 0 }
          fileProgress.value = { name: ev.name, percent: 0, dir: 'in' }
        } else if (ev.type === 'file-done') {
          if (fileRecv) {
            win.mqbox.remote.saveFile(fileRecv.name, fileRecv.buf.buffer as ArrayBuffer)
              .then((r: any) => { status.value = r?.ok ? `已保存: ${r.path || ''}` : '保存失败' })
              .catch(() => { status.value = '保存失败' })
          }
          fileRecv = null
          fileProgress.value = null
        } else if (ev.type === 'file-cancel') {
          fileRecv = null
          fileProgress.value = null
        }
        return
      }
      if (fileRecv && msg.data instanceof ArrayBuffer) {
        const chunk = new Uint8Array(msg.data)
        fileRecv.buf.set(chunk, fileRecv.received)
        fileRecv.received += chunk.byteLength
        fileProgress.value = fileRecv.size
          ? { name: fileRecv.name, percent: Math.min(1, fileRecv.received / fileRecv.size), dir: 'in' }
          : null
      }
    } catch (e: any) { console.warn('[host] file dc error:', e.message) }
  }
}

function pickFileToSend() {
  const input = document.createElement('input')
  input.type = 'file'
  input.onchange = () => {
    const f = input.files?.[0]
    if (f && fileChannel && fileChannel.readyState === 'open') {
      sendFileOverDc(fileChannel, f, (p) => {
        fileProgress.value = { name: f.name, percent: p, dir: 'out' }
        if (p >= 1) fileProgress.value = null
      })
    }
  }
  input.click()
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
    attachTrackEvents(stream.getVideoTracks()[0])

    pc = newPeer(await getIceServers())

    pc.ondatachannel = (e) => {
      if (e.channel.label === 'file') { setupFileChannel(e.channel); return }
      currentDataChannel = e.channel
      e.channel.onopen = () => {
        const { sources } = cachedSources ? { sources: cachedSources } : { sources: [] }
        e.channel.send(JSON.stringify({ type: 'screens', list: sources.map((s: any) => ({ id: s.id, name: s.name })) }))
        startClipboardSync()
      }
      e.channel.onmessage = (msg) => {
        try {
          const ev = JSON.parse(msg.data)
          if (ev.type === 'ping') { try { e.channel.send(JSON.stringify({ type: 'pong' })) } catch {}; return }
          if (ev.type === 'switchScreen') { switchScreen(ev.sourceId); return }
          if (ev.type === 'refresh') { reinitCapture(); return }
          if (ev.type === 'setQuality') {
            qualityLocked = ev.auto !== true
            if (qualityLocked) {
              qualityLockHeight = ev.maxHeight || qualityConfig.maxHeight
              qualityLockFps = ev.maxFrameRate || 30
              dispQuality.value = qualityLockHeight >= 1000 ? '1080p' : qualityLockHeight >= 700 ? '720p' : '540p'
              applyTrackSettings(qualityLockHeight, qualityLockFps)
            } else {
              currentTierIndex = 1
              staticFpsActive = false
            }
            return
          }
          if (ev.type === 'clipboard') {
            if (ev.text && ev.text !== lastRemoteClipboard && ev.text !== lastLocalClipboard) {
              lastRemoteClipboard = ev.text
              lastLocalClipboard = ev.text
              win.mqbox.clipboard.writeText(ev.text).catch(() => {})
            }
            return
          }
          handleInput(ev)
        } catch (e: any) { console.warn('[host] dc message error:', e.message) }
      }
    }

    pc.onicecandidate = (e) => {
      if (e.candidate) sendToChild('ice', e.candidate.toJSON())
    }

    await pc.setRemoteDescription({ type: 'offer', sdp: offer.sdp })
    stream.getTracks().forEach(t => pc!.addTrack(t, stream!))

    const answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    sendToChild('answer', answer)

    const localUfrag = pc.localDescription?.sdp?.match(/a=ice-ufrag:(\S+)/)?.[1]
    for (let i = 0; i < pendingIce.length; i++) {
      const ufrag = pendingIce[i]?.usernameFragment
      if (ufrag && ufrag === localUfrag) continue
      try { await pc.addIceCandidate(pendingIce[i]) } catch {}
    }
    pendingIce = []

    pc.oniceconnectionstatechange = () => {
      if (!pc) return
      const st = pc.iceConnectionState
      if (st === 'connected' || st === 'completed') {
        connected.value = true
        status.value = '推流中'
        hasPeer.value = true
        lastInputAt = Date.now()
        applyTrackSettings(TIERS[currentTierIndex].height, 30)
        startAdaptiveController()
        setTimeout(() => { reinitCapture() }, 1500)
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

async function reinitCapture() {
  if (!pc) return
  try {
    const ns = await navigator.mediaDevices.getUserMedia({
      audio: false, video: { mandatory: { chromeMediaSource: 'desktop', chromeMediaSourceId: currentSourceId, maxFrameRate: qualityConfig.maxFrameRate } } as any,
    })
    const sender = pc?.getSenders().find((s: any) => s.track?.kind === 'video')
    if (sender && pc) await sender.replaceTrack(ns.getVideoTracks()[0])
    if (stream) stream.getTracks().forEach(t => t.stop())
    stream = ns
    attachTrackEvents(ns.getVideoTracks()[0])
    const h = qualityLocked ? qualityLockHeight : TIERS[currentTierIndex].height
    applyTrackSettings(h, qualityLockFps || 30)
  } catch (e: any) { console.warn('[host] reinitCapture error:', e.message) }
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
    attachTrackEvents(ns.getVideoTracks()[0])
    currentSourceId = sourceId
    const h = qualityLocked ? qualityLockHeight : TIERS[currentTierIndex].height
    applyTrackSettings(h, qualityLockFps || 30)
    const { sources: srcs, displays: allDisplays } = await getCachedSources()
    currentDisplay = matchDisplay(srcs.find((s: any) => s.id === sourceId), allDisplays)
    currentDataChannel?.send(JSON.stringify({ type: 'activeScreen', id: sourceId }))
  } catch (e: any) { console.warn('[host] switchScreen error:', e.message) }
}

function disconnect() {
  sendToChild('revoked', {})
  if (bwTimer) { clearInterval(bwTimer); bwTimer = null }
  if (moveTimer) { clearInterval(moveTimer); moveTimer = null }
  if (wheelTimer) { clearTimeout(wheelTimer); wheelTimer = null }
  if (clipboardTimer) { clearInterval(clipboardTimer); clipboardTimer = null }
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
  const h = collapsed.value ? 40 : 160
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
        <div class="row"><span class="label">分辨率</span><span class="val">{{ dispQuality }}</span></div>
        <div class="row" v-if="fileProgress"><span class="label">{{ fileProgress.dir === 'in' ? '接收' : '发送' }} {{ fileProgress.name }}</span><span class="val">{{ Math.round(fileProgress.percent * 100) }}%</span></div>
      </div>
      <div class="panel-actions">
        <button v-if="hasPeer" class="mini-btn" @click="pickFileToSend">发文件</button>
        <button v-if="hasPeer" class="mini-btn danger" @click="disconnect">断开</button>
      </div>
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
.label { color:#888; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:150px; }
.val { color:#ccc; }
.val.ok { color:#28a745; }

.panel-actions { display:flex; gap:8px; padding:0 12px 8px; -webkit-app-region:no-drag; }
.mini-btn { flex:1; padding:5px; border:none;border-radius:6px;background:#2d2d2d;color:#ccc;font-size:11px;cursor:pointer; }
.mini-btn:hover { background:#3a3a3a; color:#fff; }
.mini-btn.danger { background:#c62828; color:#fff; }
.mini-btn.danger:hover { background:#e53935; }
</style>
