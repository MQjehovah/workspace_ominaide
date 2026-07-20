<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'

const playModeLabels: Record<string, string> = {
  sequence: '顺序播放',
  loop: '单曲循环',
  shuffle: '随机播放',
}

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
  refresh?: () => void
  close: () => void
}

const props = defineProps<Props>()

const audioRef = ref<HTMLAudioElement | null>(null)
const localCurrentTime = ref(0)
const localDuration = ref(0)
const localIsPlaying = ref(false)
const selectedPlaylistId = ref<string | null>(null)
const newPlaylistName = ref('')
const newPlaylistInline = ref(false)
const addTrackSource = ref<'local' | 'url'>('local')
const addTrackPath = ref('')
const addTrackName = ref('')
const addTrackArtist = ref('')
const showAddTrackModal = ref(false)
const renamingPlaylistId = ref<string | null>(null)
const renameName = ref('')

const activePlaylist = computed(() => {
  const id = selectedPlaylistId.value || props.data.currentPlaylistId
  return props.data.playlists.find(p => p.id === id) || null
})

const activeTracks = computed(() => {
  if (!activePlaylist.value) return []
  return activePlaylist.value.trackIds
    .map(id => props.data.tracks[id])
    .filter(Boolean)
})

const progressPercent = computed(() => {
  const dur = localDuration.value || props.data.duration
  const cur = localCurrentTime.value || props.data.currentTime
  return dur ? (cur / dur) * 100 : 0
})

function getAudioUrl(track: Track | null): string {
  if (!track) return ''
  if (track.source === 'url') return track.path
  return `local-file:///${track.path.replace(/\\/g, '/')}`
}

function formatTime(seconds: number) {
  if (!seconds || isNaN(seconds)) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

function onTimeUpdate() {
  if (!audioRef.value) return
  localCurrentTime.value = audioRef.value.currentTime
  localDuration.value = audioRef.value.duration || 0
  if (props.data.isPlaying && localCurrentTime.value > 0) {
    props.execute('updateProgress', {
      currentTime: localCurrentTime.value,
      duration: localDuration.value
    })
  }
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
    localIsPlaying.value = false
    localCurrentTime.value = 0
    localDuration.value = 0
    return
  }
  const oldUrl = getAudioUrl(oldTrack)
  if (oldUrl !== newUrl) {
    audioRef.value.src = newUrl
    localCurrentTime.value = 0
    localDuration.value = 0
    if (props.data.isPlaying) {
      try {
        await audioRef.value.play()
        localIsPlaying.value = true
      } catch (e) {
        console.error('Audio play error:', e)
      }
    }
  }
}, { deep: true })

watch(() => props.data.isPlaying, async (playing) => {
  if (!audioRef.value || !audioRef.value.src) return
  if (playing) {
    try {
      await audioRef.value.play()
      localIsPlaying.value = true
    } catch (e) {
      console.error('Audio resume error:', e)
    }
  } else {
    audioRef.value.pause()
    localIsPlaying.value = false
  }
})

watch(() => props.data.volume, (vol) => {
  if (audioRef.value) {
    audioRef.value.volume = vol / 100
  }
})

onMounted(() => {
  if (audioRef.value) {
    audioRef.value.volume = props.data.volume / 100
  }
  if (!selectedPlaylistId.value && props.data.currentPlaylistId) {
    selectedPlaylistId.value = props.data.currentPlaylistId
  }
  if (props.data.currentTrack) {
    const url = getAudioUrl(props.data.currentTrack)
    if (audioRef.value && url) {
      audioRef.value.src = url
      if (props.data.isPlaying) {
        audioRef.value.play().catch(() => {})
        localIsPlaying.value = true
      }
    }
  }
  window.mqbox?.player?.onUpdated(() => props.refresh?.())
})

onUnmounted(() => {
  if (audioRef.value) {
    audioRef.value.pause()
    audioRef.value.removeAttribute('src')
  }
})

async function handlePlay(trackId?: string) {
  if (trackId) {
    await props.execute('play', { trackId })
  } else {
    await props.execute('play', {})
  }
}

async function handlePause() {
  await props.execute('pause')
  localIsPlaying.value = false
}

async function handlePlayPause() {
  if (props.data.isPlaying || localIsPlaying.value) {
    await handlePause()
  } else {
    await handlePlay()
  }
}

async function handleNext() { await props.execute('next') }
async function handlePrev() { await props.execute('prev') }

async function handleAudioEnded() {
  localIsPlaying.value = false
  await props.execute('onTrackEnded')
  if (props.data.isPlaying && audioRef.value) {
    const url = getAudioUrl(props.data.currentTrack)
    if (url) {
      audioRef.value.src = url
      try {
        await audioRef.value.play()
        localIsPlaying.value = true
      } catch (e) {}
    }
  }
}

async function handleSeek(e: Event) {
  const input = e.target as HTMLInputElement
  const time = parseFloat(input.value)
  if (audioRef.value) audioRef.value.currentTime = time
  localCurrentTime.value = time
  await props.execute('seek', { time })
}

async function startNewPlaylist() {
  newPlaylistName.value = ''
  newPlaylistInline.value = true
}

function refreshUI() {
  setTimeout(() => props.refresh?.(), 50)
}

async function confirmNewPlaylist() {
  if (!newPlaylistName.value.trim()) { newPlaylistInline.value = false; return }
  await props.execute('createPlaylist', { name: newPlaylistName.value.trim() })
  newPlaylistName.value = ''
  newPlaylistInline.value = false
  refreshUI()
}

async function deletePlaylist(id: string) {
  await props.execute('deletePlaylist', { playlistId: id })
  if (selectedPlaylistId.value === id) selectedPlaylistId.value = null
  refreshUI()
}

async function startRename(pl: PlaylistInfo) {
  renamingPlaylistId.value = pl.id
  renameName.value = pl.name
}

async function confirmRename() {
  if (renamingPlaylistId.value && renameName.value.trim()) {
    await props.execute('renamePlaylist', { playlistId: renamingPlaylistId.value, name: renameName.value.trim() })
  }
  renamingPlaylistId.value = null
  refreshUI()
}

async function addTrack() {
  if (!addTrackPath.value.trim() || !activePlaylist.value) return
  const name = addTrackName.value.trim() || addTrackPath.value.split(/[/\\]/).pop() || '未知'
  await props.execute('addTrack', {
    playlistId: activePlaylist.value.id, name,
    path: addTrackPath.value.trim(),
    source: addTrackSource.value,
    artist: addTrackArtist.value.trim() || undefined
  })
  addTrackPath.value = ''
  addTrackName.value = ''
  addTrackArtist.value = ''
  showAddTrackModal.value = false
  refreshUI()
}

async function removeTrack(playlistId: string, trackId: string) {
  await props.execute('removeTrack', { playlistId, trackId })
  refreshUI()
}

async function moveTrackUp(playlistId: string, trackId: string) {
  await props.execute('moveTrack', { playlistId, trackId, direction: 'up' })
  refreshUI()
}

async function moveTrackDown(playlistId: string, trackId: string) {
  await props.execute('moveTrack', { playlistId, trackId, direction: 'down' })
  refreshUI()
}

async function selectPlaylist(id: string) {
  selectedPlaylistId.value = id
  await props.execute('selectPlaylist', { playlistId: id })
}

async function clearPlaylist(id: string) {
  await props.execute('clearPlaylist', { playlistId: id })
  refreshUI()
}

async function importDirectory() {
  if (!activePlaylist.value) return
  await props.execute('importDirectory', { playlistId: activePlaylist.value.id })
  refreshUI()
}
</script>

<template>
  <div class="player-page">
    <audio ref="audioRef" preload="auto" @ended="handleAudioEnded" @timeupdate="onTimeUpdate" @durationchange="onDurationChange" />

    <div class="main-area">
      <!-- Playlist sidebar -->
      <div class="sidebar">
        <div class="sidebar-header">
          <div class="sidebar-title-row">
            <span class="sidebar-title">歌单</span>
            <button class="btn-icon btn-pink" @click="startNewPlaylist" title="新建歌单">
              <svg class="icon-sm" viewBox="0 0 24 24" fill="currentColor"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>
            </button>
          </div>
        </div>
        <div class="sidebar-list">
          <div v-if="data.playlists.length === 0" class="empty-hint">暂无歌单，点击 + 创建</div>
          <div v-for="pl in data.playlists" :key="pl.id" class="playlist-item" :class="{ active: selectedPlaylistId === pl.id }" @click="selectPlaylist(pl.id)">
            <svg class="icon-sm shrink-0" viewBox="0 0 24 24" fill="currentColor"><path d="M4 6h16v2H4zm0 5h16v2H4zm0 5h10v2H4zm14 0v6l5-3z"/></svg>
            <div class="flex-1 min-w-0">
              <div v-if="renamingPlaylistId === pl.id">
                <input v-model="renameName" class="input-xs w-full" @keyup.enter="confirmRename" @keyup.escape="renamingPlaylistId = null" @blur="confirmRename" />
              </div>
              <div v-else>
                <div class="playlist-name">{{ pl.name }}</div>
                <div class="playlist-count">{{ pl.trackIds.length }} 首</div>
              </div>
            </div>
            <div class="playlist-actions">
              <button class="btn-icon-xs" title="重命名" @click.stop="startRename(pl)">
                <svg class="icon-xs" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              </button>
              <button class="btn-icon-xs btn-icon-danger" title="删除" @click.stop="deletePlaylist(pl.id)">
                <svg class="icon-xs" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            </div>
          </div>
          <div v-if="newPlaylistInline" class="playlist-item" style="background:#252525;">
            <svg class="icon-sm shrink-0" viewBox="0 0 24 24" fill="currentColor"><path d="M4 6h16v2H4zm0 5h16v2H4zm0 5h10v2H4zm14 0v6l5-3z"/></svg>
            <input v-model="newPlaylistName" class="input-xs" style="flex:1;min-width:0;" placeholder="输入歌单名称" @keyup.enter="confirmNewPlaylist" @keyup.escape="newPlaylistInline = false" @blur="confirmNewPlaylist" autofocus />
          </div>
        </div>
      </div>

      <!-- Track list -->
      <div class="track-area">
        <div class="track-header">
          <div>
            <h2 class="track-title">{{ activePlaylist?.name || '选择歌单' }}</h2>
            <span class="track-subtitle">{{ activeTracks.length }} 首歌曲</span>
          </div>
          <div class="track-actions" v-if="activePlaylist">
            <button class="btn btn-pink" @click="showAddTrackModal = true">
              <svg class="icon-sm" viewBox="0 0 24 24" fill="currentColor"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>
              添加
            </button>
            <button class="btn btn-purple" @click="importDirectory">
              <svg class="icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-6l-2-2H5a2 2 0 0 0-2 2z"/></svg>
              导入文件夹
            </button>
            <button class="btn btn-ghost" @click="clearPlaylist(activePlaylist!.id)">清空</button>
          </div>
        </div>

        <div class="track-list">
          <div v-if="!activePlaylist" class="empty-state">
            <svg class="empty-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>
            <span>选择或创建一个歌单</span>
          </div>
          <div v-else-if="activeTracks.length === 0" class="empty-state">
            <svg class="empty-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>
            <span>歌单是空的</span>
            <span class="text-xs text-gray-400 mt-1">点击上方"添加"来添加歌曲</span>
          </div>
          <div v-else>
            <div v-for="(track, index) in activeTracks" :key="track.id" class="track-row" :class="{ active: data.currentTrackId === track.id }" @click="handlePlay(track.id)">
              <div class="track-index">
                <span v-if="data.currentTrackId === track.id && data.isPlaying" class="playing-indicator">♫</span>
                <span v-else class="index-num">{{ index + 1 }}</span>
              </div>
              <div class="track-info">
                <div class="track-name">{{ track.name }}</div>
                <div class="track-meta">
                  <span v-if="track.artist">{{ track.artist }} · </span>
                  <span>{{ track.source === 'url' ? '在线' : '本地' }}</span>
                </div>
              </div>
              <div class="track-row-actions">
                <button class="btn-icon-xs" title="上移" @click.stop="moveTrackUp(activePlaylist!.id, track.id)">
                  <svg class="icon-xs" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 15l-6-6-6 6"/></svg>
                </button>
                <button class="btn-icon-xs" title="下移" @click.stop="moveTrackDown(activePlaylist!.id, track.id)">
                  <svg class="icon-xs" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
                </button>
                <button class="btn-icon-xs btn-icon-danger" title="移除" @click.stop="removeTrack(activePlaylist!.id, track.id)">
                  <svg class="icon-xs" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Bottom player bar -->
    <div class="player-bar">
      <template v-if="data.currentTrack">
        <div class="bar-track-info">
          <div class="bar-cover">
            <svg class="bar-cover-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>
          </div>
          <div class="bar-track-text">
            <div class="bar-track-name">{{ data.currentTrack.name }}</div>
            <div class="bar-track-artist">{{ data.currentTrack.artist || (data.currentTrack.source === 'url' ? '在线音频' : '本地文件') }}</div>
          </div>
        </div>

        <div class="bar-controls">
          <div class="bar-buttons">
            <button class="bar-btn" @click="handlePrev" title="上一首">
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/></svg>
            </button>
            <button class="bar-play-btn" @click="handlePlayPause" title="播放/暂停">
              <svg v-if="data.isPlaying" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
              <svg v-else viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
            </button>
            <button class="bar-btn" @click="handleNext" title="下一首">
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>
            </button>
          </div>
          <div class="bar-progress">
            <span class="bar-time">{{ formatTime(localCurrentTime || props.data.currentTime) }}</span>
            <div class="bar-track-bg">
              <div class="bar-track-fill" :style="{ width: progressPercent + '%' }"></div>
              <input type="range" class="bar-seek" :value="localCurrentTime || props.data.currentTime" :max="localDuration || props.data.duration || 100" step="0.1" @input="handleSeek" />
            </div>
            <span class="bar-time">{{ formatTime(localDuration || props.data.duration) }}</span>
          </div>
        </div>

        <div class="bar-extras">
          <button class="bar-mode-btn" :title="playModeLabels[data.playMode]" @click="execute('toggleMode')">
            <svg v-if="data.playMode === 'sequence'" class="icon-sm" viewBox="0 0 24 24" fill="currentColor"><path d="M3 5h2v14H3V5zm4 0h2v14H7V5zm10 0h4v14h-4V5zm-6 0h2v5h-2V5zm0 7h2v5h-2v-5z"/></svg>
            <svg v-else-if="data.playMode === 'loop'" class="icon-sm" viewBox="0 0 24 24" fill="currentColor"><path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/></svg>
            <svg v-else class="icon-sm" viewBox="0 0 24 24" fill="currentColor"><path d="M10.59 9.17L5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41l-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z"/></svg>
          </button>
          <div class="bar-volume">
            <svg class="icon-sm" viewBox="0 0 24 24" fill="currentColor"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg>
            <input type="range" class="volume-slider" :value="data.volume" max="100" @input="(e: Event) => execute('setVolume', { volume: parseInt((e.target as HTMLInputElement).value) })" />
          </div>
        </div>
      </template>
      <div v-else class="bar-empty">选择歌曲开始播放</div>
    </div>

    <!-- Add Track Modal -->
    <div v-if="showAddTrackModal" class="modal-overlay" @click.self="showAddTrackModal = false">
      <div class="modal-content">
        <h3 class="modal-title">添加歌曲</h3>
        <div class="modal-tabs">
          <button class="modal-tab" :class="{ active: addTrackSource === 'local' }" @click="addTrackSource = 'local'">本地文件</button>
          <button class="modal-tab" :class="{ active: addTrackSource === 'url' }" @click="addTrackSource = 'url'">在线音频</button>
        </div>
        <div class="modal-fields">
          <input v-model="addTrackPath" class="input" :placeholder="addTrackSource === 'local' ? '输入本地文件路径，如 D:\\Music\\song.mp3' : '输入音频 URL，如 https://example.com/song.mp3'" />
          <input v-model="addTrackName" class="input" placeholder="歌曲名称（可选）" />
          <input v-model="addTrackArtist" class="input" placeholder="艺术家（可选）" />
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showAddTrackModal = false">取消</button>
          <button class="btn btn-pink" :disabled="!addTrackPath.trim()" @click="addTrack">添加</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.player-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #fff;
  color: #333;
}

.main-area {
  flex: 1;
  display: flex;
  min-height: 0;
}

/* Sidebar */
.sidebar {
  width: 220px;
  background: #f8f9fa;
  border-right: 1px solid #e9ecef;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid #e9ecef;
}

.sidebar-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sidebar-title {
  font-size: 13px;
  font-weight: 600;
  color: #495057;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.sidebar-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.playlist-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 2px;
  transition: background 0.15s;
  color: #868e96;
}

.playlist-item:hover {
  background: #e9ecef;
  color: #333;
}

.playlist-item.active {
  background: #fce4ec;
  color: #e91e63;
}

.playlist-name {
  font-size: 13px;
  font-weight: 500;
  color: inherit;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.playlist-count {
  font-size: 11px;
  color: #adb5bd;
  margin-top: 1px;
}

.playlist-actions {
  display: none;
  gap: 2px;
  align-items: center;
}

.playlist-item:hover .playlist-actions {
  display: flex;
}

.playlist-input-row {
  display: flex;
  gap: 4px;
  margin-top: 8px;
}

/* Track area */
.track-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: #fff;
}

.track-header {
  padding: 16px 20px;
  border-bottom: 1px solid #e9ecef;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
}

.track-title {
  font-size: 16px;
  font-weight: 700;
  color: #212529;
}

.track-subtitle {
  font-size: 12px;
  color: #adb5bd;
}

.track-actions {
  display: flex;
  gap: 8px;
}

.track-list {
  flex: 1;
  overflow-y: auto;
}

.track-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 20px;
  cursor: pointer;
  transition: background 0.12s;
  border-radius: 0;
}

.track-row:hover {
  background: #f8f9fa;
}

.track-row.active {
  background: #fce4ec;
}

.track-index {
  width: 24px;
  text-align: right;
  flex-shrink: 0;
}

.index-num {
  font-size: 12px;
  color: #ced4da;
}

.playing-indicator {
  color: #e91e63;
  font-size: 14px;
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.track-info {
  flex: 1;
  min-width: 0;
}

.track-name {
  font-size: 13px;
  font-weight: 500;
  color: #212529;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.track-meta {
  font-size: 11px;
  color: #adb5bd;
  margin-top: 1px;
}

.track-row-actions {
  display: none;
  gap: 2px;
  align-items: center;
}

.track-row:hover .track-row-actions {
  display: flex;
}

/* Empty state */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #adb5bd;
  font-size: 14px;
  gap: 4px;
}

.empty-icon {
  width: 48px;
  height: 48px;
  color: #dee2e6;
  margin-bottom: 8px;
}

.empty-hint {
  font-size: 12px;
  color: #adb5bd;
  text-align: center;
  padding: 20px 8px;
}

/* Player bar */
.player-bar {
  display: flex;
  align-items: center;
  padding: 12px 20px;
  background: #f8f9fa;
  border-top: 1px solid #e9ecef;
  gap: 20px;
}

.bar-track-info {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 240px;
  flex-shrink: 0;
}

.bar-cover {
  width: 44px;
  height: 44px;
  border-radius: 8px;
  background: linear-gradient(135deg, #e91e63, #9c27b0);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.bar-cover-icon {
  width: 20px;
  height: 20px;
  color: #fff;
}

.bar-track-text {
  flex: 1;
  min-width: 0;
}

.bar-track-name {
  font-size: 13px;
  font-weight: 500;
  color: #212529;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bar-track-artist {
  font-size: 11px;
  color: #adb5bd;
}

.bar-controls {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  max-width: 500px;
  margin: 0 auto;
}

.bar-buttons {
  display: flex;
  align-items: center;
  gap: 16px;
}

.bar-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #adb5bd;
  transition: all 0.15s;
}

.bar-btn:hover {
  color: #333;
  background: #e9ecef;
}

.bar-btn svg {
  width: 16px;
  height: 16px;
}

.bar-play-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: none;
  background: #e91e63;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
  box-shadow: 0 2px 8px rgba(233, 30, 99, 0.3);
}

.bar-play-btn:hover {
  background: #d81b60;
  transform: scale(1.05);
  box-shadow: 0 4px 12px rgba(233, 30, 99, 0.4);
}

.bar-play-btn svg {
  width: 18px;
  height: 18px;
  color: #fff;
}

.bar-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.bar-time {
  font-size: 11px;
  color: #adb5bd;
  width: 36px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.bar-track-bg {
  flex: 1;
  height: 4px;
  background: #dee2e6;
  border-radius: 2px;
  position: relative;
  cursor: pointer;
}

.bar-track-fill {
  height: 100%;
  background: #e91e63;
  border-radius: 2px;
  pointer-events: none;
  max-width: 100%;
}

.bar-seek {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: pointer;
  margin: 0;
}

.bar-seek::-webkit-slider-thumb {
  appearance: none;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #e91e63;
  cursor: pointer;
}

.bar-extras {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 200px;
  flex-shrink: 0;
  justify-content: flex-end;
}

.bar-mode-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: none;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #adb5bd;
  transition: all 0.15s;
}

.bar-mode-btn:hover {
  color: #333;
  background: #e9ecef;
}

.bar-volume {
  display: flex;
  align-items: center;
  gap: 6px;
}

.volume-slider {
  width: 80px;
  height: 4px;
  appearance: none;
  background: #dee2e6;
  border-radius: 2px;
  outline: none;
  cursor: pointer;
}

.volume-slider::-webkit-slider-thumb {
  appearance: none;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #e91e63;
  cursor: pointer;
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
  backdrop-filter: blur(4px);
}

.modal-content {
  background: #fff;
  border-radius: 16px;
  padding: 24px;
  width: 380px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  border: 1px solid #e9ecef;
}

.modal-title {
  font-size: 16px;
  font-weight: 600;
  color: #212529;
  margin-bottom: 16px;
}

.modal-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.modal-tab {
  flex: 1;
  height: 34px;
  border-radius: 8px;
  border: none;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  background: #f1f3f5;
  color: #868e96;
}

.modal-tab:hover {
  background: #e9ecef;
  color: #495057;
}

.modal-tab.active {
  background: #e91e63;
  color: #fff;
}

.modal-fields {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 16px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* Shared component styles */
.input {
  height: 36px;
  border-radius: 8px;
  border: 1px solid #dee2e6;
  background: #fff;
  color: #333;
  padding: 0 12px;
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s;
  box-sizing: border-box;
}

.input:focus {
  border-color: #e91e63;
}

.input-xs {
  height: 28px;
  border-radius: 6px;
  border: 1px solid #dee2e6;
  background: #fff;
  color: #333;
  padding: 0 8px;
  font-size: 12px;
  outline: none;
  box-sizing: border-box;
}

.input-xs:focus {
  border-color: #e91e63;
}

.btn {
  height: 32px;
  border-radius: 8px;
  border: none;
  padding: 0 14px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: all 0.15s;
}

.btn-pink {
  background: #e91e63;
  color: #fff;
}

.btn-pink:hover {
  background: #d81b60;
}

.btn-pink:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-purple {
  background: #9c27b0;
  color: #fff;
}

.btn-purple:hover {
  background: #8e24aa;
}

.btn-ghost {
  background: transparent;
  color: #868e96;
  border: 1px solid #dee2e6;
}

.btn-ghost:hover {
  background: #f1f3f5;
  color: #333;
}

.btn-xs {
  height: 28px;
  border-radius: 6px;
  border: none;
  padding: 0 10px;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  box-sizing: border-box;
  flex-shrink: 0;
}

.btn-icon {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.btn-icon-xs {
  width: 24px;
  height: 24px;
  border-radius: 4px;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  color: #adb5bd;
  transition: all 0.15s;
}

.btn-icon-xs:hover {
  background: #e9ecef;
  color: #495057;
}

.btn-icon-danger:hover {
  background: #fff0f3;
  color: #e91e63;
}

.icon-sm {
  width: 16px;
  height: 16px;
}

.icon-xs {
  width: 12px;
  height: 12px;
}

.shrink-0 {
  flex-shrink: 0;
}

.bar-empty {
  flex: 1;
  text-align: center;
  font-size: 13px;
  color: #adb5bd;
}

/* Scrollbar */
.sidebar-list::-webkit-scrollbar,
.track-list::-webkit-scrollbar {
  width: 6px;
}

.sidebar-list::-webkit-scrollbar-track,
.track-list::-webkit-scrollbar-track {
  background: transparent;
}

.sidebar-list::-webkit-scrollbar-thumb,
.track-list::-webkit-scrollbar-thumb {
  background: #333;
  border-radius: 3px;
}

.sidebar-list::-webkit-scrollbar-thumb:hover,
.track-list::-webkit-scrollbar-thumb:hover {
  background: #555;
}
</style>
