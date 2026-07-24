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

function setupRemoteWs() {
  window.mqbox.remote.onConnect((data: any) => {
    remoteWsDisconnect()
    remoteWsRoomId = data.roomId || ''
    remoteWsDeviceId = data.deviceId || ''
    const wsUrl = `${data.serverUrl.replace(/^http/, 'ws')}/ws/remote/${data.roomId}?token=${encodeURIComponent(data.token)}`
    remoteWs = new WebSocket(wsUrl)
    remoteWs.onopen = () => {
      remoteWs!.send(JSON.stringify({ type: 'join' }))
      window.mqbox.remote.publishStatus('connected')
    }
    remoteWs.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        window.mqbox.remote.publishSignal(msg)
      } catch {}
    }
    remoteWs.onclose = () => {
      remoteWs = null
      window.mqbox.remote.publishStatus('disconnected')
      if (remoteWsRoomId) {
        clearTimeout(remoteWsReconnectTimer)
        remoteWsReconnectTimer = setTimeout(() => {
          if (remoteWsRoomId) remoteWsReconnect()
        }, 5000)
      }
    }
    remoteWs.onerror = () => {
      remoteWs?.close()
    }
  })
  window.mqbox.remote.onSend((data: any) => {
    if (remoteWs?.readyState === WebSocket.OPEN) {
      remoteWs.send(JSON.stringify(data))
    }
  })
  window.mqbox.remote.onDisconnect(() => {
    remoteWsDisconnect()
  })
}

function remoteWsDisconnect() {
  clearTimeout(remoteWsReconnectTimer)
  if (remoteWs) { remoteWs.onclose = null; remoteWs.close(); remoteWs = null }
  remoteWsRoomId = ''
  remoteWsDeviceId = ''
}

function remoteWsReconnect() {
  const cfg = window.mqbox?.config
  if (!cfg || !remoteWsRoomId) return
  Promise.all([cfg.get('serverUrl'), cfg.get('token')]).then(([serverUrl, token]) => {
    remoteWs = new WebSocket(`${(serverUrl || 'http://localhost:8000').replace(/^http/, 'ws')}/ws/remote/${remoteWsRoomId}?token=${encodeURIComponent(token || '')}`)
    remoteWs.onopen = () => {
      remoteWs!.send(JSON.stringify({ type: 'join' }))
      window.mqbox.remote.publishStatus('connected')
    }
    remoteWs.onmessage = (e) => {
      try { window.mqbox.remote.publishSignal(JSON.parse(e.data)) } catch {}
    }
    remoteWs.onclose = () => { remoteWs = null }
  }).catch(() => {})
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
