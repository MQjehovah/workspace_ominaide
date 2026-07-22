<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import * as webrtcHost from './webrtc-host'

const props = defineProps<{ data: any; execute: (a: string, args?: any) => Promise<any>; openPage: () => void; refresh: () => Promise<void> }>()

const hosting = ref(false)
const pairCode = ref('')
const status = ref('')
const hasPeer = ref(false)
const autoAccept = ref(localStorage.getItem('remote_autoAccept') === 'true')

function toggleAutoAccept() {
  if (autoAccept.value) localStorage.setItem('remote_autoAccept', 'true')
  else localStorage.removeItem('remote_autoAccept')
  props.execute?.('setAutoAccept', { enabled: autoAccept.value })
}

function openManagement() {
  ;(props as any).openPage?.('remote') || (window as any).mqbox?.window?.openPage?.('remote')
}

async function toggleHost() {
  const st = await props.execute('getState')
  const enabled = st?.hostState?.enabled
  if (enabled) {
    webrtcHost.stop()
    await props.execute('stopHost')
    hosting.value = false
    pairCode.value = ''
    status.value = ''
    hasPeer.value = false
  } else {
    await props.execute('startHost')
    webrtcHost.init(props.execute)
    webrtcHost.ensureStarted()
    const s2 = await props.execute('getState')
    if (s2?.hostState) updateUI(s2.hostState)
  }
}

function updateUI(h: any) {
  hosting.value = !!h.enabled
  if (h.code) pairCode.value = h.code
  if (h.status) status.value = h.status
  autoAccept.value = !!h.autoAccept
  hasPeer.value = webrtcHost.getPeerConnected()
}

let uiTimer: any = null

onMounted(() => {
  webrtcHost.init(props.execute)
  webrtcHost.ensureStarted()
  // UI refresh timer (separate from WebRTC polling)
  const refreshUI = async () => {
    try {
      const st = await props.execute('getState')
      if (st?.hostState) updateUI(st.hostState)
    } catch {}
  }
  refreshUI()
  uiTimer = setInterval(refreshUI, 3000)
})

onUnmounted(() => {
  if (uiTimer) clearInterval(uiTimer)
  // Do NOT stop webrtcHost — WebRTC continues independently
})
</script>

<template>
  <div class="panel">
    <div class="panel-hd">
      <span class="title">远程控制</span>
      <button class="panel-arrow" @click="openManagement">›</button>
    </div>

    <div class="host-row">
      <span class="host-label" :class="{ active: hosting }">允许控制本机</span>
      <label class="switch">
        <input type="checkbox" :checked="hosting" @change="toggleHost" />
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

    <div v-if="hasPeer" class="peer-info">
      <span class="peer-dot"></span>
      <span>主控已连接</span>
    </div>

    <button v-if="hasPeer" class="revoke-btn" @click="webrtcHost.revokePeer()">断开控制</button>
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
.peer-info { display:flex; align-items:center; gap:6px; padding:4px 0; font-size:11px; color:#28a745; }
.peer-dot { width:6px;height:6px;border-radius:50%;background:#28a745; }

.revoke-btn { width:100%; margin-top:6px; padding:6px; border:none; border-radius:8px; background:#ffebee; color:#c62828; font-size:11px; cursor:pointer; }
.revoke-btn:hover { background:#ffcdd2; }
</style>
