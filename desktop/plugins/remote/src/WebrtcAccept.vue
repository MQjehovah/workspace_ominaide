<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { newPeer, getIceServers, setCodecPreferences } from './webrtc'

const props = defineProps<{ data?: any; execute?: (a: string, args?: any) => Promise<any> }>()
const viewerId = new URLSearchParams(window.location.search).get('viewer') || ''

const collapsed = ref(true)
const status = ref('连接中…')
const connected = ref(false)
const hasPeer = ref(false)

let pc: RTCPeerConnection | null = null
let stream: MediaStream | null = null
let pendingIce: any[] = []
let iceProcessedCount = 0
let iceTimer: any = null
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
  const msg: any = { type, payload }
  if (viewerId) msg.target_deviceId = viewerId
  props.execute?.('sendSignal', msg)
}

function cleanup() {
  if (pc) { try { pc.close() } catch {} ; pc = null }
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
  stream = null
  pendingIce = []
  iceProcessedCount = 0
  if (iceTimer) { clearInterval(iceTimer); iceTimer = null }
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
    iceProcessedCount = 0

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

    // Standard WebRTC flow: setRemoteDescription → createAnswer → setLocalDescription → addIceCandidate
    // Set ICE candidate handler BEFORE any SDP operations to avoid losing candidates
    pc.onicecandidate = (e) => {
      if (e.candidate) {
        console.log('[host] local ICE candidate:', e.candidate.candidate?.substring(0, 80), 'component:', e.candidate.component, 'protocol:', e.candidate.protocol)
        sendToChild('ice', e.candidate.toJSON())
      } else {
        console.log('[host] ICE gathering complete (null candidate)')
      }
    }

    await pc.setRemoteDescription({ type: 'offer', sdp: offer.sdp })

    // Use addTrack to properly associate the track with a stream
    stream.getTracks().forEach(t => pc!.addTrack(t, stream!))
    console.log('[host] added tracks via addTrack')
    console.log('[host] stream tracks:', stream.getTracks().map(t => `${t.kind}:${t.readyState}:${t.enabled}`).join(', '))
    console.log('[host] transceivers:', pc.getTransceivers().map(t => `${t.kind}:${t.direction}:${t.currentDirection}:${t.mid}:senderTrack=${t.sender?.track?.kind ?? 'null'}`).join(', '))

    // Create and set answer BEFORE adding ICE candidates
    // Adding candidates before setLocalDescription causes ICE to associate with wrong credentials
    const answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    console.log('[host] answer SDP lines:', answer.sdp?.split('\n').filter(l => l.startsWith('m=')).join(', '))
    console.log('[host] after answer transceivers:', pc.getTransceivers().map(t => `${t.kind}:${t.direction}:${t.currentDirection}:${t.mid}`).join(', '))
    sendToChild('answer', answer)

    // NOW add viewer ICE candidates (after both local and remote descriptions are set)
    // Filter out self-echoed ICE candidates (same machine broadcast issue)
    const localUfrag = pc.localDescription?.sdp?.match(/a=ice-ufrag:(\S+)/)?.[1]
    let addedCount = 0
    let skippedSelf = 0
    console.log('[host] initial pendingIce count:', pendingIce.length, 'localUfrag:', localUfrag)
    for (let i = 0; i < pendingIce.length; i++) {
      const ufrag = pendingIce[i]?.usernameFragment
      if (ufrag && ufrag === localUfrag) {
        skippedSelf++
        continue // Skip self-echoed candidate
      }
      try { await pc.addIceCandidate(pendingIce[i]); addedCount++ }
      catch (e: any) { console.log('[host] FAILED to add viewer ICE:', e.message) }
    }
    console.log('[host] added', addedCount, 'viewer ICE, skipped', skippedSelf, 'self-echoed, iceState:', pc.iceConnectionState)
    iceProcessedCount = pendingIce.length
    // Periodically check for new ICE candidates from hostState
    iceTimer = setInterval(async () => {
      if (!pc || pc.iceConnectionState === 'closed') return
      const st = await props.execute?.('getState')
      const newPending = st?.hostState?.pendingIce
      if (newPending && newPending.length > iceProcessedCount) {
        const localUfrag = pc.localDescription?.sdp?.match(/a=ice-ufrag:(\S+)/)?.[1]
        let added = 0, skipped = 0
        for (let i = iceProcessedCount; i < newPending.length; i++) {
          if (newPending[i]?.usernameFragment && newPending[i].usernameFragment === localUfrag) { skipped++; continue }
          try { await pc.addIceCandidate(newPending[i]); added++ }
          catch (e: any) { console.log('[host] polling FAILED:', e.message) }
        }
        iceProcessedCount = newPending.length
        if (added > 0 || skipped > 0) console.log('[host] polling: added', added, 'skipped', skipped, 'total:', iceProcessedCount, 'iceState:', pc.iceConnectionState)
      }
    }, 200)

    // Diagnostic: check stats after 3s
    setTimeout(async () => {
      if (!pc) return
      try {
        const stats = await pc.getStats()
        let reports: any[] = []
        stats.forEach((report: any) => {
          if (report.type === 'candidate-pair' || report.type === 'inbound-rtp' || report.type === 'outbound-rtp' || report.type === 'transport' || report.type === 'dtls-transport') {
            reports.push(JSON.parse(JSON.stringify(report)))
          }
        })
        console.log('[host] stats at 3s:', JSON.stringify(reports, null, 0).substring(0, 2000))
      } catch (e: any) { console.log('[host] stats error:', e.message) }
    }, 3000)

    console.log('[host] initial iceConnectionState:', pc.iceConnectionState, 'iceGatheringState:', pc.iceGatheringState, 'signalingState:', pc.signalingState)
    pc.oniceconnectionstatechange = () => {
      if (!pc) return
      const st = pc.iceConnectionState
      console.log('[host] ICE state:', st, 'gathering:', pc.iceGatheringState, 'signaling:', pc.signalingState)
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
    pc.onicegatheringstatechange = () => {
      if (!pc) return
      console.log('[host] ICE gathering:', pc.iceGatheringState)
    }
    pc.onconnectionstatechange = () => {
      if (!pc) return
      console.log('[host] connectionState:', pc.connectionState)
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
  if (iceTimer) { clearInterval(iceTimer); iceTimer = null }
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
