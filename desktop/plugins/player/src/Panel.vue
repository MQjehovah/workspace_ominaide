<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'

interface Track {
  id: string
  name: string
  source: 'local' | 'url'
  path: string
  artist?: string
}

interface PlaylistInfo {
  id: string
  name: string
  trackIds: string[]
}

interface Props {
  data: {
    playlists: PlaylistInfo[]
    tracks: Record<string, Track>
    currentPlaylistId: string | null
    currentPlaylist: PlaylistInfo | null
    currentTrackId: string | null
    currentTrack: Track | null
    currentPlaylistTracks: Track[]
    isPlaying: boolean
    currentTime: number
    duration: number
    volume: number
    playMode: 'sequence' | 'loop' | 'shuffle'
  }
  execute: (action: string, args?: unknown) => Promise<unknown>
  openPage: () => void
  refresh: () => Promise<void>
}

const props = defineProps<Props>()
const showPlaylist = ref(false)
const audioRef = ref<HTMLAudioElement | null>(null)
const localCurrentTime = ref(0)
const localDuration = ref(0)

const progress = computed(() => {
  const dur = localDuration.value || props.data.duration
  if (!dur) return 0
  return ((localCurrentTime.value || props.data.currentTime) / dur) * 100
})

function fmt(s: number) {
  if (!s || isNaN(s)) return '0:00'
  return `${Math.floor(s / 60)}:${Math.floor(s % 60).toString().padStart(2, '0')}`
}

function getAudioUrl(track: Track | null): string {
  if (!track) return ''
  if (track.source === 'url') return track.path
  return `local-file:///${track.path.replace(/\\/g, '/')}`
}

function onTimeUpdate() {
  if (!audioRef.value) return
  localCurrentTime.value = audioRef.value.currentTime
  localDuration.value = audioRef.value.duration || 0
}

function onDurationChange() {
  if (!audioRef.value) return
  localDuration.value = audioRef.value.duration || 0
}

watch(() => props.data.currentTrack, async (newTrack, oldTrack) => {
  if (!audioRef.value) return
  const newUrl = getAudioUrl(newTrack)
  if (!newTrack || !newUrl) {
    audioRef.value.pause()
    audioRef.value.removeAttribute('src')
    localCurrentTime.value = 0
    localDuration.value = 0
    return
  }
  if (getAudioUrl(oldTrack) !== newUrl) {
    audioRef.value.src = newUrl
    localCurrentTime.value = 0
    localDuration.value = 0
    if (props.data.isPlaying) {
      try { await audioRef.value.play() } catch (e) { console.error('Audio error:', e) }
    }
  }
}, { deep: true })

watch(() => props.data.isPlaying, async (playing) => {
  if (!audioRef.value || !audioRef.value.src) return
  if (playing) {
    try { await audioRef.value.play() } catch (e) { console.error('Audio resume error:', e) }
  } else {
    audioRef.value.pause()
  }
})

watch(() => props.data.volume, (vol) => {
  if (audioRef.value) audioRef.value.volume = vol / 100
})

onMounted(() => {
  if (audioRef.value) {
    audioRef.value.volume = props.data.volume / 100
    if (props.data.currentTrack) {
      const url = getAudioUrl(props.data.currentTrack)
      if (url) {
        audioRef.value.src = url
        if (props.data.isPlaying) {
          audioRef.value.play().catch(() => {})
        }
      }
    }
  }
})

onUnmounted(() => {
  if (audioRef.value) {
    audioRef.value.pause()
    audioRef.value.removeAttribute('src')
  }
})

async function handleAudioEnded() {
  await props.execute('onTrackEnded')
  if (audioRef.value) {
    const url = getAudioUrl(props.data.currentTrack)
    if (url) {
      audioRef.value.src = url
      if (props.data.isPlaying) {
        try { await audioRef.value.play() } catch {}
      }
    }
  }
}
</script>

<template>
  <div class="panel">
    <audio ref="audioRef" preload="auto" @ended="handleAudioEnded" @timeupdate="onTimeUpdate" @durationchange="onDurationChange" />

    <div class="panel-hd">
      <div class="panel-icon pink">
        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>
      </div>
      <div class="panel-info">
        <span class="panel-title">播放器</span>
        <span class="panel-meta">{{ data.currentTrack?.name || '未播放' }}</span>
      </div>
      <div class="panel-actions">
        <button class="panel-arrow" @click="openPage">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
        </button>
      </div>
    </div>

    <div v-if="data.currentTrack" class="player-body">
      <div class="progress-row">
        <span class="time-label">{{ fmt(localCurrentTime || props.data.currentTime) }}</span>
        <div class="progress-track" @click="(e: MouseEvent) => execute('seek', { percent: (e as any).offsetX / (e.target as HTMLElement).offsetWidth })">
          <div class="progress-fill" :style="{ width: progress + '%' }"></div>
        </div>
        <span class="time-label">{{ fmt(localDuration || props.data.duration) }}</span>
      </div>
      <div class="controls-row">
        <div class="center-group">
          <button class="ctrl-btn" @click="execute('prev')">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/></svg>
          </button>
          <button class="play-btn" @click="data.isPlaying ? execute('pause') : execute('play', { trackId: data.currentTrackId })">
            <svg v-if="data.isPlaying" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
            <svg v-else viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
          </button>
          <button class="ctrl-btn" @click="execute('next')">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>
          </button>
        </div>
        <div class="right-group">
          <button class="mode-btn" :title="data.playMode === 'sequence' ? '顺序播放' : data.playMode === 'loop' ? '单曲循环' : '随机播放'" @click="execute('toggleMode')">
            <svg v-if="data.playMode === 'sequence'" viewBox="0 0 24 24" fill="currentColor"><path d="M3 5h2v14H3V5zm4 0h2v14H7V5zm10 0h4v14h-4V5zm-6 0h2v5h-2V5zm0 7h2v5h-2v-5z"/></svg>
            <svg v-else-if="data.playMode === 'loop'" viewBox="0 0 24 24" fill="currentColor"><path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/></svg>
            <svg v-else viewBox="0 0 24 24" fill="currentColor"><path d="M10.59 9.17L5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41l-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z"/></svg>
          </button>
          <div class="playlist-wrapper">
            <button class="list-btn" @click="showPlaylist = !showPlaylist" :title="data.currentPlaylist?.name || '歌单'">
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="M4 6h16v2H4zm0 5h16v2H4zm0 5h10v2H4zm14 0v6l5-3z"/></svg>
            </button>
            <div v-if="showPlaylist" class="playlist-dropdown">
              <div v-if="data.playlists.length > 1" class="pl-tabs">
                <button v-for="pl in data.playlists" :key="pl.id" class="pl-tab" :class="{ active: data.currentPlaylistId === pl.id }" @click="execute('selectPlaylist', { playlistId: pl.id })">{{ pl.name }}</button>
              </div>
              <div class="pl-list">
                <div v-if="!data.currentPlaylistTracks.length" class="pl-empty">歌单为空</div>
                <button v-for="(t, i) in data.currentPlaylistTracks" :key="t.id" class="pl-item" :class="{ active: data.currentTrackId === t.id }" @click="showPlaylist = false; execute('play', { trackId: t.id })">
                  <span class="pl-idx">{{ i + 1 }}</span>
                  <span class="pl-name">{{ t.name }}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="empty-row">
      <button class="play-btn sm" @click="openPage">
        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
      </button>
      <span class="empty-text">打开播放器添加歌曲</span>
    </div>
  </div>
</template>

<style scoped>
.panel { background:#fff; border-radius:10px; border:1px solid #e8e8e8; padding:12px; }
.panel-hd { display:flex; align-items:center; gap:10px; margin-bottom:8px; }
.panel-icon { width:32px; height:32px; border-radius:8px; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.panel-icon.pink { background:#fce4ec; }
.panel-icon svg { width:16px; height:16px; color:#E91E63; }
.panel-info { flex:1; min-width:0; }
.panel-title { font-size:13px; font-weight:600; color:#1e1e1e; display:block; }
.panel-meta { font-size:11px; color:#999; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.panel-actions { display:flex; align-items:center; gap:4px; flex-shrink:0; }
.panel-arrow { border:none; background:transparent; cursor:pointer; color:#ccc; padding:4px; border-radius:4px; display:flex; }
.panel-arrow:hover { background:#f5f5f5; color:#666; }
.mode-btn { border:none; background:transparent; cursor:pointer; padding:4px; border-radius:4px; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.mode-btn:hover { background:#f5f5f5; }
.mode-btn svg { width:14px; height:14px; color:#E91E63; }

.player-body { display:flex; flex-direction:column; gap:8px; }
.progress-row { display:flex; align-items:center; gap:6px; }
.time-label { font-size:10px; color:#999; width:28px; text-align:center; flex-shrink:0; font-variant-numeric:tabular-nums; }
.progress-track { flex:1; height:4px; background:#eee; border-radius:2px; cursor:pointer; overflow:hidden; position:relative; }
.progress-fill { height:100%; background:#E91E63; border-radius:2px; pointer-events:none; max-width:100%; }

.controls-row { display:flex; align-items:center; }
.center-group { flex:1; display:flex; align-items:center; justify-content:center; gap:10px; }
.right-group { display:flex; align-items:center; gap:4px; flex-shrink:0; margin-left:auto; }
.ctrl-btn { width:26px; height:26px; border-radius:50%; border:none; background:#f0f0f0; cursor:pointer; display:flex; align-items:center; justify-content:center; padding:0; flex-shrink:0; }
.ctrl-btn:hover { background:#e0e0e0; }
.ctrl-btn svg { width:12px; height:12px; color:#666; }
.play-btn { width:34px; height:34px; border-radius:50%; border:none; background:#E91E63; cursor:pointer; display:flex; align-items:center; justify-content:center; padding:0; flex-shrink:0; }
.play-btn:hover { background:#d81b60; }
.play-btn svg { width:16px; height:16px; color:#fff; }
.play-btn.sm { width:28px; height:28px; }
.play-btn.sm svg { width:13px; height:13px; }

.playlist-wrapper { position:relative; display:inline-flex; }
.list-btn { width:24px; height:24px; border-radius:6px; border:1px solid #e0e0e0; background:#fff; cursor:pointer; display:flex; align-items:center; justify-content:center; padding:0; }
.list-btn:hover { background:#f5f5f5; }
.list-btn svg { width:13px; height:13px; color:#E91E63; }

.playlist-dropdown { position:absolute; bottom:100%; right:0; margin-bottom:6px; width:190px; background:#fff; border-radius:8px; box-shadow:0 4px 16px rgba(0,0,0,0.12); border:1px solid #e8e8e8; z-index:100; overflow:hidden; }
.pl-tabs { display:flex; gap:2px; padding:6px; border-bottom:1px solid #f0f0f0; overflow-x:auto; }
.pl-tab { flex-shrink:0; padding:3px 8px; border-radius:4px; border:none; font-size:11px; cursor:pointer; background:transparent; color:#666; white-space:nowrap; }
.pl-tab:hover { background:#f5f5f5; }
.pl-tab.active { background:#E91E63; color:#fff; }
.pl-list { max-height:160px; overflow-y:auto; padding:4px; }
.pl-empty { text-align:center; padding:12px; color:#ccc; font-size:11px; }
.pl-item { width:100%; display:flex; align-items:center; gap:6px; padding:6px 8px; border-radius:6px; border:none; background:transparent; cursor:pointer; text-align:left; }
.pl-item:hover { background:#f8f9fa; }
.pl-item.active { background:#fce4ec; }
.pl-idx { width:16px; font-size:10px; color:#bbb; text-align:right; flex-shrink:0; }
.pl-name { font-size:11px; color:#333; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; }

.empty-row { display:flex; align-items:center; justify-content:center; gap:8px; padding:4px 0; }
.empty-text { font-size:12px; color:#ccc; }
</style>
