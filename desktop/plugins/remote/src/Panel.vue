<script setup lang="ts">
import { ref } from 'vue'
import { openSignal, newPeer, getServer, getAuthHeaders, getIceServers } from './webrtc'

const props = defineProps<{ data: any; execute: (a: string, args?: any) => Promise<any>; openPage: () => void; refresh: () => Promise<void> }>()

const hosting = ref(false)
const hostingEnabled = ref(localStorage.getItem('remote_hostEnabled') === '1')
const status = ref('')
const pairCode = ref('')
const pendingRequest = ref<{ name: string } | null>(null)
const hasPeer = ref(false)
const autoAccept = ref(localStorage.getItem('remote_autoAccept') === 'true')
function toggleAutoAccept() {
  if (autoAccept.value) localStorage.setItem('remote_autoAccept', 'true')
  else localStorage.removeItem('remote_autoAccept')
}
let ws: WebSocket | null = null
let pc: RTCPeerConnection | null = null
let stream: MediaStream | null = null
let pendingIce: any[] = []
let currentRoomId = ''
let lastMoveTs = 0
let pendingMove: any = null
let moveScheduled = false
let trailingTimer: any = null
let heartbeatTimer: any = null
let currentDisplay: any = null
let currentSourceId = ''
let codeTimer: any = null

async function flushMove() {
  if (!pendingMove || !currentDisplay) return
  const m = pendingMove
  pendingMove = null
  const d = currentDisplay
  const sf = d.scaleFactor || 1
  const x = Math.round((d.bounds.x + (Number(m.x) || 0) * d.bounds.width) * sf)
  const y = Math.round((d.bounds.y + (Number(m.y) || 0) * d.bounds.height) * sf)
  await (window as any).mqbox.remote.injectInput({ type: 'mouseMove', x, y })
}

async function handleInput(ev: any) {
  try {
    if (ev.type === 'mouseMove') {
      pendingMove = ev
      const now = Date.now()
      if (now - lastMoveTs >= 16 && !moveScheduled) {
        lastMoveTs = now
        moveScheduled = true
        await flushMove()
        moveScheduled = false
      } else if (!trailingTimer) {
        trailingTimer = setTimeout(async () => {
          trailingTimer = null
          lastMoveTs = Date.now()
          await flushMove()
        }, 16)
      }
    } else if (ev.type === 'mouseDown' || ev.type === 'mouseUp' || ev.type === 'wheel' || ev.type === 'keyDown' || ev.type === 'keyUp') {
      await (window as any).mqbox.remote.injectInput(ev)
    }
  } catch {}
}

async function startHost() {
  if (hosting.value) return
  try {
    status.value = '上线中…'
    const { serverUrl } = await getServer()
    const headers = await getAuthHeaders()
    const deviceId = await props.execute('getDeviceId')
    const me = await fetch(`${serverUrl}/api/auth/me`, { headers }).then(r => r.json())
    const hostName = await props.execute('getHostName')
    const roomId = `u${me.id}_d${deviceId}`
    currentRoomId = roomId
    await fetch(`${serverUrl}/api/remote/online`, {
      method: 'POST', headers,
      body: JSON.stringify({ device_id: deviceId, name: hostName, room_id: roomId }),
    })
    ws = await openSignal(roomId, onSignal)
    ws.onclose = () => {
      hosting.value = false
      status.value = status.value || '信令断开'
      if (pc) { try { pc.close() } catch {} ; pc = null }
      if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
      if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null }
      hasPeer.value = false
      pendingRequest.value = null
      // Auto-retry if user still wants hosting
      if (hostingEnabled.value) {
        setTimeout(async () => {
          if (!hosting.value && hostingEnabled.value) await startHost()
        }, 3000)
      }
    }
    ws.onerror = () => { status.value = '信令错误' }
    ws.send(JSON.stringify({ type: 'join' }))
    hosting.value = true
    hostingEnabled.value = true
    status.value = '允许控制中（等待主控连接）'
    heartbeatTimer = setInterval(async () => {
      try {
        const { serverUrl } = await getServer()
        const headers = await getAuthHeaders()
        await fetch(`${serverUrl}/api/remote/heartbeat`, { method: 'POST', headers, body: JSON.stringify({ device_id: deviceId }) })
      } catch {}
    }, 30000)
    await genPairAuto(deviceId)
  } catch (e: any) {
    status.value = '失败: ' + (e?.message || e)
  }
}

async function onSignal(m: any) {
  if (m.type === 'requestControl') {
    if (pc || hasPeer.value) {
      ws?.send(JSON.stringify({ type: 'controlDenied', reason: 'busy' }))
    } else if (autoAccept.value) {
      ws?.send(JSON.stringify({ type: 'controlAllowed' }))
      status.value = `已接受 ${m.name || '未知设备'} 的请求`
    } else {
      pendingRequest.value = { name: m.name || '未知设备' }
    }
    return
  }
  if (m.type === 'offer') {
    try {
      if (pc) { try { pc.close() } catch {} ; pc = null }
      if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
      pendingIce = []
      const sources = await (window as any).mqbox.remote.getDesktopSources()
      if (!sources.length) { status.value = '无屏幕源'; return }
      const allDisplays = await (window as any).mqbox.remote.getAllDisplays()
      currentDisplay = matchDisplay(sources[0], allDisplays)
      currentSourceId = sources[0].id
      stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { mandatory: { chromeMediaSource: 'desktop', chromeMediaSourceId: sources[0].id, maxFrameRate: 30 } } as any,
      })
      pc = newPeer(await getIceServers())
      pc.ondatachannel = (e) => {
        const dc = e.channel
        dc.onopen = () => {
          try {
            ;(window as any).mqbox.remote.getDesktopSources().then((srcs: any[]) => {
              dc.send(JSON.stringify({ type: 'screens', list: srcs.map(s => ({ id: s.id, name: s.name })) }))
              dc.send(JSON.stringify({ type: 'activeScreen', id: currentSourceId }))
            })
          } catch {}
        }
        dc.onmessage = async (msg) => {
          try {
            const ev = JSON.parse(msg.data)
            if (ev.type === 'switchScreen') { await switchScreen(ev.sourceId, dc); return }
            await handleInput(ev)
          } catch {}
        }
      }
      stream.getTracks().forEach(t => pc!.addTrack(t, stream!))
      await pc.setRemoteDescription({ type: 'offer', sdp: m.payload.sdp })
      for (const c of pendingIce) { try { await pc.addIceCandidate(c) } catch {} }
      pendingIce = []
      const answer = await pc.createAnswer()
      await pc.setLocalDescription(answer)
      ws!.send(JSON.stringify({ type: 'answer', payload: answer }))
      pc.onicecandidate = (e) => { if (e.candidate) ws!.send(JSON.stringify({ type: 'ice', payload: e.candidate })) }
      pc.oniceconnectionstatechange = () => {
        if (pc && (pc.iceConnectionState === 'failed' || pc.iceConnectionState === 'closed')) {
          if (pc) { try { pc.close() } catch {} ; pc = null }
          if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
          hasPeer.value = false
          pendingIce = []
          status.value = '主控已断开（仍允许新连接）'
          props.execute('syncHostState', { peerConnected: false })
        }
      }
      hasPeer.value = true
      status.value = '主控已连接，推流中'
      props.execute('syncHostState', { peerConnected: true })
    } catch (e: any) {
      status.value = '建立连接失败: ' + (e?.message || e)
      try { ws?.send(JSON.stringify({ type: 'error', message: 'host_getusermedia_failed' })) } catch {}
    }
  } else if (m.type === 'ice') {
    if (pc && pc.remoteDescription) {
      try { await pc.addIceCandidate(m.payload) } catch {}
    } else {
      pendingIce.push(m.payload)
    }
  }
}

function allowControl() {
  pendingRequest.value = null
  ws?.send(JSON.stringify({ type: 'controlAllowed' }))
}

function denyControl() {
  pendingRequest.value = null
  ws?.send(JSON.stringify({ type: 'controlDenied' }))
}

function revokePeer() {
  try { ws?.send(JSON.stringify({ type: 'revoked' })) } catch {}
  if (pc) { try { pc.close() } catch {} ; pc = null }
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
  hasPeer.value = false
  pendingIce = []
  status.value = '已断开控制（仍允许新连接）'
  props.execute('syncHostState', { peerConnected: false })
}

async function stopHost() {
  try { ws?.send(JSON.stringify({ type: 'revoked' })) } catch {}
  if (pc) { pc.close(); pc = null }
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
  if (ws) { ws.close(); ws = null }
  if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null }
  if (codeTimer) { clearInterval(codeTimer); codeTimer = null }
  if (currentRoomId) {
    try {
      const { serverUrl } = await getServer()
      const headers = await getAuthHeaders()
      await fetch(`${serverUrl}/api/remote/online`, { method: 'DELETE', headers })
    } catch {}
  }
  currentRoomId = ''
  hosting.value = false
  hostingEnabled.value = false
  status.value = ''
  pairCode.value = ''
  await props.execute('syncHostState', { enabled: false, code: '', status: '', peerConnected: false })
}

async function genPair() {
  try {
    const { serverUrl } = await getServer()
    const headers = await getAuthHeaders()
    const r = await fetch(`${serverUrl}/api/remote/pair`, {
      method: 'POST', headers,
      body: JSON.stringify({ device_id: await props.execute('getDeviceId'), room_id: currentRoomId }),
    }).then(r => r.json())
    pairCode.value = r.code
    status.value = `配对码: ${r.code}（5 分钟有效）`
  } catch (e: any) {
    status.value = '生成配对码失败: ' + (e?.message || e)
  }
}

async function genPairAuto(deviceId: string) {
  try {
    const { serverUrl } = await getServer()
    const headers = await getAuthHeaders()
    const r = await fetch(`${serverUrl}/api/remote/pair`, {
      method: 'POST', headers,
      body: JSON.stringify({ device_id: deviceId, room_id: currentRoomId }),
    }).then(res => res.json())
    pairCode.value = r.code
    status.value = `配对码: ${r.code}（允许控制中）`
    await props.execute('syncHostState', { enabled: true, code: r.code, status: '允许控制中' })
    if (codeTimer) clearInterval(codeTimer)
    codeTimer = setInterval(() => genPairAuto(deviceId), 240000)
  } catch (e: any) {
    status.value = '生成配对码失败: ' + (e?.message || e)
  }
}

async function switchScreen(sourceId: string, dc: any) {
  try {
    const newStream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { mandatory: { chromeMediaSource: 'desktop', chromeMediaSourceId: sourceId, maxFrameRate: 30 } } as any,
    })
    const sender = pc?.getSenders().find((s: any) => s.track && s.track.kind === 'video')
    if (sender && pc) await sender.replaceTrack(newStream.getVideoTracks()[0])
    if (stream) stream.getTracks().forEach(t => t.stop())
    stream = newStream
    currentSourceId = sourceId
    const allDisplays = await (window as any).mqbox.remote.getAllDisplays()
    const srcs = await (window as any).mqbox.remote.getDesktopSources()
    currentDisplay = matchDisplay(srcs.find((s: any) => s.id === sourceId), allDisplays)
    dc.send(JSON.stringify({ type: 'activeScreen', id: sourceId }))
  } catch (e: any) {
    status.value = '切屏失败: ' + (e?.message || e)
  }
}

function matchDisplay(src: any, displays: any[]) {
  if (!src) return displays[0] || null
  return displays.find((d: any) => String(d.id) === String(src.display_id)) || displays[0] || null
}

function openManagement() {
  ;(props as any).openPage?.('remote') || (window as any).mqbox?.window?.openPage?.('remote')
}

async function toggleHost() {
  localStorage.setItem('remote_hostEnabled', hostingEnabled.value ? '1' : '0')
  if (hostingEnabled.value) { await startHost() } else { await stopHost() }
}

if (hostingEnabled.value) {
  setTimeout(async () => { if (!hosting.value) await startHost() }, 1500)
}
</script>

<template>
  <div class="panel">
    <div class="panel-hd">
      <span class="title">远程控制</span>
      <button class="panel-arrow" @click="openPage">›</button>
    </div>

    <div class="host-row">
      <span class="host-label" :class="{ active: hosting }">允许控制本机</span>
      <label class="switch">
        <input type="checkbox" v-model="hostingEnabled" @change="toggleHost" />
        <span class="slider"></span>
      </label>
    </div>

    <div v-if="pairCode" class="code-block">
      <span class="code-label">配对码</span>
      <span class="code-num">{{ pairCode }}</span>
    </div>

    <div class="host-row" v-if="hosting">
      <span class="host-label" :class="{ active: autoAccept }">自动接受</span>
      <label class="switch">
        <input type="checkbox" v-model="autoAccept" @change="toggleAutoAccept" />
        <span class="slider"></span>
      </label>
    </div>

    <p v-if="status" class="status">{{ status }}</p>

    <div v-if="pendingRequest" class="confirm">
      <p>{{ pendingRequest.name }} 请求控制本机</p>
      <div class="confirm-row">
        <button class="confirm-btn allow" @click="allowControl">允许</button>
        <button class="confirm-btn deny" @click="denyControl">拒绝</button>
      </div>
    </div>

    <button v-if="hasPeer" class="revoke-btn" @click="revokePeer">断开控制</button>
  </div>
</template>

<style scoped>
.panel { background:#fff; border-radius:10px; border:1px solid #e8e8e8; padding:12px; }
.panel-hd { display:flex; align-items:center; justify-content:space-between; margin-bottom:10px; }
.title { font-size:13px; font-weight:600; color:#1e1e1e; }
.panel-arrow { width:24px;height:24px;border:none;border-radius:6px;background:transparent;color:#ccc;cursor:pointer;font-size:18px;line-height:1;display:flex;align-items:center;justify-content:center; }
.panel-arrow:hover { background:#f5f5f5;color:#666; }

.host-row { display:flex; align-items:center; justify-content:space-between; padding:8px 0; }
.host-label { font-size:12px; color:#868e96; }
.host-label.active { color:#e91e63; }

.switch { position:relative; display:inline-block; width:36px; height:20px; flex-shrink:0; }
.switch input { opacity:0; width:0; height:0; }
.slider { position:absolute; cursor:pointer; inset:0; background:#dee2e6; border-radius:10px; transition:.2s; }
.slider::before { content:''; position:absolute; height:16px; width:16px; left:2px; bottom:2px; background:#fff; border-radius:50%; transition:.2s; }
input:checked + .slider { background:#e91e63; }
input:checked + .slider::before { transform:translateX(16px); }

.code-block { display:flex; align-items:center; gap:6px; padding:6px 0; }
.code-label { font-size:11px; color:#adb5bd; }
.code-num { font-size:16px; font-weight:700; color:#e91e63; letter-spacing:1.5px; }

.status { font-size:11px; color:#868e96; margin:4px 0; }
.confirm { border:1px solid #e8e8e8; border-radius:8px; padding:10px; margin-top:6px; background:#fafafa; }
.confirm p { margin:0 0 8px; font-size:12px; color:#333; font-weight:500; }
.confirm-row { display:flex; gap:8px; }
.confirm-btn { flex:1; height:32px; border:none; border-radius:8px; font-size:12px; cursor:pointer; }
.confirm-btn.allow { background:#fce4ec; color:#e91e63; }
.confirm-btn.allow:hover { background:#f8bbd0; }
.confirm-btn.deny { background:#f1f3f5; color:#495057; }
.confirm-btn.deny:hover { background:#e9ecef; }

.revoke-btn { width:100%; margin-top:6px; padding:6px; border:none; border-radius:8px; background:#ffebee; color:#c62828; font-size:11px; cursor:pointer; }
.revoke-btn:hover { background:#ffcdd2; }
</style>
