<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import WebrtcAccept from './WebrtcAccept.vue'
import ViewerSession from './ViewerSession.vue'

const props = defineProps<{ data?:any; execute?:(a:string,args?:any)=>Promise<any>; refresh?:()=>void; close?:()=>void }>()
const params = new URLSearchParams(window.location.search)
const mode = params.get('mode') || ''
const isViewer = mode === 'viewer'
const isWebrtcAccept = mode === 'webrtc-accept'
const roomId = params.get('room') || ''

const hostEnabled = ref(false)
const hostCode = ref('')
const hostStatus = ref('')
const peerConnected = ref(false)
const autoAccept = ref(false)
const devices = ref<any[]>([])
const localDeviceId = ref('')
const pairInput = ref('')
const loadingStatus = ref('')
const starting = ref(false)

let pollTimer: any = null
let emptyCount = 0

function loadState() {
  const st = props.data?.hostState
  if (st) {
    hostEnabled.value = st.enabled || false
    hostCode.value = st.code || ''
    hostStatus.value = st.status || ''
    peerConnected.value = st.peerConnected || false
    autoAccept.value = st.autoAccept || false
  }
  starting.value = false
}

async function loadDevices() {
  try {
    const [r, myId] = await Promise.all([
      props.execute?.('getDevices'),
      props.execute?.('getDeviceId'),
    ])
    localDeviceId.value = myId || ''
    const list: any[] = r?.devices || []
    list.forEach(d => d.isLocal = d.device_id === myId)
    if (list.length === 0 && devices.value.length > 0) {
      emptyCount++
      ;(window as any).mqbox?.log?.write('remote', 'warn', `device list empty (${emptyCount}/3)`)
      if (emptyCount < 3) return
    }
    emptyCount = 0
    devices.value = list
  } catch (e: any) {
    ;(window as any).mqbox?.log?.write('remote', 'error', `loadDevices error: ${e?.message}`)
  }
}

async function toggleHost() {
  starting.value = true
  if (hostEnabled.value) {
    await props.execute?.('stopHost')
  } else {
    await props.execute?.('startHost')
  }
  await props.refresh?.()
  loadState()
}

function toggleAutoAccept() {
  const newVal = !autoAccept.value
  props.execute?.('setAutoAccept', { enabled: newVal })
  autoAccept.value = newVal
}

function controlDevice(roomId: string) {
  ;(window as any).mqbox?.window?.openPage('remote', `mode=viewer&room=${roomId}`)
}

async function connectByCode() {
  if (!pairInput.value.trim()) return
  try {
    const r = await props.execute?.('connectByCode', { code: pairInput.value.trim() })
    if (r?.room_id) {
      controlDevice(r.room_id)
      pairInput.value = ''
    } else {
      loadingStatus.value = '配对码无效或已过期'
    }
  } catch (e: any) {
    loadingStatus.value = e?.message || '连接失败'
  }
}

async function refreshAll() {
  await props.refresh?.()
  loadState()
  await loadDevices()
}

onMounted(() => {
  refreshAll()
  pollTimer = setInterval(refreshAll, 5000)
})

onUnmounted(() => {
  clearInterval(pollTimer)
})
</script>

<template>
  <WebrtcAccept v-if="isWebrtcAccept" v-bind="$props" />
  <ViewerSession v-else-if="isViewer" v-bind="$props" :room="roomId" />
  <div v-else class="dashboard">
    <div class="header">
      <h2>远程控制</h2>
      <div class="header-right">
        <span v-if="peerConnected" class="badge connected">已连接</span>
        <button class="close-btn" @click="props.close?.()">✕</button>
      </div>
    </div>

    <div class="section">
      <div class="host-row">
        <div class="host-info">
          <div class="host-label">允许控制本机</div>
          <div class="host-desc">后台常驻，关闭此页面不影响连接</div>
        </div>
        <label class="switch">
          <input type="checkbox" :checked="hostEnabled" :disabled="starting" @change="toggleHost">
          <span class="switch-slider"></span>
        </label>
      </div>

      <div v-if="hostEnabled" class="code-area">
        <div class="code-label">你的配对码</div>
        <div class="code-display">{{ hostCode || '获取中…' }}</div>
        <div class="code-status">{{ hostStatus }}</div>
        <label class="auto-accept">
          <input type="checkbox" :checked="autoAccept" @change="toggleAutoAccept">
          <span>自动接受连接请求</span>
        </label>
      </div>
    </div>

    <div class="section">
      <div class="section-title">在线设备（同账号）</div>
      <div v-if="devices.length === 0" class="empty">暂无在线设备</div>
      <button v-for="d in devices" :key="d.device_id" class="device" :class="{ local: d.isLocal }" @click="controlDevice(d.room_id)">
        <span class="dev-icon">🖥</span>
        <span class="dev-name">{{ d.name }}</span>
        <span class="dev-badge" v-if="d.isLocal">本机</span>
        <span class="dev-id" v-else>{{ d.device_id.slice(0, 6) }}</span>
      </button>
    </div>

    <div class="section">
      <div class="section-title">连接其他设备</div>
      <div class="pair-row">
        <input v-model="pairInput" class="input" placeholder="输入对方的 6 位配对码" maxlength="6" @keyup.enter="connectByCode" />
        <button class="btn" @click="connectByCode">连接</button>
      </div>
    </div>

    <p v-if="loadingStatus" class="status-text">{{ loadingStatus }}</p>
  </div>
</template>

<style scoped>
.dashboard { height:100vh; background:#f5f5f5; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; overflow-y:auto; }
.header { display:flex; align-items:center; justify-content:space-between; padding:14px 20px; border-bottom:1px solid #e8e8e8; position:sticky; top:0; background:#fff; z-index:10; }
.header h2 { margin:0; font-size:17px; font-weight:600; color:#1a1a1a; }
.header-right { display:flex; align-items:center; gap:10px; }
.badge { font-size:11px; padding:2px 10px; border-radius:10px; font-weight:500; }
.badge.connected { background:#e6f7e6; color:#28A745; }
.close-btn { width:30px;height:30px;border:none;border-radius:8px;background:transparent;color:#909399;font-size:16px;cursor:pointer; display:flex;align-items:center;justify-content:center; }
.close-btn:hover { background:#f5f5f5;color:#333; }

.section { background:#fff; margin:10px 14px; border:1px solid #e8e8e8; border-radius:10px; padding:14px; }
.host-row { display:flex; align-items:center; justify-content:space-between; }
.host-info { flex:1; }
.host-label { font-size:15px; font-weight:600; color:#1a1a1a; }
.host-desc { font-size:11px; color:#909399; margin-top:2px; }

.switch { position:relative; width:44px; height:24px; flex-shrink:0; }
.switch input { opacity:0; width:0; height:0; }
.switch-slider { position:absolute; inset:0; background:#ccc; border-radius:12px; cursor:pointer; transition:background .2s; }
.switch-slider::before { content:''; position:absolute; left:3px; top:3px; width:18px; height:18px; border-radius:9px; background:#fff; transition:transform .2s; }
.switch input:checked + .switch-slider { background:#0078D4; }
.switch input:checked + .switch-slider::before { transform:translateX(20px); }
.switch input:disabled + .switch-slider { opacity:0.5; }

.code-area { border-top:1px solid #e8e8e8; margin-top:14px; padding-top:14px; text-align:center; }
.code-label { font-size:12px; color:#909399; margin-bottom:8px; }
.code-display { font-size:32px; font-weight:700; color:#0078D4; letter-spacing:6px; font-family:'SF Mono',Consolas,monospace; margin-bottom:4px; }
.code-status { font-size:12px; color:#909399; margin-bottom:10px; }
.auto-accept { display:flex; align-items:center; justify-content:center; gap:6px; cursor:pointer; font-size:12px; color:#606266; }
.auto-accept input { width:14px;height:14px; }

.section-title { font-size:13px; font-weight:600; color:#303133; margin-bottom:8px; }
.empty { font-size:12px; color:#c0c4cc; text-align:center; padding:14px 0; }
.device { width:100%; display:flex; align-items:center; padding:10px 12px; border:1px solid #e8e8e8; border-radius:8px; background:#fff; cursor:pointer; margin-bottom:6px; gap:8px; }
.device:hover { background:#f5f7fa; border-color:#0078D4; }
.device.local { background:#f8f9fa; border-color:#e0e0e0; }
.device.local:hover { border-color:#0078D4; background:#f0f4ff; }
.dev-icon { font-size:16px; }
.dev-name { flex:1; font-size:13px; font-weight:500; color:#1a1a1a; }
.dev-badge { font-size:10px; color:#0078D4; background:#e8f4fd; padding:1px 7px; border-radius:8px; font-weight:500; }
.dev-id { font-size:11px; color:#c0c4cc; font-family:monospace; }

.pair-row { display:flex; gap:8px; }
.input { flex:1; height:36px; padding:0 12px; border:1px solid #dcdfe6; border-radius:8px; font-size:13px; outline:none; }
.input:focus { border-color:#0078D4; }
.btn { height:36px; padding:0 18px; border:none; border-radius:8px; background:#0078D4; color:#fff; font-size:13px; font-weight:500; cursor:pointer; }
.btn:hover { background:#106ebe; }

.status-text { text-align:center; font-size:11px; color:#909399; margin:8px 14px; }
</style>
