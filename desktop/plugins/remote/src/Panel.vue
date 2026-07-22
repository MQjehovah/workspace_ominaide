<script setup lang="ts">
import { ref } from 'vue'
import { openSignal, newPeer, getServer, getAuthHeaders } from './webrtc'

const props = defineProps<{ data: any; execute: (a: string, args?: any) => Promise<any>; openPage: () => void; refresh: () => Promise<void> }>()

const hosting = ref(false)
const status = ref('')
const pairCode = ref('')
let ws: WebSocket | null = null
let pc: RTCPeerConnection | null = null
let stream: MediaStream | null = null
let pendingIce: any[] = []
let currentRoomId = ''
let cachedScreen: { width: number; height: number } | null = null
let lastMoveTs = 0
let pendingMove: any = null
let moveScheduled = false

async function getScreen(): Promise<{ width: number; height: number }> {
  if (cachedScreen) return cachedScreen
  cachedScreen = await (window as any).mqbox.remote.getScreenSize()
  return cachedScreen!
}

async function handleInput(ev: any) {
  try {
    if (ev.type === 'mouseMove') {
      pendingMove = ev
      const now = Date.now()
      if (now - lastMoveTs >= 16 && !moveScheduled) {
        lastMoveTs = now
        moveScheduled = true
        const s = await getScreen()
        const m = pendingMove
        const x = Math.round((Number(m.x) || 0) * s.width)
        const y = Math.round((Number(m.y) || 0) * s.height)
        await (window as any).mqbox.remote.injectInput({ type: 'mouseMove', x, y })
        moveScheduled = false
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
    const roomId = `u${me.id}_d${deviceId}`
    currentRoomId = roomId
    await fetch(`${serverUrl}/api/remote/online`, {
      method: 'POST', headers,
      body: JSON.stringify({ device_id: deviceId, name: '我的电脑', room_id: roomId }),
    })
    ws = await openSignal(roomId, onSignal)
    ws.onclose = () => {
      hosting.value = false
      status.value = status.value || '信令断开'
      if (pc) { try { pc.close() } catch {} ; pc = null }
      if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
    }
    ws.onerror = () => { status.value = '信令错误' }
    ws.send(JSON.stringify({ type: 'join' }))
    hosting.value = true
    status.value = '允许控制中（等待主控连接）'
  } catch (e: any) {
    status.value = '失败: ' + (e?.message || e)
  }
}

async function onSignal(m: any) {
  if (m.type === 'offer') {
    try {
      if (pc) { try { pc.close() } catch {} ; pc = null }
      if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
      pendingIce = []
      const sources = await (window as any).mqbox.remote.getDesktopSources()
      if (!sources.length) { status.value = '无屏幕源'; return }
      stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { mandatory: { chromeMediaSource: 'desktop', chromeMediaSourceId: sources[0].id, maxFrameRate: 30 } } as any,
      })
      pc = newPeer()
      pc.ondatachannel = (e) => {
        const dc = e.channel
        dc.onmessage = async (msg) => {
          try {
            const ev = JSON.parse(msg.data)
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
      ws!.send(JSON.stringify({ type: 'answer', payload: answer.toJSON() }))
      pc.onicecandidate = (e) => { if (e.candidate) ws!.send(JSON.stringify({ type: 'ice', payload: e.candidate.toJSON() })) }
      status.value = '主控已连接，推流中'
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

async function stopHost() {
  if (pc) { pc.close(); pc = null }
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
  if (ws) { ws.close(); ws = null }
  if (currentRoomId) {
    try {
      const { serverUrl } = await getServer()
      const headers = await getAuthHeaders()
      await fetch(`${serverUrl}/api/remote/online`, { method: 'DELETE', headers })
    } catch {}
  }
  currentRoomId = ''
  hosting.value = false
  status.value = ''
  pairCode.value = ''
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
</script>

<template>
  <div class="panel">
    <div class="panel-hd"><span class="title">远程控制</span></div>
    <button v-if="!hosting" class="btn" @click="startHost">允许控制本机</button>
    <template v-else>
      <button class="btn danger" @click="stopHost">停止控制</button>
      <button class="btn" @click="genPair" style="margin-top:6px">生成配对码</button>
    </template>
    <p v-if="status" class="status">{{ status }}</p>
    <p v-if="pairCode" class="code">{{ pairCode }}</p>
  </div>
</template>

<style scoped>
.panel { background:#fff; border-radius:10px; border:1px solid #e8e8e8; padding:12px; }
.panel-hd { margin-bottom:8px; }
.title { font-size:13px; font-weight:600; }
.btn { width:100%; padding:8px; border:none; border-radius:8px; background:#fce4ec; color:#e91e63; font-size:12px; cursor:pointer; }
.btn:hover { background:#f8bbd0; }
.btn.danger { background:#ffebee; color:#c62828; }
.btn.danger:hover { background:#ffcdd2; }
.status { font-size:11px; color:#666; margin:8px 0 0; }
.code { font-size:20px; font-weight:700; color:#e91e63; text-align:center; margin:6px 0 0; letter-spacing:2px; }
</style>
