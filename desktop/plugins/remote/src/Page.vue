<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { openSignal, newPeer, getServer, getAuthHeaders } from './webrtc'

defineProps<{ data: any; execute: (a: string, args?: any) => Promise<any>; refresh?: () => void; close: () => void }>()

const mode = ref<'menu' | 'viewer'>('menu')
const devices = ref<any[]>([])
const videoRef = ref<HTMLVideoElement | null>(null)
const status = ref('')
const pairInput = ref('')
let ws: WebSocket | null = null
let pc: RTCPeerConnection | null = null
let pendingIce: any[] = []

async function loadDevices() {
  try {
    const { serverUrl } = await getServer()
    const headers = await getAuthHeaders()
    const d = await fetch(`${serverUrl}/api/remote/devices`, { headers }).then(r => r.json())
    devices.value = d.devices || []
  } catch (e: any) {
    status.value = '加载设备失败: ' + (e?.message || e)
  }
}

async function connect(roomId: string) {
  mode.value = 'viewer'
  status.value = '连接中…'
  ws = await openSignal(roomId, onSignal)
  ws.onclose = () => { status.value = status.value || '信令断开'; cleanup() }
  ws.onerror = () => { status.value = '信令错误' }
  ws.send(JSON.stringify({ type: 'join' }))
  pc = newPeer()
  pc.ontrack = (e) => { if (videoRef.value) videoRef.value.srcObject = e.streams[0]; status.value = '已连接' }
  pc.onicecandidate = (e) => { if (e.candidate) ws!.send(JSON.stringify({ type: 'ice', payload: e.candidate.toJSON() })) }
  const offer = await pc.createOffer()
  await pc.setLocalDescription(offer)
  ws.send(JSON.stringify({ type: 'offer', payload: offer.toJSON() }))
}

async function onSignal(m: any) {
  if (m.type === 'answer' && pc) {
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

async function connectByCode() {
  if (!pairInput.value.trim()) return
  try {
    const { serverUrl } = await getServer()
    const headers = await getAuthHeaders()
    const r = await fetch(`${serverUrl}/api/remote/pair/${pairInput.value.trim()}`, { headers }).then(resp => {
      if (!resp.ok) throw new Error('配对码无效或已过期')
      return resp.json()
    })
    await connect(r.room_id)
  } catch (e: any) {
    status.value = e?.message || String(e)
  }
}

function cleanup() {
  if (pc) { try { pc.close() } catch {} ; pc = null }
  pendingIce = []
}

function backToMenu() {
  cleanup()
  if (ws) { try { ws.close() } catch {} ; ws = null }
  mode.value = 'menu'
  status.value = ''
  loadDevices()
}

onMounted(loadDevices)
</script>

<template>
  <div class="page">
    <div class="header">
      <h2>远程控制</h2>
      <button v-if="mode === 'viewer'" class="back" @click="backToMenu">返回</button>
      <button class="close-btn" @click="close">×</button>
    </div>

    <div v-if="mode === 'menu'" class="menu">
      <div class="section">
        <div class="section-title">我的设备（同账号在线被控端）</div>
        <div v-if="devices.length === 0" class="empty">暂无在线设备</div>
        <button v-for="d in devices" :key="d.device_id" class="device" @click="connect(d.room_id)">
          <span class="device-name">{{ d.name }}</span>
          <span class="device-id">{{ d.device_id.slice(0, 6) }}</span>
        </button>
      </div>
      <div class="section">
        <div class="section-title">配对码连接</div>
        <div class="pair-row">
          <input v-model="pairInput" class="input" placeholder="输入 6 位配对码" maxlength="6" @keyup.enter="connectByCode" />
          <button class="btn" @click="connectByCode">连接</button>
        </div>
      </div>
      <p class="hint">被控端需在面板点"允许控制本机"并生成配对码</p>
    </div>

    <div v-else class="viewer">
      <video ref="videoRef" autoplay playsinline class="video"></video>
      <p v-if="status" class="status">{{ status }}</p>
    </div>
  </div>
</template>

<style scoped>
.page { height: 100vh; background: #f8f9fa; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
.header { display: flex; align-items: center; gap: 12px; padding: 16px 24px; border-bottom: 1px solid #e9ecef; position: relative; }
.header h2 { margin: 0; font-size: 18px; font-weight: 600; color: #212529; }
.back { margin-left: auto; height: 32px; padding: 0 14px; border: none; border-radius: 8px; background: #f1f3f5; color: #495057; font-size: 12px; cursor: pointer; }
.back:hover { background: #e9ecef; }
.close-btn { width: 32px; height: 32px; border: none; border-radius: 8px; background: transparent; color: #868e96; font-size: 20px; line-height: 1; cursor: pointer; display: flex; align-items: center; justify-content: center; }
.close-btn:hover { background: #ffebee; color: #e91e63; }

.menu { padding: 24px; display: flex; flex-direction: column; gap: 20px; max-width: 560px; margin: 0 auto; }
.section { background: #fff; border: 1px solid #e9ecef; border-radius: 12px; padding: 16px; }
.section-title { font-size: 13px; font-weight: 600; color: #495057; margin-bottom: 12px; }
.empty { font-size: 12px; color: #adb5bd; text-align: center; padding: 16px 0; }
.device { width: 100%; display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; margin-bottom: 6px; border: 1px solid #e9ecef; border-radius: 10px; background: #fff; cursor: pointer; transition: all 0.15s; }
.device:hover { border-color: #e91e63; background: #fce4ec; }
.device-name { font-size: 13px; font-weight: 500; color: #212529; }
.device-id { font-size: 11px; color: #adb5bd; font-family: monospace; }

.pair-row { display: flex; gap: 8px; }
.input { flex: 1; height: 36px; padding: 0 12px; border: 1px solid #dee2e6; border-radius: 8px; font-size: 13px; outline: none; transition: border-color 0.15s; }
.input:focus { border-color: #e91e63; }
.btn { height: 36px; padding: 0 16px; border: none; border-radius: 8px; background: #fce4ec; color: #e91e63; font-size: 12px; font-weight: 500; cursor: pointer; transition: background 0.15s; }
.btn:hover { background: #f8bbd0; }

.hint { font-size: 11px; color: #adb5bd; margin: 4px 0 0; text-align: center; }

.viewer { position: relative; height: calc(100vh - 65px); background: #212529; display: flex; align-items: center; justify-content: center; }
.video { width: 100%; height: 100%; object-fit: contain; }
.status { position: absolute; top: 16px; left: 50%; transform: translateX(-50%); margin: 0; padding: 6px 14px; background: rgba(0, 0, 0, 0.6); color: #fff; font-size: 12px; border-radius: 16px; }
</style>
