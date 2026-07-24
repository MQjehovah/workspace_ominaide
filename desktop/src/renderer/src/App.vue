<template>
  <div v-if="ready">
    <LoginPage v-if="view === 'login'" @logged-in="onLoggedIn" />
    <MainPanel v-else-if="view === 'main'" />
    <SearchBox v-else-if="view === 'search'" />
    <PluginPage v-else-if="view === 'plugin-page'" />
    <AssistantWindow v-else-if="view === 'assistant'" />
    <ScreenshotPanel v-else-if="view === 'screenshot'" />
    <ScreenshotEditor v-else-if="view === 'screenshot-editor'" />
    <PluginManager v-else-if="view === 'plugin-manager'" />
    <audio ref="audioRef" preload="auto" @ended="onAudioEnded" @timeupdate="onTimeUpdate" @loadedmetadata="onLoadedMeta" />
  </div>
  <div v-else-if="error" class="error">{{ error }}</div>
  <div v-else class="loading"><p>加载中...</p></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onErrorCaptured, onUnmounted } from 'vue'
import MainPanel from './components/MainPanel.vue'
import SearchBox from './components/SearchBox.vue'
import PluginPage from './components/PluginPage.vue'
import PluginManager from './components/PluginManager.vue'
import LoginPage from './components/LoginPage.vue'
import ScreenshotPanel from './components/ScreenshotPanel.vue'
import AssistantWindow from './components/AssistantWindow.vue'
import ScreenshotEditor from './components/ScreenshotEditor.vue'

const ready = ref(false)
const error = ref('')
const params = new URLSearchParams(window.location.search)
const view = ref(params.get('view') || 'login')
const audioRef = ref<HTMLAudioElement | null>(null)
let pendingSeek: number | null = null

let remoteWs: WebSocket | null = null
let remoteWsReconnectTimer: any = null
let remoteWsDeviceId = ''

onErrorCaptured((err) => { error.value = String(err); return false })

onMounted(async () => {
  try {
    let tries = 0
    while (!window.mqbox && tries < 20) {
      await new Promise(r => setTimeout(r, 100))
      tries++
    }
    if (!window.mqbox) { error.value = 'Preload bridge not loaded'; return }
    ready.value = true
    setupAudioListeners()
    setupRemoteWs()
    // Auto-reconnect WS if host was enabled
    checkRemoteAutoConnect()
  } catch (e: any) { error.value = String(e) }
})

async function checkRemoteAutoConnect() {
  try {
    const stored = await window.mqbox.plugin.execute('remote', 'getState')
    const hostState = stored?.hostState
    if (hostState?.enabled) {
      console.log('[app] auto-connect: saved host was enabled, connecting WS')
      const deviceId = await window.mqbox.plugin.execute('remote', 'getDeviceId')
      const hostName = await window.mqbox.plugin.execute('remote', 'getHostName')
      if (!deviceId) { console.log('[app] auto-connect: no deviceId'); return }
      const serverUrl = await window.mqbox.config.get('serverUrl') || 'http://localhost:8000'
      const token = await window.mqbox.config.get('token') || ''
      window.mqbox.remote.connectDirectly({ serverUrl, token, deviceId, name: hostName })
    }
  } catch (e) {
    console.error('[app] auto-connect error:', e)
  }
}

function setupRemoteWs() {
  window.mqbox.remote.onConnect((data: any) => {
    console.log('[app] remote:ws-connect received', data?.deviceId)
    if (remoteWs && (remoteWs.readyState === WebSocket.OPEN || remoteWs.readyState === WebSocket.CONNECTING)) {
      console.log('[app] WS already exists/connecting, ignoring duplicate connect')
      return
    }
    remoteWsDisconnect()
    remoteWsDeviceId = data.deviceId || ''
    if (!data.serverUrl || !data.deviceId) { console.error('[app] remote:ws-connect: missing data'); return }
    const url = data.serverUrl.replace(/^http/, 'ws') + '/ws/remote'
    console.log('[app] creating WebSocket')
    remoteWs = new WebSocket(url)
    remoteWs.onopen = () => {
      console.log('[app] WS connected, sending join')
      remoteWs.send(JSON.stringify({ type: 'join', device_id: data.deviceId, name: data.name || '', token: data.token }))
      window.mqbox.remote.publishStatus('connected')
    }
    remoteWs.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        console.log('[app] WS msg:', msg.type)
        window.mqbox.remote.publishSignal(msg)
      } catch (err) { console.error('[app] WS parse error:', err) }
    }
    remoteWs.onclose = () => {
      console.log('[app] WS closed')
      remoteWs = null
      window.mqbox.remote.publishStatus('disconnected')
      if (remoteWsDeviceId) {
        clearTimeout(remoteWsReconnectTimer)
        remoteWsReconnectTimer = setTimeout(function() {
          if (remoteWsDeviceId) remoteWsReconnect()
        }, 5000)
      }
    }
    remoteWs.onerror = function() {
      console.error('[app] WS error')
    }
  })
  window.mqbox.remote.onSend(function(data: any) {
    console.log('[app] remote:ws-send type=' + (data?.type))
    if (remoteWs && remoteWs.readyState === WebSocket.OPEN) {
      remoteWs.send(JSON.stringify(data))
      console.log('[app] WS send done')
    } else {
      console.warn('[app] WS not open')
    }
  })
  window.mqbox.remote.onDisconnect(function() {
    console.log('[app] remote:ws-disconnect received')
    remoteWsDisconnect()
  })
}

function remoteWsDisconnect() {
  console.log('[app] remoteWsDisconnect')
  clearTimeout(remoteWsReconnectTimer)
  if (remoteWs) { remoteWs.onclose = null; remoteWs.close(); remoteWs = null }
  remoteWsDeviceId = ''
}

function remoteWsReconnect() {
  console.log('[app] remoteWsReconnect')
  var cfg = window.mqbox && window.mqbox.config
  if (!cfg || !remoteWsDeviceId) { console.log('[app] reconnect: skip'); return }
  Promise.all([cfg.get('serverUrl'), cfg.get('token'), cfg.get('deviceName')]).then(function(values) {
    var serverUrl = values[0] || 'http://localhost:8000'
    var token = values[1] || ''
    var name = values[2] || ''
    var url = serverUrl.replace(/^http/, 'ws') + '/ws/remote'
    console.log('[app] reconnect WS')
    remoteWs = new WebSocket(url)
    remoteWs.onopen = function() {
      remoteWs.send(JSON.stringify({ type: 'join', device_id: remoteWsDeviceId, name: name, token: token }))
      console.log('[app] reconnect: joined')
    }
    remoteWs.onmessage = function(e) { try { window.mqbox.remote.publishSignal(JSON.parse(e.data)) } catch (e) {} }
    remoteWs.onclose = function() { remoteWs = null }
  }).catch(function(e) { console.error('[app] reconnect error:', e) })
}

function setupAudioListeners() {
  window.mqbox.player.onControl((detail: any) => {
    const audio = audioRef.value
    if (!audio) return
    switch (detail?.action) {
      case 'play':
        if (detail.src) audio.src = detail.src
        if (detail.currentTime != null) {
          if (audio.readyState >= 1) audio.currentTime = detail.currentTime
          else pendingSeek = detail.currentTime
        }
        audio.play().catch(() => {})
        break
      case 'pause':
        audio.pause()
        break
      case 'seek':
        if (detail.time != null) {
          if (audio.readyState >= 1) audio.currentTime = detail.time
          else pendingSeek = detail.time
        }
        break
      case 'set-volume':
        if (detail.volume != null) audio.volume = detail.volume / 100
        break
      case 'set-source':
        audio.src = detail.src
        if (detail.currentTime != null) {
          if (audio.readyState >= 1) audio.currentTime = detail.currentTime
          else pendingSeek = detail.currentTime
        }
        if (detail.autoplay !== false) audio.play().catch(() => {})
        break
    }
  })
}

function onAudioEnded() {
  window.mqbox.player.sendEvent('ended', {})
}

function onTimeUpdate() {
  const audio = audioRef.value
  if (audio) {
    window.mqbox.player.sendEvent('timeupdate', { currentTime: audio.currentTime, duration: audio.duration })
  }
}

function onLoadedMeta() {
  const audio = audioRef.value
  if (audio) {
    window.mqbox.player.sendEvent('loadedmetadata', { duration: audio.duration })
    if (pendingSeek != null) {
      audio.currentTime = pendingSeek
      pendingSeek = null
    }
  }
}

onUnmounted(() => {
  if (audioRef.value) { audioRef.value.pause(); audioRef.value.src = '' }
})

function onLoggedIn() {
  window.mqbox.window.openMain()
}
</script>

<style scoped>
.loading { display:flex; align-items:center; justify-content:center; height:100vh; color:#909399; font-size:14px; }
</style>
