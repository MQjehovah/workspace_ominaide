<script setup lang="ts">
import { computed, ref } from 'vue'
const props = defineProps<{
  data: { currentTrack: any; isPlaying: boolean; currentTime: number; duration: number; playMode: string; playlists: any[]; currentPlaylistTracks: any[] }
  execute: (action: string, args?: unknown) => Promise<unknown>
  openPage: () => void; refresh: () => Promise<void>
}>()
const showMenu = ref(false)
const progress = computed(() => props.data.duration ? (props.data.currentTime / props.data.duration) * 100 : 0)
function fmt(s: number) { if (!s || isNaN(s)) return '0:00'; return `${Math.floor(s / 60)}:${Math.floor(s % 60).toString().padStart(2, '0')}` }
</script>

<template>
  <div class="panel">
    <div class="panel-hd">
      <div class="panel-icon pink">
        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>
      </div>
      <div class="panel-info"><span class="panel-title">播放器</span></div>
      <button class="panel-btn" @click="openPage"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg></button>
    </div>

    <div v-if="data.currentTrack" class="track-info">
      <div class="track-name">{{ data.currentTrack.name }}</div>
      <div class="track-artist">{{ data.currentTrack.artist || '' }}</div>
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progress + '%' }"></div>
      </div>
      <div class="time-row">
        <span>{{ fmt(data.currentTime) }}</span>
        <span>{{ fmt(data.duration) }}</span>
      </div>
    </div>

    <div class="controls">
      <button class="ctrl-btn sm" @click="execute('prev')">
        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/></svg>
      </button>
      <button class="play-btn" @click="data.isPlaying ? execute('pause') : execute('play', { trackId: data.currentTrack?.id })">
        <svg v-if="data.isPlaying" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
        <svg v-else viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
      </button>
      <button class="ctrl-btn sm" @click="execute('next')">
        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>
      </button>
    </div>

    <div v-if="!data.currentTrack" class="empty" @click="openPage">打开播放器添加歌曲</div>
  </div>
</template>

<style scoped>
.panel { background:#fff; border-radius:10px; border:1px solid #e8e8e8; padding:12px; }
.panel-hd { display:flex; align-items:center; gap:10px; margin-bottom:8px; }
.panel-icon { width:32px; height:32px; border-radius:8px; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.panel-icon.pink { background:#fce4ec; }
.panel-icon svg { width:16px; height:16px; color:#E91E63; }
.panel-info { flex:1; }
.panel-title { font-size:13px; font-weight:600; color:#1e1e1e; }
.panel-btn { border:none; background:transparent; cursor:pointer; color:#ccc; padding:4px; border-radius:4px; }
.panel-btn:hover { background:#f5f5f5; color:#666; }
.track-info { margin-bottom:8px; }
.track-name { font-size:12px; font-weight:500; color:#333; }
.track-artist { font-size:11px; color:#999; }
.progress-bar { height:4px; background:#eee; border-radius:2px; margin:6px 0; cursor:pointer; overflow:hidden; }
.progress-fill { height:100%; background:#E91E63; border-radius:2px; }
.time-row { display:flex; justify-content:space-between; font-size:10px; color:#999; }
.controls { display:flex; align-items:center; justify-content:center; gap:12px; }
.ctrl-btn { width:24px; height:24px; border-radius:12px; border:none; background:#f0f0f0; cursor:pointer; display:flex; align-items:center; justify-content:center; padding:0; }
.ctrl-btn:hover { background:#e0e0e0; }
.ctrl-btn svg { width:12px; height:12px; color:#666; }
.ctrl-btn.sm { width:20px; height:20px; }
.play-btn { width:32px; height:32px; border-radius:16px; border:none; background:#E91E63; cursor:pointer; display:flex; align-items:center; justify-content:center; }
.play-btn:hover { background:#d81b60; }
.play-btn svg { width:16px; height:16px; color:#fff; }
.empty { text-align:center; padding:12px; color:#999; font-size:12px; cursor:pointer; }
.empty:hover { color:#E91E63; }
</style>
