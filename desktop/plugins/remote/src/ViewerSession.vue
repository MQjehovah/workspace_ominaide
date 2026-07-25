<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { newPeer, getIceServers } from './webrtc'

const props = defineProps<{ data?:any; execute?:(a:string,args?:any)=>Promise<any>; refresh?:()=>void; close?:()=>void; targetDeviceId?:string }>()
const videoRef = ref<HTMLVideoElement|null>(null)
const status = ref('准备连接…')
const connected = ref(false)
const screens = ref<any[]>([])
const activeScreenId = ref('')

let pc: RTCPeerConnection | null = null
let dc: RTCDataChannel | null = null
let pendingIce: any[] = []
let connectionEnded = false
let targetId = ''
let cleanupSignal: (() => void) | null = null
let cachedNorm: { cw: number; ch: number; vw: number; vh: number; scale: number; rw: number; rh: number; ox: number; oy: number } | null = null
function invalidateNormCache() { cachedNorm = null }

async function connect(hostDeviceId: string) {
  console.log('[viewer] connect to:', hostDeviceId)
  connectionEnded = false
  targetId = hostDeviceId
  status.value = '连接中…'
  try {
    pc = newPeer(await getIceServers())

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
  let maxWidth = 1920, maxHeight = 1080, maxFrameRate = 30
  if (w <= 800 || h <= 600) { maxWidth = 800; maxHeight = 600; maxFrameRate = 15 }
  else if (w <= 1280 || h <= 720) { maxWidth = 1280; maxHeight = 720; maxFrameRate = 24 }
  sendInput({ type: 'setQuality', maxWidth, maxHeight, maxFrameRate })
}

async function startOffering() {
  if (!pc) return
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
    console.log('[viewer] ontrack:', e.track?.kind, 'enabled:', e.track?.enabled, 'readyState:', e.track?.readyState, 'muted:', e.track?.muted, 'streams:', e.streams?.length)
    connected.value = true
    status.value = '已连接（可控制）'
    const stream = e.streams?.[0]
    if (!stream) { console.log('[viewer] ERROR: no stream in ontrack!'); return }
    console.log('[viewer] stream tracks:', stream.getTracks().map(t => `${t.kind}:${t.readyState}:${t.enabled}:${t.muted}`).join(','))

    const attachAndPlay = (retryCount = 0) => {
      const el = videoRef.value
      if (!el) {
        console.log('[viewer] videoRef null, retry', retryCount)
        if (retryCount < 50) setTimeout(() => attachAndPlay(retryCount + 1), 100)
        return
      }
      el.srcObject = null
      el.srcObject = stream
      el.muted = true
      el.autoplay = true
      console.log('[viewer] video dimensions:', el.clientWidth, 'x', el.clientHeight, 'readyState:', el.readyState, 'networkState:', el.networkState, 'paused:', el.paused)

      el.onloadeddata = () => console.log('[viewer] video loadeddata, videoWidth:', el.videoWidth, 'x', el.videoHeight)
      el.onerror = (ev) => console.log('[viewer] video error:', (ev as any).message || 'unknown')

      el.play().then(() => {
        console.log('[viewer] play ok, video size:', el.videoWidth, 'x', el.videoHeight)
      }).catch((err) => {
        console.log('[viewer] play err:', err.message, '- retrying in 500ms')
        setTimeout(() => attachAndPlay(retryCount), 500)
      })

      setTimeout(() => {
        console.log('[viewer] play timeout check - readyState:', el.readyState, 'networkState:', el.networkState, 'videoWidth:', el.videoWidth, 'paused:', el.paused, 'currentTime:', el.currentTime, 'srcObject:', el.srcObject !== null)
        // Diagnostic stats
        if (pc) {
          pc.getStats().then((stats: any) => {
            let reports: any[] = []
            stats.forEach((report: any) => {
              if (report.type === 'candidate-pair' || report.type === 'inbound-rtp' || report.type === 'transport' || report.type === 'dtls-transport') {
                reports.push(JSON.parse(JSON.stringify(report)))
              }
            })
            console.log('[viewer] stats at 3s:', JSON.stringify(reports, null, 0).substring(0, 2000))
          }).catch((e: any) => console.log('[viewer] stats error:', e.message))
        }
      }, 3000)
    }
    nextTick(() => attachAndPlay())
    setTimeout(() => determineQuality(), 500)
  }
  pc.onicecandidate = (e) => {
    if (e.candidate) {
      console.log('[viewer] sending ICE:', e.candidate.candidate?.substring(0, 60))
      props.execute?.('sendSignal', { type: 'ice', target_deviceId: targetId, payload: e.candidate.toJSON() })
    } else {
      console.log('[viewer] ICE gathering complete (null candidate)')
    }
  }
  console.log('[viewer] initial iceConnectionState:', pc.iceConnectionState, 'iceGatheringState:', pc.iceGatheringState, 'signalingState:', pc.signalingState)
  pc.oniceconnectionstatechange = () => {
    if (!pc) return
    const st = pc.iceConnectionState
    console.log('[viewer] ICE state:', st, 'gathering:', pc.iceGatheringState, 'signaling:', pc.signalingState, 'connectionState:', pc.connectionState)
    if (st === 'failed') { if (!connectionEnded) status.value = '连接失败（ICE）'; connected.value = false; cleanup() }
    else if (st === 'disconnected') { if (!connectionEnded) status.value = '连接中断，尝试恢复…' }
    else if (st === 'closed') { connected.value = false }
  }
  pc.onicegatheringstatechange = () => {
    if (!pc) return
    console.log('[viewer] ICE gathering:', pc.iceGatheringState)
  }
  pc.onconnectionstatechange = () => {
    if (!pc) return
    console.log('[viewer] connectionState:', pc.connectionState)
  }
  const offer = await pc.createOffer()
  await pc.setLocalDescription(offer)
  console.log('[viewer] offer SDP lines:', offer.sdp?.split('\n').filter(l => l.startsWith('m=')).join(', '))
  props.execute?.('sendSignal', { type: 'offer', target_deviceId: targetId, payload: offer })
  status.value = '等待画面…'
}

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
        console.log('[viewer] answer set, signaling:', pc!.signalingState, 'iceState:', pc!.iceConnectionState)
      } catch (e: any) { console.log('[viewer] answer error:', e.message) }
    })()
  } else if (m.type === 'ice') {
    // Filter out self-echoed ICE candidates (same machine broadcast issue)
    const localUfrag = pc?.localDescription?.sdp?.match(/a=ice-ufrag:(\S+)/)?.[1]
    if (m.payload?.usernameFragment && m.payload.usernameFragment === localUfrag) {
      // Skip self-echoed candidate
    } else if (pc && pc.remoteDescription) { try { pc.addIceCandidate(m.payload) } catch (e: any) { console.log('[viewer] addIce error:', e.message) } }
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

function onMouseMove(e: MouseEvent) { const { x, y } = normVideo(e); sendInput({ type: 'mouseMove', x, y }) }
function onMouseDown(e: MouseEvent) { const button = e.button === 2 ? 'right' : e.button === 1 ? 'middle' : 'left'; sendInput({ type: 'mouseDown', button }) }
function onMouseUp(e: MouseEvent) { const button = e.button === 2 ? 'right' : e.button === 1 ? 'middle' : 'left'; sendInput({ type: 'mouseUp', button }) }
function onWheel(e: WheelEvent) { e.preventDefault(); sendInput({ type: 'wheel', deltaY: e.deltaY }) }
function isIgnoredKey(code: string): boolean { return code === 'F5' || code === 'F11' || code === 'F12' }
function onKeyDown(e: KeyboardEvent) { if (!connected.value || !e.code || isIgnoredKey(e.code)) return; e.preventDefault(); sendInput({ type: 'keyDown', code: e.code }) }
function onKeyUp(e: KeyboardEvent) { if (!connected.value || !e.code || isIgnoredKey(e.code)) return; e.preventDefault(); sendInput({ type: 'keyUp', code: e.code }) }

function cleanup() {
  connected.value = false
  if (dc) { try { dc.close() } catch {} ; dc = null }
  if (pc) { try { pc.close() } catch {} ; pc = null }
  pendingIce = []
  if (videoRef.value) videoRef.value.srcObject = null
  if (cleanupSignal) { cleanupSignal(); cleanupSignal = null }
}

function backToMenu() { connectionEnded = false; cleanup(); props.close?.() }

onMounted(() => {
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
  window.addEventListener('resize', invalidateNormCache)
  console.log('[viewer] mounted, target=', props.targetDeviceId, 'typeof=', typeof props.targetDeviceId)
  if (props.targetDeviceId && props.targetDeviceId !== 'undefined' && props.targetDeviceId !== '') {
    console.log('[viewer] calling connect with:', props.targetDeviceId)
    connect(props.targetDeviceId)
  } else {
    console.log('[viewer] skipped connect, target is empty or undefined')
  }
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
  window.removeEventListener('resize', invalidateNormCache)
  cleanup()
})
</script>

<template>
  <div class="viewer" tabindex="0">
    <p class="status">{{ status }}</p>
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
.video { flex:1; object-fit:contain; width:100%; height:100%; background:#000; }
.status { position:fixed; top:12px; left:50%; transform:translateX(-50%); margin:0; padding:6px 14px; background:rgba(0,0,0,.6); color:#fff; font-size:12px; border-radius:16px; z-index:10; }
</style>
