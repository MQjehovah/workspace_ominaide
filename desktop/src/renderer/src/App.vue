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
let remoteWsRoomId = ''
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
  } catch (e: any) { error.value = String(e) }
})

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

function setupRemoteWs() {
  window.mqbox.remote.onConnect((data: any) => {
    console.log('[app] remote:ws-connect received', data?.roomId)
    remoteWsDisconnect()
    remoteWsRoomId = data.roomId || ''
    remoteWsDeviceId = data.deviceId || ''
    if (!data.serverUrl || !data.roomId) { console.error('[app] remote:ws-connect: missing data'); return }
    const url = data.serverUrl.replace(/^http/, 'ws') + '/ws/remote/' + data.roomId + '?token=' + encodeURIComponent(data.token)
    console.log('[app] creating WebSocket')
    remoteWs = new WebSocket(url)
    remoteWs.onopen = () => {
      console.log('[app] WS connected, sending join')
      remoteWs.send(JSON.stringify({ type: 'join' }))
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
      if (remoteWsRoomId) {
        clearTimeout(remoteWsReconnectTimer)
        remoteWsReconnectTimer = setTimeout(function() {
          if (remoteWsRoomId) remoteWsReconnect()
        }, 5000)
      }
    }
    remoteWs.onerror = function() {
      console.error('[app] WS error')
      remoteWs.close()
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
  remoteWsRoomId = ''
  remoteWsDeviceId = ''
}

function remoteWsReconnect() {
  console.log('[app] remoteWsReconnect')
  var cfg = window.mqbox && window.mqbox.config
  if (!cfg || !remoteWsRoomId) { console.log('[app] reconnect: skip'); return }
  Promise.all([cfg.get('serverUrl'), cfg.get('token')]).then(function(values) {
    var serverUrl = values[0] || 'http://localhost:8000'
    var token = values[1] || ''
    var url = serverUrl.replace(/^http/, 'ws') + '/ws/remote/' + remoteWsRoomId + '?token=' + encodeURIComponent(token)
    console.log('[app] reconnect WS')
    remoteWs = new WebSocket(url)
    remoteWs.onopen = function() { remoteWs.send(JSON.stringify({ type: 'join' })); console.log('[app] reconnect: joined') }
    remoteWs.onmessage = function(e) { try { window.mqbox.remote.publishSignal(JSON.parse(e.data)) } catch (e) {} }
    remoteWs.onclose = function() { remoteWs = null }
  }).catch(function(e) { console.error('[app] reconnect error:', e) })
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
