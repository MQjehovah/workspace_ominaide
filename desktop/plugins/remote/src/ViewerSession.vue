<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { newPeer, getIceServers, setCodecPreferences } from './webrtc'

const props = defineProps<{ data?:any; execute?:(a:string,args?:any)=>Promise<any>; refresh?:()=>void; close?:()=>void; targetDeviceId?:string }>()
const videoRef = ref<HTMLVideoElement|null>(null)
const status = ref('准备连接…')
const connected = ref(false)
const screens = ref<any[]>([])
const activeScreenId = ref('')
const diag = ref({ rtt: 0, fps: 0, bitrate: 0, loss: 0, jitter: 0, resolution: '' })

let pc: RTCPeerConnection | null = null
let dc: RTCDataChannel | null = null
let pendingIce: any[] = []
let connectionEnded = false
let targetId = ''
let cleanupSignal: (() => void) | null = null
let keepaliveTimer: any = null
let lastPong = 0
let reconnectTimer: any = null
let adaptTimer: any = null
let statsTimer: any = null
let prevStats: any = null
let currentQuality = { maxWidth: 1280, maxHeight: 720, maxFrameRate: 24 }
let qualityGoodSince = 0
let cachedNorm: { cw: number; ch: number; vw: number; vh: number; scale: number; rw: number; rh: number; ox: number; oy: number } | null = null
function invalidateNormCache() { cachedNorm = null }

async function connect(hostDeviceId: string) {
  console.log('[viewer] connect to:', hostDeviceId)
  connectionEnded = false
  targetId = hostDeviceId
  status.value = '连接中…'
  stopKeepalive()
  stopAdaptiveQuality()
  stopStatsMonitor()
  cancelReconnect()
  try {
    pc = newPeer(await getIceServers())
    setCodecPreferences(pc)

    // Listen for signals via App.vue WS
    const rm = window.mqbox?.remote?.onSignal?.(function(m: any) {
      console.log('[viewer] onSignal:', m.type)
      onSignal(m)
    })
    cleanupSignal = typeof rm === 'function' ? rm : null

    console.log('[viewer] sending requestControl target:', targetId)
    props.execute?.('sendSignal', { type: 'requestControl', target_deviceId: targetId, name: 'OmniAide 桌面端' })
    status.value = '等待被控端授权…'
  } catch (e: any) {
    console.error('[viewer] connect error:', e)
    status.value = e?.message || String(e)
    cleanup()
  }
}

function determineQuality() {
  const el = videoRef.value
  if (!el) return
  const w = el.clientWidth, h = el.clientHeight
  let maxWidth = 1280, maxHeight = 720, maxFrameRate = 24
  if (w <= 800 || h <= 600) { maxWidth = 640; maxHeight = 480; maxFrameRate = 15 }
  else if (w <= 1024 || h <= 768) { maxWidth = 1024; maxHeight = 768; maxFrameRate = 20 }
  sendInput({ type: 'setQuality', maxWidth, maxHeight, maxFrameRate })
  currentQuality = { maxWidth, maxHeight, maxFrameRate }
  qualityGoodSince = 0
}

function startKeepalive() {
  lastPong = Date.now()
  clearInterval(keepaliveTimer)
  keepaliveTimer = setInterval(() => {
    if (dc?.readyState === 'open') {
      try { dc.send(JSON.stringify({ type: 'ping' })) } catch {}
      if (Date.now() - lastPong > 45000) {
        console.log('[viewer] keepalive timeout')
        status.value = '控制通道无响应'
      }
    }
  }, 10000)
}

function stopKeepalive() { clearInterval(keepaliveTimer); keepaliveTimer = null }

function cancelReconnect() { clearTimeout(reconnectTimer); reconnectTimer = null }

async function startOffering() {
  if (!pc) return
  dc = pc.createDataChannel('input', { ordered: false, maxRetransmits: 0 })
  dc.onopen = () => { determineQuality(); startKeepalive() }
  dc.onmessage = (msg) => {
    try {
      const ev = JSON.parse(msg.data)
      if (ev.type === 'pong') { lastPong = Date.now(); return }
      if (ev.type === 'screens') { screens.value = ev.list || []; return }
      if (ev.type === 'activeScreen') { activeScreenId.value = ev.id; return }
    } catch { console.warn('[viewer] dc message parse error') }
  }
  pc.addTransceiver('video', { direction: 'recvonly' })
  pc.ontrack = (e) => {
    console.log('[viewer] ontrack:', e.track?.kind, 'readyState:', e.track?.readyState)
    connected.value = true
    status.value = '已连接（可控制）'
    cancelReconnect()
    const stream = e.streams?.[0]
    if (!stream) return
    const attachAndPlay = (retryCount = 0) => {
      const el = videoRef.value
      if (!el) { if (retryCount < 50) setTimeout(() => attachAndPlay(retryCount + 1), 100); return }
      el.srcObject = null
      el.srcObject = stream
      el.muted = true
      el.autoplay = true
      el.play().catch(() => setTimeout(() => attachAndPlay(retryCount), 500))
    }
    nextTick(() => attachAndPlay())
    setTimeout(() => determineQuality(), 500)
    startAdaptiveQuality()
    startStatsMonitor()
  }
  pc.onicecandidate = (e) => {
    if (e.candidate) {
      props.execute?.('sendSignal', { type: 'ice', target_deviceId: targetId, payload: e.candidate.toJSON() })
    }
  }
  pc.oniceconnectionstatechange = () => {
    if (!pc) return
    const st = pc.iceConnectionState
    console.log('[viewer] ICE state:', st)
    if (st === 'connected') { cancelReconnect(); status.value = '已连接（可控制）' }
    else if (st === 'disconnected' && !connectionEnded) { status.value = '连接中断，等待恢复…' }
    else if (st === 'failed' && !connectionEnded) { status.value = '连接失败，重连中…'; connected.value = false; scheduleReconnect() }
    else if (st === 'closed') { connected.value = false }
  }
  pc.onconnectionstatechange = () => {}
  const offer = await pc.createOffer()
  await pc.setLocalDescription(offer)
  props.execute?.('sendSignal', { type: 'offer', target_deviceId: targetId, payload: offer })
  status.value = '等待画面…'
}

function startAdaptiveQuality() {
  clearInterval(adaptTimer)
  adaptTimer = setInterval(async () => {
    if (!pc || pc.iceConnectionState !== 'connected') return
    try {
      const stats = await pc.getStats()
      let totalLost = 0, totalReceived = 0, rtt = 0
      stats.forEach((r: any) => {
        if (r.type === 'inbound-rtp' && r.kind === 'video') {
          totalLost += r.packetsLost || 0
          totalReceived += r.packetsReceived || 0
        }
        if (r.type === 'candidate-pair' && r.state === 'succeeded') {
          rtt = r.currentRoundTripTime || 0
        }
      })
      const lossRate = totalReceived > 0 ? totalLost / (totalLost + totalReceived) : 0
      const highLatency = rtt > 0.3
      const current = currentQuality
      if (lossRate > 0.03 || highLatency) {
        if (current.maxWidth > 800) {
          currentQuality = { maxWidth: 800, maxHeight: 600, maxFrameRate: 15 }
          sendInput({ type: 'setQuality', ...currentQuality })
          qualityGoodSince = 0
        }
      } else if (lossRate < 0.005 && !highLatency && current.maxWidth < 1280) {
        if (qualityGoodSince === 0) qualityGoodSince = Date.now()
        else if (Date.now() - qualityGoodSince > 20000) {
          currentQuality = { maxWidth: 1280, maxHeight: 720, maxFrameRate: 24 }
          sendInput({ type: 'setQuality', ...currentQuality })
        }
      } else { qualityGoodSince = 0 }
    } catch {}
  }, 10000)
}

function stopAdaptiveQuality() { clearInterval(adaptTimer); adaptTimer = null }

function startStatsMonitor() {
  clearInterval(statsTimer)
  prevStats = null
  statsTimer = setInterval(async () => {
    if (!pc || pc.iceConnectionState !== 'connected') return
    try {
      const stats = await pc.getStats()
      let rtt = 0, fps = 0, bitrate = 0, lossRate = 0, jitter = 0, w = 0, h = 0
      let bytesNow = 0, framesNow = 0, lostNow = 0
      stats.forEach((r: any) => {
        if (r.type === 'candidate-pair' && r.state === 'succeeded') rtt = Math.round((r.currentRoundTripTime || 0) * 1000)
        if (r.type === 'inbound-rtp' && r.kind === 'video') {
          bytesNow = r.bytesReceived || 0
          framesNow = r.framesDecoded || 0
          lostNow = r.packetsLost || 0
          jitter = Math.round((r.jitter || 0) * 1000)
          const m = r.codecId || ''
        }
        if (r.type === 'media-source' || (r.type === 'outbound-rtp' && r.kind === 'video')) {
          if (r.width) { w = r.width; h = r.height }
        }
      })
      if (prevStats) {
        const dt = (stats as any).entries ? 2 : 2
        const dBytes = bytesNow - (prevStats.bytes || 0)
        const dFrames = framesNow - (prevStats.frames || 0)
        const dLost = lostNow - (prevStats.lost || 0)
        bitrate = Math.round(dBytes * 8 / 2 / 1000)
        fps = Math.round(dFrames / 2)
        const total = dFrames + dLost
        lossRate = total > 0 ? Math.round(dLost / total * 100) : 0
      }
      prevStats = { bytes: bytesNow, frames: framesNow, lost: lostNow }
      diag.value = { rtt, fps, bitrate, loss: lossRate, jitter, resolution: w && h ? `${w}×${h}` : '' }
    } catch {}
  }, 2000)
}

function stopStatsMonitor() { clearInterval(statsTimer); statsTimer = null; prevStats = null }

function onSignal(m: any) {
  if (m.type === 'controlAllowed') {
    startOffering()
  } else if (m.type === 'controlDenied') {
    connectionEnded = true
    status.value = m.reason === 'busy' ? '被控端忙（已有连接）' : '被控端拒绝'
    cleanup()
  } else if (m.type === 'revoked') {
    connectionEnded = true
    status.value = '被控端断开了控制'
    cleanup()
  } else if (m.type === 'answer' && pc) {
    (async () => {
      try {
        await pc!.setRemoteDescription({ type: 'answer', sdp: m.payload.sdp })
        for (const c of pendingIce) { try { await pc!.addIceCandidate(c) } catch { console.warn('[viewer] addIce error') } }
        pendingIce = []
        console.log('[viewer] answer set, iceState:', pc!.iceConnectionState)
      } catch (e: any) { console.log('[viewer] answer error:', e.message) }
    })()
  } else if (m.type === 'ice') {
    const localUfrag = pc?.localDescription?.sdp?.match(/a=ice-ufrag:(\S+)/)?.[1]
    if (m.payload?.usernameFragment && m.payload.usernameFragment === localUfrag) {
    } else if (pc && pc.remoteDescription) { try { pc.addIceCandidate(m.payload) } catch { console.warn('[viewer] addIce error') } }
    else if (pc && !pc.remoteDescription) pendingIce.push(m.payload)
  } else if (m.type === 'error') {
    status.value = '被控端错误: ' + (m.message || '未知')
  }
}

function switchScreen(sourceId: string) {
  if (dc && dc.readyState === 'open') { try { dc.send(JSON.stringify({type:'switchScreen',sourceId})) } catch { console.warn('[viewer] switchScreen send error') } }
}

function sendInput(ev: any) {
  if (dc && dc.readyState === 'open') {
    try { dc.send(JSON.stringify(ev)) } catch { console.warn('[viewer] sendInput error') }
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

let lastMoveTime = 0
function onMouseMove(e: MouseEvent) { const now = Date.now(); if (now - lastMoveTime < 16) return; lastMoveTime = now; const { x, y } = normVideo(e); sendInput({ type: 'mouseMove', x, y }) }
function onMouseDown(e: MouseEvent) { const button = e.button === 2 ? 'right' : e.button === 1 ? 'middle' : 'left'; sendInput({ type: 'mouseDown', button }) }
function onMouseUp(e: MouseEvent) { const button = e.button === 2 ? 'right' : e.button === 1 ? 'middle' : 'left'; sendInput({ type: 'mouseUp', button }) }
function onWheel(e: WheelEvent) { sendInput({ type: 'wheel', deltaY: e.deltaY }) }
function isIgnoredKey(code: string): boolean { return code === 'F5' || code === 'F11' || code === 'F12' }
function onKeyDown(e: KeyboardEvent) { if (!connected.value || !e.code || isIgnoredKey(e.code)) return; e.preventDefault(); sendInput({ type: 'keyDown', code: e.code }) }
function onKeyUp(e: KeyboardEvent) { if (!connected.value || !e.code || isIgnoredKey(e.code)) return; e.preventDefault(); sendInput({ type: 'keyUp', code: e.code }) }

function cleanup(silent = false) {
  connected.value = false
  if (!silent && !connectionEnded && targetId && pc) {
    props.execute?.('sendSignal', { type: 'revoked', target_deviceId: targetId })
  }
  if (dc) { try { dc.close() } catch {} ; dc = null }
  if (pc) { try { pc.close() } catch {} ; pc = null }
  pendingIce = []
  if (videoRef.value) videoRef.value.srcObject = null
  if (cleanupSignal) { cleanupSignal(); cleanupSignal = null }
  stopKeepalive()
  stopAdaptiveQuality()
  stopStatsMonitor()
  cancelReconnect()
}

function scheduleReconnect() {
  if (connectionEnded) return
  clearTimeout(reconnectTimer)
  reconnectTimer = setTimeout(() => {
    if (connectionEnded) return
    console.log('[viewer] reconnecting...')
    cleanup(true)
    if (targetId) connect(targetId)
  }, 3000)
}

function backToMenu() { connectionEnded = false; cleanup(); props.close?.() }

onMounted(() => {
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
  window.addEventListener('resize', invalidateNormCache)
  window.addEventListener('beforeunload', sendRevokedOnUnload)
  if (props.targetDeviceId && props.targetDeviceId !== 'undefined' && props.targetDeviceId !== '') {
    connect(props.targetDeviceId)
  }
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
  window.removeEventListener('resize', invalidateNormCache)
  window.removeEventListener('beforeunload', sendRevokedOnUnload)
  cleanup()
})

function sendRevokedOnUnload() {
  if (!connectionEnded && targetId) {
    props.execute?.('sendSignal', { type: 'revoked', target_deviceId: targetId })
  }
}
</script>

<template>
  <div class="viewer" tabindex="0">
    <p class="status">{{ status }}</p>
    <div v-if="connected" class="diag-card">
      <div class="diag-row"><span class="diag-label">延迟</span><span class="diag-val">{{ diag.rtt }}ms</span></div>
      <div class="diag-row"><span class="diag-label">帧率</span><span class="diag-val">{{ diag.fps }}fps</span></div>
      <div class="diag-row"><span class="diag-label">网速</span><span class="diag-val">{{ diag.bitrate }}kbps</span></div>
      <div class="diag-row"><span class="diag-label">丢包</span><span class="diag-val">{{ diag.loss }}%</span></div>
      <div class="diag-row"><span class="diag-label">抖动</span><span class="diag-val">{{ diag.jitter }}ms</span></div>
      <div class="diag-row" v-if="diag.resolution"><span class="diag-label">分辨率</span><span class="diag-val">{{ diag.resolution }}</span></div>
    </div>
    <div class="toolbar" v-if="screens.length > 1">
      <button v-for="s in screens" :key="s.id" class="screen-btn" :class="{ active: s.id === activeScreenId }" @click="switchScreen(s.id)">{{ s.name }}</button>
    </div>
    <video ref="videoRef" autoplay playsinline muted class="video"
      @mousemove="onMouseMove" @mousedown="onMouseDown" @mouseup="onMouseUp"
      @wheel.prevent="onWheel" @contextmenu.prevent></video>
  </div>
</template>

<style scoped>
.viewer { height:100vh; background:#212529; display:flex; flex-direction:column; position:relative; }
.toolbar { display:flex; gap:4px; padding:6px 12px; background:rgba(0,0,0,.4); justify-content:center; flex-shrink:0; }
.screen-btn { padding:4px 10px; border-radius:4px; border:none; background:rgba(255,255,255,.1); color:#fff; font-size:11px; cursor:pointer; }
.screen-btn.active { background:#e91e63; color:#fff; }
.screen-btn:hover { background:rgba(255,255,255,.2); }
.video { flex:1; object-fit:contain; width:100%; height:100%; background:#000; cursor:none; }
.status { position:fixed; top:12px; left:50%; transform:translateX(-50%); margin:0; padding:6px 14px; background:rgba(0,0,0,.6); color:#fff; font-size:12px; border-radius:16px; z-index:10; }
.diag-card { position:fixed; top:12px; left:12px; background:rgba(0,0,0,.7); border-radius:8px; padding:8px 12px; z-index:10; font-size:11px; line-height:1.6; min-width:120px; backdrop-filter:blur(4px); }
.diag-row { display:flex; justify-content:space-between; gap:12px; }
.diag-label { color:#999; }
.diag-val { color:#eee; font-family:'SF Mono',Consolas,monospace; font-variant-numeric:tabular-nums; }
</style>
