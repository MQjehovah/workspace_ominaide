<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted } from 'vue'
import { newPeer, getIceServers } from './webrtc'

const props = defineProps<{ data?:any; execute?:(a:string,args?:any)=>Promise<any>; refresh?:()=>void; close?:()=>void; targetDeviceId?:string }>()
const videoRef = ref<HTMLVideoElement|null>(null)
const viewerWrapRef = ref<HTMLDivElement|null>(null)
const status = ref('准备连接…')
const connected = ref(false)
const screens = ref<any[]>([])
const activeScreenId = ref('')
const videoReady = ref(false)
const qualityMode = ref<'auto'|'540p'|'720p'|'1080p'>('auto')
const hostLocked = ref(false)
const fileUi = ref<{ name: string; percent: number; dir: 'in'|'out' } | null>(null)
const diag = ref({ rtt: 0, fps: 0, bitrate: 0, loss: 0, jitter: 0, resolution: '', net: '' })

let pc: RTCPeerConnection | null = null
let dc: RTCDataChannel | null = null
let fileDc: RTCDataChannel | null = null
let pendingIce: any[] = []
let connectionEnded = false
let targetId = ''
let cleanupSignal: (() => void) | null = null
let keepaliveTimer: any = null
let lastPong = 0
let reconnectTimer: any = null
let statsTimer: any = null
let prevStats: any = null
let clipboardTimer: any = null
let lastLocalClipboard = ''
let lastRemoteClipboard = ''
let lastFrameDecSample = 0
let decFrozen = 0
let lastRefreshAt = 0
let resizeObserver: ResizeObserver | null = null
let resizeTimer: any = null
let cachedNorm: { cw: number; ch: number; vw: number; vh: number; scale: number; rw: number; rh: number; ox: number; oy: number } | null = null
function invalidateNormCache() { cachedNorm = null }

const FILE_CHUNK = 64 * 1024

async function connect(hostDeviceId: string) {
  console.log('[viewer] connect to:', hostDeviceId)
  connectionEnded = false
  targetId = hostDeviceId
  status.value = '连接中…'
  stopKeepalive()
  stopStatsMonitor()
  cancelReconnect()
  try {
    pc = newPeer(await getIceServers())

    const rm = window.mqbox?.remote?.onSignal?.(function(m: any) {
      onSignal(m)
    })
    cleanupSignal = typeof rm === 'function' ? rm : null

    props.execute?.('sendSignal', { type: 'requestControl', target_deviceId: targetId, name: 'OmniAide 桌面端' })
    status.value = '等待被控端授权…'
  } catch (e: any) {
    console.error('[viewer] connect error:', e)
    status.value = e?.message || String(e)
    cleanup()
  }
}

function applyQuality() {
  if (qualityMode.value === 'auto') {
    determineQuality()
  } else {
    const height = Number(qualityMode.value.replace('p', ''))
    sendInput({ type: 'setQuality', maxWidth: Math.round(height * 16 / 9), maxHeight: height, maxFrameRate: 30, auto: false })
  }
}

function determineQuality() {
  const el = viewerWrapRef.value
  if (!el) return
  const w = el.clientWidth, h = el.clientHeight
  let maxHeight = 720, maxFrameRate = 30
  if (w <= 800 || h <= 600) { maxHeight = 480; maxFrameRate = 20 }
  else if (w <= 1024 || h <= 768) { maxHeight = 576; maxFrameRate = 24 }
  sendInput({ type: 'setQuality', maxWidth: Math.round(maxHeight * 16 / 9), maxHeight, maxFrameRate, auto: true })
}

function startKeepalive() {
  lastPong = Date.now()
  clearInterval(keepaliveTimer)
  keepaliveTimer = setInterval(() => {
    if (dc?.readyState === 'open') {
      try { dc.send(JSON.stringify({ type: 'ping' })) } catch {}
      if (Date.now() - lastPong > 45000) {
        status.value = '控制通道无响应'
      }
    }
  }, 10000)
}

function stopKeepalive() { clearInterval(keepaliveTimer); keepaliveTimer = null }
function cancelReconnect() { clearTimeout(reconnectTimer); reconnectTimer = null }

function startClipboardSync() {
  clearInterval(clipboardTimer)
  clipboardTimer = setInterval(async () => {
    if (!dc || dc.readyState !== 'open') return
    try {
      const text = (await window.mqbox.clipboard.readText()) || ''
      if (text && text !== lastLocalClipboard && text !== lastRemoteClipboard) {
        lastLocalClipboard = text
        try { dc.send(JSON.stringify({ type: 'clipboard', text })) } catch {}
      }
    } catch {}
  }, 1500)
}

function stopClipboardSync() { clearInterval(clipboardTimer); clipboardTimer = null }

function setupFileChannel(ch: RTCDataChannel) {
  fileDc = ch
  ch.binaryType = 'arraybuffer'
  if (typeof (ch as any).bufferedAmountLowThreshold === 'number') (ch as any).bufferedAmountLowThreshold = 4 * 1024 * 1024
  let recv: { name: string; size: number; buf: Uint8Array; received: number } | null = null
  ch.onmessage = (msg: any) => {
    try {
      if (typeof msg.data === 'string') {
        const ev = JSON.parse(msg.data)
        if (ev.type === 'file-meta') {
          recv = { name: ev.name, size: ev.size || 0, buf: new Uint8Array(ev.size || 0), received: 0 }
          fileUi.value = { name: ev.name, percent: 0, dir: 'in' }
        } else if (ev.type === 'file-done') {
          if (recv) {
            window.mqbox.remote.saveFile(recv.name, recv.buf.buffer as ArrayBuffer)
              .then((r: any) => { status.value = r?.ok ? `已保存: ${r.path || ''}` : '保存失败' })
              .catch(() => { status.value = '保存失败' })
          }
          recv = null
          fileUi.value = null
        } else if (ev.type === 'file-cancel') {
          recv = null
          fileUi.value = null
        }
        return
      }
      if (recv && msg.data instanceof ArrayBuffer) {
        const chunk = new Uint8Array(msg.data)
        recv.buf.set(chunk, recv.received)
        recv.received += chunk.byteLength
        fileUi.value = recv.size ? { name: recv.name, percent: Math.min(1, recv.received / recv.size), dir: 'in' } : null
      }
    } catch { console.warn('[viewer] file dc error') }
  }
}

async function sendFileOverDc(ch: RTCDataChannel, file: File, onProgress: (p: number) => void) {
  const id = 'f' + Date.now().toString(36)
  const size = file.size
  try {
    ch.send(JSON.stringify({ type: 'file-meta', id, name: file.name, size }))
    const buf = new Uint8Array(await file.arrayBuffer())
    let sent = 0
    while (sent < size) {
      if (ch.bufferedAmount > 4 * 1024 * 1024) {
        await new Promise<void>((res) => ch.addEventListener('bufferedamountlow', () => res(), { once: true }))
      }
      const chunk = buf.subarray(sent, sent + FILE_CHUNK)
      ch.send(chunk)
      sent += chunk.byteLength
      onProgress(size ? sent / size : 1)
    }
    ch.send(JSON.stringify({ type: 'file-done', id }))
  } catch (e: any) { console.warn('[viewer] sendFile error:', e.message) }
}

function pickFileToSend() {
  if (!fileDc || fileDc.readyState !== 'open') { status.value = '文件通道未就绪'; return }
  const input = document.createElement('input')
  input.type = 'file'
  input.onchange = () => {
    const f = input.files?.[0]
    if (f) {
      sendFileOverDc(fileDc!, f, (p) => {
        fileUi.value = { name: f.name, percent: p, dir: 'out' }
        if (p >= 1) fileUi.value = null
      })
    }
  }
  input.click()
}

async function startOffering() {
  if (!pc) return
  dc = pc.createDataChannel('input', { ordered: false, maxRetransmits: 3 })
  fileDc = pc.createDataChannel('file', { ordered: true })
  setupFileChannel(fileDc)
  dc.onopen = () => { determineQuality(); startKeepalive(); startClipboardSync() }
  dc.onmessage = (msg) => {
    try {
      const ev = JSON.parse(msg.data)
      if (ev.type === 'pong') { lastPong = Date.now(); return }
      if (ev.type === 'screens') { screens.value = ev.list || []; return }
      if (ev.type === 'activeScreen') { activeScreenId.value = ev.id; return }
      if (ev.type === 'lock-state') { hostLocked.value = ev.locked === true; return }
      if (ev.type === 'clipboard') {
        if (ev.text && ev.text !== lastRemoteClipboard && ev.text !== lastLocalClipboard) {
          lastRemoteClipboard = ev.text
          lastLocalClipboard = ev.text
          window.mqbox.clipboard.writeText(ev.text).catch(() => {})
        }
        return
      }
    } catch { console.warn('[viewer] dc message parse error') }
  }
  const tr = pc.addTransceiver('video', { direction: 'recvonly' })
  pc.ontrack = (e) => {
    connected.value = true
    status.value = '已连接（可控制）'
    cancelReconnect()
    try {
      const receivers = pc?.getReceivers().filter((r: any) => r.track?.kind === 'video')
      receivers?.forEach((r: any) => { r.playoutDelayHint = 0.1 })
    } catch {}
    const stream = e.streams?.[0]
    if (!stream) return
    const attachAndPlay = (retryCount = 0) => {
      const el = videoRef.value
      if (!el) { if (retryCount < 50) setTimeout(() => attachAndPlay(retryCount + 1), 100); return }
      el.srcObject = null
      el.srcObject = stream
      el.muted = true
      el.autoplay = true
      el.playsInline = true
      el.play().catch(() => setTimeout(() => attachAndPlay(retryCount), 500))
    }
    const waitFirstFrame = () => {
      const el = videoRef.value
      if (el && el.videoWidth > 0 && el.videoHeight > 0) {
        el.setAttribute('resolution-width', String(el.videoWidth))
        el.setAttribute('resolution-height', String(el.videoHeight))
        invalidateNormCache()
        videoReady.value = true
        return
      }
      setTimeout(waitFirstFrame, 100)
    }
    nextTick(() => { attachAndPlay(); waitFirstFrame() })
    setTimeout(() => { if (qualityMode.value === 'auto') determineQuality() }, 500)
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

function startStatsMonitor() {
  clearInterval(statsTimer)
  prevStats = null
  statsTimer = setInterval(async () => {
    if (!pc || pc.iceConnectionState !== 'connected') return
    try {
      const stats = await pc.getStats()
      let rtt = 0, fps = 0, bitrate = 0, lossRate = 0, jitter = 0, w = 0, h = 0
      let bytesNow = 0, framesNow = 0, lostNow = 0
      const candidates = new Map<string, string>()
      let localType = '', remoteType = ''
      stats.forEach((r: any) => {
        if (r.type === 'candidate') candidates.set(r.id, r.candidateType || '')
        if (r.type === 'candidate-pair' && r.state === 'succeeded') {
          rtt = Math.round((r.currentRoundTripTime || 0) * 1000)
          localType = r.localCandidateType || candidates.get(r.localCandidateId) || ''
          remoteType = r.remoteCandidateType || candidates.get(r.remoteCandidateId) || ''
        }
        if (r.type === 'inbound-rtp' && r.kind === 'video') {
          bytesNow = r.bytesReceived || 0
          framesNow = r.framesDecoded || 0
          lostNow = r.packetsLost || 0
          jitter = Math.round((r.jitter || 0) * 1000)
          w = r.frameWidth || r.width || w
          h = r.frameHeight || r.height || h
        }
        if (r.type === 'media-source' || (r.type === 'outbound-rtp' && r.kind === 'video')) {
          if (r.width && !w) { w = r.width; h = r.height }
        }
      })
      if (prevStats) {
        const dBytes = bytesNow - (prevStats.bytes || 0)
        const dFrames = framesNow - (prevStats.frames || 0)
        const dLost = lostNow - (prevStats.lost || 0)
        bitrate = Math.round(dBytes * 8 / 2 / 1000)
        fps = Math.round(dFrames / 2)
        const total = dFrames + dLost
        lossRate = total > 0 ? Math.round(dLost / total * 100) : 0
      }
      prevStats = { bytes: bytesNow, frames: framesNow, lost: lostNow }
      const relayed = localType === 'relay' || remoteType === 'relay'
      diag.value = {
        rtt, fps, bitrate, loss: lossRate, jitter,
        resolution: w && h ? `${w}×${h}` : '',
        net: relayed ? '中转' : '直连',
      }

      // Decoder-stall watchdog: if the host capture freezes (e.g. after screen
      // lock/unlock) ask the host to re-initialize its capture.
      if (framesNow === lastFrameDecSample) decFrozen++
      else decFrozen = 0
      lastFrameDecSample = framesNow
      if (decFrozen >= 5 && Date.now() - lastRefreshAt > 15000) {
        lastRefreshAt = Date.now()
        decFrozen = 0
        sendInput({ type: 'refresh' })
      }
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
        for (const c of pendingIce) { try { await pc!.addIceCandidate(c) } catch {} }
        pendingIce = []
      } catch (e: any) { console.log('[viewer] answer error:', e.message) }
    })()
  } else if (m.type === 'ice') {
    const localUfrag = pc?.localDescription?.sdp?.match(/a=ice-ufrag:(\S+)/)?.[1]
    if (m.payload?.usernameFragment && m.payload.usernameFragment === localUfrag) {
    } else if (pc && pc.remoteDescription) { try { pc.addIceCandidate(m.payload) } catch {} }
    else if (pc && !pc.remoteDescription) pendingIce.push(m.payload)
  } else if (m.type === 'error') {
    status.value = '被控端错误: ' + (m.message || '未知')
  }
}

function switchScreen(sourceId: string) {
  if (dc && dc.readyState === 'open') { try { dc.send(JSON.stringify({type:'switchScreen',sourceId})) } catch {} }
}

function sendInput(ev: any) {
  if (dc && dc.readyState === 'open') {
    try { dc.send(JSON.stringify(ev)) } catch { console.warn('[viewer] sendInput error') }
  }
}

function normVideo(e: MouseEvent) {
  const el = e.currentTarget as HTMLVideoElement
  const cw = el.clientWidth, ch = el.clientHeight
  const vw = el.videoWidth || 0, vh = el.videoHeight || 0
  if (!vw || !vh || !cw || !ch) return { x: 0.5, y: 0.5 }
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
function onMouseDown(e: MouseEvent) { if (hostLocked.value) return; const button = e.button === 2 ? 'right' : e.button === 1 ? 'middle' : 'left'; sendInput({ type: 'mouseDown', button }) }
function onMouseUp(e: MouseEvent) { if (hostLocked.value) return; const button = e.button === 2 ? 'right' : e.button === 1 ? 'middle' : 'left'; sendInput({ type: 'mouseUp', button }) }
function onWheel(e: WheelEvent) { if (hostLocked.value) return; sendInput({ type: 'wheel', deltaY: e.deltaY }) }
function isIgnoredKey(code: string): boolean { return code === 'F5' || code === 'F11' || code === 'F12' }
function onKeyDown(e: KeyboardEvent) { if (!connected.value || hostLocked.value || !e.code || isIgnoredKey(e.code)) return; e.preventDefault(); sendInput({ type: 'keyDown', code: e.code }) }
function onKeyUp(e: KeyboardEvent) { if (!connected.value || hostLocked.value || !e.code || isIgnoredKey(e.code)) return; e.preventDefault(); sendInput({ type: 'keyUp', code: e.code }) }

function specialKey(key: string) { if (connected.value && !hostLocked.value) sendInput({ type: 'specialKey', key }) }

function onQualityChange(e: Event) {
  const v = (e.target as HTMLSelectElement).value
  qualityMode.value = (v === '540p' || v === '720p' || v === '1080p' ? v : 'auto') as any
  applyQuality()
}

function cleanup(silent = false) {
  connected.value = false
  if (!silent && !connectionEnded && targetId && pc) {
    props.execute?.('sendSignal', { type: 'revoked', target_deviceId: targetId })
  }
  if (dc) { try { dc.close() } catch {} ; dc = null }
  if (fileDc) { try { fileDc.close() } catch {} ; fileDc = null }
  if (pc) { try { pc.close() } catch {} ; pc = null }
  pendingIce = []
  if (videoRef.value) videoRef.value.srcObject = null
  videoReady.value = false
  hostLocked.value = false
  fileUi.value = null
  if (cleanupSignal) { cleanupSignal(); cleanupSignal = null }
  stopKeepalive()
  stopStatsMonitor()
  stopClipboardSync()
  cancelReconnect()
}

function scheduleReconnect() {
  if (connectionEnded) return
  clearTimeout(reconnectTimer)
  reconnectTimer = setTimeout(() => {
    if (connectionEnded) return
    cleanup(true)
    if (targetId) connect(targetId)
  }, 3000)
}

function backToMenu() { connectionEnded = false; cleanup(); props.close?.() }

function setupResizeObserver() {
  if (resizeObserver || !viewerWrapRef.value) return
  resizeObserver = new ResizeObserver(() => {
    clearTimeout(resizeTimer)
    resizeTimer = setTimeout(() => {
      invalidateNormCache()
      if (connected.value && qualityMode.value === 'auto') determineQuality()
    }, 500)
  })
  resizeObserver.observe(viewerWrapRef.value)
}

onMounted(() => {
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
  window.addEventListener('resize', invalidateNormCache)
  window.addEventListener('beforeunload', sendRevokedOnUnload)
  setupResizeObserver()
  if (props.targetDeviceId && props.targetDeviceId !== 'undefined' && props.targetDeviceId !== '') {
    connect(props.targetDeviceId)
  }
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
  window.removeEventListener('resize', invalidateNormCache)
  window.removeEventListener('beforeunload', sendRevokedOnUnload)
  if (resizeObserver) { resizeObserver.disconnect(); resizeObserver = null }
  cleanup()
})

function sendRevokedOnUnload() {
  if (!connectionEnded && targetId) {
    props.execute?.('sendSignal', { type: 'revoked', target_deviceId: targetId })
  }
}
</script>

<template>
  <div class="viewer" ref="viewerWrapRef" tabindex="0">
    <p class="status">{{ status }}</p>
    <div v-if="connected" class="diag-card">
      <div class="diag-row"><span class="diag-label">延迟</span><span class="diag-val">{{ diag.rtt }}ms</span></div>
      <div class="diag-row"><span class="diag-label">帧率</span><span class="diag-val">{{ diag.fps }}fps</span></div>
      <div class="diag-row"><span class="diag-label">网速</span><span class="diag-val">{{ diag.bitrate }}kbps</span></div>
      <div class="diag-row"><span class="diag-label">丢包</span><span class="diag-val">{{ diag.loss }}%</span></div>
      <div class="diag-row"><span class="diag-label">抖动</span><span class="diag-val">{{ diag.jitter }}ms</span></div>
      <div class="diag-row"><span class="diag-label">网络</span><span class="diag-val" :class="diag.net === '直连' ? 'net-direct' : 'net-relay'">{{ diag.net || '-' }}</span></div>
      <div class="diag-row" v-if="diag.resolution"><span class="diag-label">分辨率</span><span class="diag-val">{{ diag.resolution }}</span></div>
    </div>
    <div class="toolbar" v-if="screens.length > 1">
      <button v-for="s in screens" :key="s.id" class="screen-btn" :class="{ active: s.id === activeScreenId }" @click="switchScreen(s.id)">{{ s.name }}</button>
    </div>
    <video ref="videoRef" autoplay playsinline muted class="video"
      @mousemove="onMouseMove" @mousedown="onMouseDown" @mouseup="onMouseUp"
      @wheel="onWheel" @contextmenu.prevent></video>
    <div v-if="connected && !videoReady" class="video-placeholder">画面加载中…</div>
    <div v-if="connected && hostLocked" class="lock-overlay">
      <div class="lock-box">🔒 被控端已锁定</div>
    </div>

    <div v-if="connected" class="action-bar">
      <select class="quality-select" :value="qualityMode" @change="onQualityChange">
        <option value="auto">自适应</option>
        <option value="540p">540p</option>
        <option value="720p">720p</option>
        <option value="1080p">1080p</option>
      </select>
      <button class="act-btn" title="显示桌面" @click="specialKey('desktop')">🖥 桌面</button>
      <button class="act-btn" title="任务管理器" @click="specialKey('taskmanager')">⚙ 任务</button>
      <button class="act-btn" title="锁定" @click="specialKey('lock')">🔒 锁屏</button>
      <button class="act-btn" title="发送文件" @click="pickFileToSend">📤 文件</button>
    </div>
    <div v-if="fileUi" class="file-bar">
      <span class="file-name">{{ fileUi.name }}</span>
      <div class="file-progress"><div class="file-progress-inner" :style="{ width: (fileUi.percent * 100) + '%' }"></div></div>
      <span class="file-pct">{{ Math.round(fileUi.percent * 100) }}%</span>
    </div>
  </div>
</template>

<style scoped>
.viewer { height:100vh; background:#212529; display:flex; flex-direction:column; position:relative; overflow:hidden; }
.toolbar { display:flex; gap:4px; padding:6px 12px; background:rgba(0,0,0,.4); justify-content:center; flex-shrink:0; }
.screen-btn { padding:4px 10px; border-radius:4px; border:none; background:rgba(255,255,255,.1); color:#fff; font-size:11px; cursor:pointer; }
.screen-btn.active { background:#e91e63; color:#fff; }
.screen-btn:hover { background:rgba(255,255,255,.2); }
.video { flex:1; min-height:0; min-width:0; object-fit:contain; width:100%; background:#000; cursor:none; display:block; }
.video-placeholder { position:fixed; inset:0; display:flex; align-items:center; justify-content:center; background:#212529; color:#888; font-size:13px; z-index:5; }
.lock-overlay { position:fixed; inset:0; display:flex; align-items:center; justify-content:center; background:rgba(0,0,0,.6); z-index:9; }
.lock-box { background:rgba(0,0,0,.75); border:1px solid rgba(255,255,255,.15); color:#fff; font-size:15px; padding:14px 22px; border-radius:10px; }
.status { position:fixed; top:12px; left:50%; transform:translateX(-50%); margin:0; padding:6px 14px; background:rgba(0,0,0,.6); color:#fff; font-size:12px; border-radius:16px; z-index:10; }
.diag-card { position:fixed; top:12px; left:12px; background:rgba(0,0,0,.7); border-radius:8px; padding:8px 12px; z-index:10; font-size:11px; line-height:1.6; min-width:120px; backdrop-filter:blur(4px); }
.diag-row { display:flex; justify-content:space-between; gap:12px; }
.diag-label { color:#999; }
.diag-val { color:#eee; font-family:'SF Mono',Consolas,monospace; font-variant-numeric:tabular-nums; }
.diag-val.net-direct { color:#28a745; font-weight:600; }
.diag-val.net-relay { color:#ff9800; font-weight:600; }

.action-bar { display:flex; gap:6px; padding:6px 12px; background:rgba(0,0,0,.55); justify-content:center; align-items:center; flex-shrink:0; z-index:8; }
.quality-select { background:#2d2d2d; color:#fff; border:1px solid #444; border-radius:4px; font-size:11px; padding:2px 4px; }
.act-btn { padding:4px 8px; border-radius:4px; border:none; background:rgba(255,255,255,.12); color:#fff; font-size:11px; cursor:pointer; white-space:nowrap; }
.act-btn:hover { background:rgba(255,255,255,.25); }

.file-bar { position:fixed; bottom:46px; left:50%; transform:translateX(-50%); width:min(70%, 420px); display:flex; align-items:center; gap:8px; background:rgba(0,0,0,.75); border-radius:8px; padding:6px 10px; z-index:20; }
.file-name { color:#ddd; font-size:11px; max-width:120px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.file-progress { flex:1; height:6px; background:#333; border-radius:3px; overflow:hidden; }
.file-progress-inner { height:100%; background:#4caf50; transition:width .15s; }
.file-pct { color:#eee; font-size:11px; font-variant-numeric:tabular-nums; }
</style>
