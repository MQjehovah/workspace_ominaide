<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { getServer, getAuthHeaders } from './webrtc'

const props = defineProps<{ data?:any; execute?:(a:string,args?:any)=>Promise<any>; refresh?:()=>void; close?:()=>void }>()
const devices = ref<any[]>([])
const hostState = ref<any>({ enabled:false, code:'', status:'', peerConnected:false })
const pairInput = ref('')
const loadingStatus = ref('')
let pollTimer: any = null

async function loadDevices() {
  try {
    const { serverUrl } = await getServer(); const headers = await getAuthHeaders()
    const r = await fetch(`${serverUrl}/api/remote/devices`, { headers }).then(r=>r.json())
    devices.value = r.devices || []
  } catch { loadingStatus.value = '加载设备失败' }
}

function loadHostState() {
  hostState.value = props.data?.hostState || { enabled:false, code:'', status:'', peerConnected:false }
}

function controlDevice(roomId: string) {
  const w = window as any
  if (w.mqbox?.window?.openPage) w.mqbox.window.openPage('remote', `mode=viewer&room=${roomId}`)
}

async function connectByCode() {
  if (!pairInput.value.trim()) return
  try {
    const { serverUrl } = await getServer(); const headers = await getAuthHeaders()
    const r = await fetch(`${serverUrl}/api/remote/pair/${pairInput.value.trim()}`, { headers }).then(resp => { if(!resp.ok) throw new Error('无效或过期'); return resp.json() })
    controlDevice(r.room_id)
    pairInput.value = ''
  } catch (e: any) { loadingStatus.value = e?.message || String(e) }
}

function openControls() {
  loadingStatus.value = '被控管理在主面板的"远程控制"中开启'
}

onMounted(() => {
  loadDevices(); loadHostState()
  pollTimer = setInterval(() => {
    loadDevices(); props.refresh?.(); loadHostState()
  }, 15000)
})
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
</script>

<template>
  <div class="dashboard">
    <div class="header">
      <h2>远程控制</h2>
      <button class="close-btn" @click="props.close?.()">×</button>
    </div>

    <div class="section">
      <div class="section-title">本机</div>
      <div v-if="hostState.enabled" class="host-card">
        <p class="code">配对码: <strong>{{ hostState.code }}</strong></p>
        <p class="hint">{{ hostState.peerConnected ? '主控已连接' : hostState.status || '等待连接' }}</p>
        <button class="btn ghost sm" @click="openControls">在面板管理被控</button>
      </div>
      <div v-else class="host-card disabled">
        <p>被控未开启</p>
        <button class="btn ghost sm" @click="openControls">在面板开启被控</button>
      </div>
    </div>

    <div class="section">
      <div class="section-title">在线设备（同账号）</div>
      <div v-if="devices.length === 0" class="empty">暂无在线设备</div>
      <button v-for="d in devices" :key="d.device_id" class="device" @click="controlDevice(d.room_id)">
        <span class="device-name">{{ d.name }}</span>
        <span class="device-id">{{ d.device_id.slice(0, 6) }}</span>
        <span class="device-action">控制</span>
      </button>
    </div>

    <div class="section">
      <div class="section-title">配对码连接</div>
      <div class="pair-row">
        <input v-model="pairInput" class="input" placeholder="输入 6 位配对码" maxlength="6" @keyup.enter="connectByCode" />
        <button class="btn" @click="connectByCode">连接</button>
      </div>
    </div>

    <p v-if="loadingStatus" class="status-text">{{ loadingStatus }}</p>
  </div>
</template>

<style scoped>
.dashboard { height:100vh; background:#f8f9fa; font-family:-apple-system,sans-serif; overflow-y:auto; }
.header { display:flex; align-items:center; justify-content:space-between; padding:16px 24px; border-bottom:1px solid #e9ecef; position:sticky; top:0; background:#f8f9fa; z-index:10; }
.header h2 { margin:0; font-size:18px; font-weight:600; color:#212529; }
.close-btn { width:32px;height:32px;border:none;border-radius:8px;background:transparent;color:#868e96;font-size:20px;cursor:pointer; display:flex;align-items:center;justify-content:center; }
.close-btn:hover { background:#ffebee;color:#e91e63; }

.section { background:#fff; margin:12px 16px; border:1px solid #e9ecef; border-radius:12px; padding:16px; }
.section-title { font-size:13px; font-weight:600; color:#495057; margin-bottom:12px; }
.host-card { text-align:center; padding:12px; }
.host-card.disabled { color:#adb5bd; }
.code { font-size:22px; font-weight:700; color:#e91e63; margin:0 0 6px; letter-spacing:2px; }
.hint { font-size:12px; color:#868e96; margin:0 0 10px; }
.btn.ghost { background:#f1f3f5; color:#495057; border:none; border-radius:8px; padding:6px 14px; font-size:12px; cursor:pointer; }
.btn.ghost:hover { background:#e9ecef; }
.btn.ghost.sm { padding:4px 10px; font-size:11px; }

.empty { font-size:12px; color:#adb5bd; text-align:center; padding:16px 0; }
.device { width:100%; display:flex; align-items:center; padding:10px 12px; border:1px solid #e9ecef; border-radius:10px; background:#fff; cursor:pointer; margin-bottom:6px; gap:8px; }
.device:hover { border-color:#e91e63; background:#fce4ec; }
.device-name { flex:1; font-size:13px; font-weight:500; color:#212529; }
.device-id { font-size:11px; color:#adb5bd; font-family:monospace; }
.device-action { font-size:11px; color:#e91e63; font-weight:500; }

.pair-row { display:flex; gap:8px; }
.input { flex:1; height:36px; padding:0 12px; border:1px solid #dee2e6; border-radius:8px; font-size:13px; outline:none; }
.input:focus { border-color:#e91e63; }
.btn { height:36px; padding:0 16px; border:none; border-radius:8px; background:#fce4ec; color:#e91e63; font-size:12px; font-weight:500; cursor:pointer; }
.btn:hover { background:#f8bbd0; }

.status-text { text-align:center; font-size:11px; color:#868e96; margin:8px 16px; }
</style>
