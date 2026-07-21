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
  source: 'local' | 'url' | 'cloud'
  path: string
  fileId?: number
  itemId?: number
  artist?: string
  size?: number
  mime?: string
}

interface PlaylistInfo {
  id: string
  name: string
  source: 'local' | 'cloud'
  serverId?: number
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

const addTrackSource = ref<'local' | 'url'>('local')
const addTrackPath = ref('')
const addTrackName = ref('')
const addTrackArtist = ref('')
const showAddTrackModal = ref(false)
const renamingPlaylistId = ref<string | null>(null)
const renameName = ref('')
const cloudAudioList = ref<any[]>([])
const cloudAddLoading = ref(false)
const cloudSelectedIds = ref<Set<number>>(new Set())

const showNewPlaylist = ref(false)
const newPlaylistSource = ref<'local' | 'cloud'>('local')
const newPlaylistName = ref('')
const serverConfig = ref<{ serverUrl: string; token: string }>({ serverUrl: '', token: '' })

const activeTrack = computed(() => props.data.currentTrack)
const activeIsPlaying = computed(() => props.data.isPlaying)
const activePosition = computed(() => localCurrentTime.value || props.data.currentTime)
const activeDuration = computed(() => localDuration.value || props.data.duration)

const progressPercent = computed(() => {
  const dur = activeDuration.value
  const cur = activePosition.value
  return dur ? (cur / dur) * 100 : 0
})

const activePlaylist = computed(() => {
  return props.data.playlists.find(p => p.id === selectedPlaylistId.value) || null
})

const activeTracks = computed(() => {
  if (!activePlaylist.value) return []
  return activePlaylist.value.trackIds.map(id => props.data.tracks[id]).filter(Boolean)
})

function getAudioUrl(track: Track | null): string {
  if (!track) return ''
  if (track.source === 'cloud' && track.fileId) {
    const { serverUrl, token } = serverConfig.value
    return `${serverUrl}/api/files/${track.fileId}/stream?token=${token}`
  }
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
  if (localCurrentTime.value > 0) {
    props.execute('updateProgress', { currentTime: localCurrentTime.value, duration: localDuration.value })
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
      try { await audioRef.value.play(); localIsPlaying.value = true }
      catch (e) { console.error('Audio play error:', e) }
    }
  }
}, { deep: true })

watch(() => props.data.isPlaying, async (playing) => {
  if (!audioRef.value || !audioRef.value.src) return
  if (playing) {
    try { await audioRef.value.play(); localIsPlaying.value = true }
    catch (e) { console.error('Audio resume error:', e) }
  } else {
    audioRef.value.pause(); localIsPlaying.value = false
  }
})

watch(() => props.data.volume, (vol) => {
  if (audioRef.value) { audioRef.value.volume = vol / 100 }
})

onMounted(async () => {
  const cfg = await props.execute('getCloudStreamBaseUrl')
  if (cfg) serverConfig.value = cfg as any
  if (audioRef.value) { audioRef.value.volume = props.data.volume / 100 }
  if (!selectedPlaylistId.value && props.data.currentPlaylistId) {
    selectedPlaylistId.value = props.data.currentPlaylistId
  }
  if (props.data.currentTrack) {
    const url = getAudioUrl(props.data.currentTrack)
    if (audioRef.value && url) {
      audioRef.value.src = url
      if (props.data.isPlaying) { audioRef.value.play().catch(() => {}); localIsPlaying.value = true }
    }
  }
  window.mqbox?.player?.onUpdated(() => props.refresh?.())
})

onUnmounted(() => {
  if (audioRef.value) { audioRef.value.pause(); audioRef.value.removeAttribute('src') }
})

async function handlePlay(trackId?: string) {
  if (trackId) { await props.execute('play', { trackId }) }
  else { await props.execute('play', {}) }
}

async function handlePause() {
  await props.execute('pause'); localIsPlaying.value = false
}

async function handlePlayPause() {
  if (activeIsPlaying.value) { await handlePause() }
  else { await handlePlay() }
}

async function handleNext() {
  await props.execute('next')
}

async function handlePrev() {
  await props.execute('prev')
}

async function handleSeek(e: Event) {
  const target = e.target as HTMLInputElement
  const time = parseFloat(target.value)
  if (audioRef.value) { audioRef.value.currentTime = time }
  localCurrentTime.value = time
  await props.execute('seek', { time })
}

async function selectPlaylist(id: string) {
  selectedPlaylistId.value = id
  await props.execute('selectPlaylist', { playlistId: id })
  refreshUI()
}

async function confirmNewPlaylist() {
  const name = newPlaylistName.value.trim()
  if (!name) { showNewPlaylist.value = false; return }
  await props.execute('createPlaylist', { name, source: newPlaylistSource.value })
  newPlaylistName.value = ''; showNewPlaylist.value = false
  refreshUI()
}

async function deletePlaylist(id: string) {
  await props.execute('deletePlaylist', { playlistId: id })
  if (selectedPlaylistId.value === id) selectedPlaylistId.value = null
  refreshUI()
}

function startRename(pl: any) { renamingPlaylistId.value = pl.id; renameName.value = pl.name }
async function confirmRename() {
  if (renamingPlaylistId.value && renameName.value.trim()) {
    await props.execute('renamePlaylist', { playlistId: renamingPlaylistId.value, name: renameName.value.trim() })
  }
  renamingPlaylistId.value = null; refreshUI()
}

async function addTrack() {
  if (!activePlaylist.value) return
  const pl = activePlaylist.value
  if (pl.source === 'cloud') {
    if (cloudSelectedIds.value.size === 0) return
    for (const fileId of cloudSelectedIds.value) {
      try { await props.execute('addTrack', { playlistId: pl.id, fileId, source: 'cloud' }) }
      catch (e) { console.error(e) }
    }
    cloudSelectedIds.value = new Set()
    await props.execute('selectPlaylist', { playlistId: pl.id })
  } else {
    if (!addTrackPath.value.trim()) return
    const name = addTrackName.value.trim() || addTrackPath.value.split(/[/\\]/).pop() || '未知'
    await props.execute('addTrack', {
      playlistId: pl.id, name, path: addTrackPath.value.trim(),
      source: addTrackSource.value, artist: addTrackArtist.value.trim() || undefined,
    })
    addTrackPath.value = ''; addTrackName.value = ''; addTrackArtist.value = ''
  }
  showAddTrackModal.value = false
  refreshUI()
}

async function openAddTrackModal() {
  if (!activePlaylist.value) return
  if (activePlaylist.value.source === 'cloud') {
    cloudSelectedIds.value = new Set()
    cloudAudioList.value = []
    showAddTrackModal.value = true
    cloudAddLoading.value = true
    const list = await props.execute('cloudListAudioFiles')
    if (Array.isArray(list)) cloudAudioList.value = list
    cloudAddLoading.value = false
  } else {
    showAddTrackModal.value = true
  }
}

function toggleCloudFile(fileId: number) {
  const s = new Set(cloudSelectedIds.value)
  if (s.has(fileId)) s.delete(fileId); else s.add(fileId)
  cloudSelectedIds.value = s
}

async function removeTrack(trackId: string) {
  if (!activePlaylist.value) return
  await props.execute('removeTrack', { playlistId: activePlaylist.value.id, trackId })
  refreshUI()
}
async function moveTrackUp(trackId: string) {
  if (!activePlaylist.value) return
  await props.execute('moveTrack', { playlistId: activePlaylist.value.id, trackId, direction: 'up' })
  refreshUI()
}
async function moveTrackDown(trackId: string) {
  if (!activePlaylist.value) return
  await props.execute('moveTrack', { playlistId: activePlaylist.value.id, trackId, direction: 'down' })
  refreshUI()
}
async function clearActivePlaylist() {
  if (!activePlaylist.value) return
  await props.execute('clearPlaylist', { playlistId: activePlaylist.value.id })
  refreshUI()
}
async function importDirectory() {
  if (!activePlaylist.value) return
  await props.execute('importDirectory', { playlistId: activePlaylist.value.id })
  refreshUI()
}
function refreshUI() { setTimeout(() => props.refresh?.(), 50) }
</script>

<template>
  <div class="player-page">
    <audio ref="audioRef" preload="auto" @ended="handleNext" @timeupdate="onTimeUpdate" @durationchange="onDurationChange" />

    <div class="main-area">
      <!-- Sidebar -->
      <div class="sidebar">
        <div class="sidebar-header">
          <div class="sidebar-title-row">
            <span class="sidebar-title">歌单</span>
            <button class="btn-icon btn-pink" @click="showNewPlaylist = true; newPlaylistSource = 'local'; newPlaylistName = ''" title="新建歌单">
              <svg class="icon-sm" viewBox="0 0 24 24" fill="currentColor"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>
            </button>
          </div>
        </div>

        <div class="sidebar-list">
          <div class="group-label">本地歌单</div>
          <div v-if="data.playlists.filter(p => p.source === 'local').length === 0" class="empty-hint">暂无本地歌单</div>
          <div v-for="pl in data.playlists.filter(p => p.source === 'local')" :key="pl.id" class="playlist-item" :class="{ active: selectedPlaylistId === pl.id }" @click="selectPlaylist(pl.id)">
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
              <button class="btn-icon-xs" title="重命名" @click.stop="startRename(pl)"><svg class="icon-xs" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>
              <button class="btn-icon-xs btn-icon-danger" title="删除" @click.stop="deletePlaylist(pl.id)"><svg class="icon-xs" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
            </div>
          </div>

          <div class="group-label" style="margin-top:12px;">云端歌单</div>
          <div v-if="data.playlists.filter(p => p.source === 'cloud').length === 0" class="empty-hint">暂无云端歌单</div>
          <div v-for="pl in data.playlists.filter(p => p.source === 'cloud')" :key="pl.id" class="playlist-item" :class="{ active: selectedPlaylistId === pl.id }" @click="selectPlaylist(pl.id)">
            <svg class="icon-sm shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/></svg>
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
              <button class="btn-icon-xs" title="重命名" @click.stop="startRename(pl)"><svg class="icon-xs" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>
              <button class="btn-icon-xs btn-icon-danger" title="删除" @click.stop="deletePlaylist(pl.id)"><svg class="icon-xs" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
            </div>
          </div>
        </div>
      </div>

      <!-- Track list -->
      <div class="track-area">
        <div class="track-header">
          <div>
            <h2 class="track-title">{{ activePlaylist?.name || '选择歌单' }}</h2>
            <span class="track-subtitle">{{ activeTracks.length }} 首歌曲<template v-if="activePlaylist"> · {{ activePlaylist.source === 'cloud' ? '云端' : '本地' }}</template></span>
          </div>
          <div class="track-actions" v-if="activePlaylist">
            <button class="btn btn-pink" @click="openAddTrackModal">
              <svg class="icon-sm" viewBox="0 0 24 24" fill="currentColor"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>
              添加
            </button>
            <button v-if="activePlaylist.source === 'local'" class="btn btn-purple" @click="importDirectory">
              <svg class="icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-6l-2-2H5a2 2 0 0 0-2 2z"/></svg>
              导入文件夹
            </button>
            <button class="btn btn-ghost" @click="clearActivePlaylist">清空</button>
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
                  <span>{{ track.source === 'cloud' ? '云端' : (track.source === 'url' ? '在线' : '本地') }}</span>
                </div>
              </div>
              <div class="track-row-actions">
                <button class="btn-icon-xs" title="上移" @click.stop="moveTrackUp(track.id)"><svg class="icon-xs" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 15l-6-6-6 6"/></svg></button>
                <button class="btn-icon-xs" title="下移" @click.stop="moveTrackDown(track.id)"><svg class="icon-xs" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg></button>
                <button class="btn-icon-xs btn-icon-danger" title="移除" @click.stop="removeTrack(track.id)"><svg class="icon-xs" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Bottom player bar -->
    <div class="player-bar">
      <template v-if="activeTrack">
        <div class="bar-track-info">
          <div class="bar-cover">
            <svg class="bar-cover-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>
          </div>
          <div class="bar-track-text">
            <div class="bar-track-name">{{ activeTrack.name }}</div>
            <div class="bar-track-artist">{{ activeTrack.artist || (activeTrack.source === 'cloud' ? '云端音频' : (activeTrack.source === 'url' ? '在线音频' : '本地文件')) }}</div>
          </div>
        </div>

        <div class="bar-controls">
          <div class="bar-buttons">
            <button class="bar-btn" @click="handlePrev" title="上一首"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/></svg></button>
            <button class="bar-play-btn" @click="handlePlayPause" title="播放/暂停">
              <svg v-if="activeIsPlaying" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
              <svg v-else viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
            </button>
            <button class="bar-btn" @click="handleNext" title="下一首"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg></button>
          </div>
          <div class="bar-progress">
            <span class="bar-time">{{ formatTime(activePosition) }}</span>
            <div class="bar-track-bg">
              <div class="bar-track-fill" :style="{ width: progressPercent + '%' }"></div>
              <input type="range" class="bar-seek" :value="activePosition" :max="activeDuration || 100" step="0.1" @input="handleSeek" />
            </div>
            <span class="bar-time">{{ formatTime(activeDuration) }}</span>
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
            <input type="range" class="volume-slider" :value="data.volume" max="100" @input="execute('setVolume', { volume: parseInt(($event.target as HTMLInputElement).value) })" />
          </div>
        </div>
      </template>
      <div v-else class="bar-empty">选择歌曲开始播放</div>
    </div>

    <!-- New Playlist Modal -->
    <div v-if="showNewPlaylist" class="modal-overlay" @click.self="showNewPlaylist = false">
      <div class="modal-content" style="max-width:360px;">
        <h3 class="modal-title">新建歌单</h3>
        <div class="modal-tabs">
          <button class="modal-tab" :class="{ active: newPlaylistSource === 'local' }" @click="newPlaylistSource = 'local'">本地</button>
          <button class="modal-tab" :class="{ active: newPlaylistSource === 'cloud' }" @click="newPlaylistSource = 'cloud'">云端</button>
        </div>
        <input v-model="newPlaylistName" class="input" placeholder="歌单名称" @keyup.enter="confirmNewPlaylist" />
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showNewPlaylist = false">取消</button>
          <button class="btn btn-pink" :disabled="!newPlaylistName.trim()" @click="confirmNewPlaylist">创建</button>
        </div>
      </div>
    </div>

    <!-- Add Track Modal -->
    <div v-if="showAddTrackModal" class="modal-overlay" @click.self="showAddTrackModal = false">
      <div v-if="activePlaylist?.source !== 'cloud'" class="modal-content">
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
      <div v-else class="modal-content" style="max-width:480px;max-height:500px;display:flex;flex-direction:column;">
        <h3 class="modal-title">添加歌曲到云端歌单</h3>
        <div v-if="cloudAddLoading" style="text-align:center;padding:20px;color:#868e96;">加载中...</div>
        <div v-else style="flex:1;overflow-y:auto;padding:8px 0;">
          <div v-for="f in cloudAudioList" :key="f.file_id" class="playlist-item" :class="{ active: cloudSelectedIds.has(f.file_id) }" @click="toggleCloudFile(f.file_id)" style="display:flex;align-items:center;gap:8px;padding:8px 12px;border-radius:8px;cursor:pointer;margin-bottom:2px;">
            <svg style="width:16px;height:16px;flex-shrink:0;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
            <div style="flex:1;min-width:0;">
              <div style="font-size:13px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ f.name }}</div>
            </div>
            <svg v-if="cloudSelectedIds.has(f.file_id)" style="width:18px;height:18px;flex-shrink:0;color:#007aff;" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
          </div>
          <div v-if="cloudAudioList.length === 0 && !cloudAddLoading" style="text-align:center;padding:20px;color:#868e96;">没有找到音频文件</div>
        </div>
        <div class="modal-actions" style="border-top:1px solid #eee;padding-top:12px;">
          <span style="font-size:12px;color:#868e96;margin-right:auto;">已选 {{ cloudSelectedIds.size }} 项</span>
          <button class="btn btn-ghost" @click="showAddTrackModal = false">取消</button>
          <button class="btn btn-pink" :disabled="cloudSelectedIds.size === 0" @click="addTrack">添加 ({{ cloudSelectedIds.size }})</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.player-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f8f9fa;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
.main-area { flex: 1; display: flex; min-height: 0; }

/* Sidebar */
.sidebar { width: 220px; background: #f8f9fa; border-right: 1px solid #e9ecef; display:flex; flex-direction:column; flex-shrink:0; }
.sidebar-header { padding: 16px; border-bottom: 1px solid #e9ecef; }
.sidebar-title-row { display: flex; align-items: center; justify-content: space-between; }
.sidebar-title { font-size: 13px; font-weight: 600; color: #495057; text-transform: uppercase; letter-spacing: 0.5px; }
.sidebar-list { flex: 1; overflow-y: auto; padding: 8px; }
.group-label { font-size: 11px; font-weight: 600; color: #adb5bd; text-transform: uppercase; letter-spacing: 0.5px; padding: 8px 10px 4px; }
.playlist-item { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 8px; cursor: pointer; margin-bottom: 2px; transition: background 0.15s; color: #868e96; }
.playlist-item:hover { background: #e9ecef; color: #333; }
.playlist-item.active { background: #fce4ec; color: #e91e63; }
.playlist-name { font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.playlist-count { font-size: 11px; color: #adb5bd; margin-top: 1px; }
.playlist-actions { display: none; gap: 2px; align-items: center; }
.playlist-item:hover .playlist-actions { display: flex; }
.empty-hint { padding: 16px; text-align: center; font-size: 12px; color: #adb5bd; }

/* Buttons */
.btn-icon { width: 28px; height: 28px; border: none; border-radius: 7px; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.15s; }
.btn-icon.pink { background: #fce4ec; color: #e91e63; }
.btn-icon.pink:hover { background: #f8bbd0; }
.icon-sm { width: 16px; height: 16px; }
.icon-xs { width: 12px; height: 12px; }
.btn-icon-xs { width: 24px; height: 24px; border: none; border-radius: 5px; background: transparent; cursor: pointer; display: flex; align-items: center; justify-content: center; color: #adb5bd; transition: all 0.15s; }
.btn-icon-xs:hover { background: #e9ecef; color: #495057; }
.btn-icon-xs.btn-icon-danger:hover { background: #ffebee; color: #e91e63; }
.input-xs { height: 28px; padding: 0 8px; border: 1px solid #dee2e6; border-radius: 6px; font-size: 12px; outline: none; }
.flex-1 { flex: 1; }
.min-w-0 { min-width: 0; }
.shrink-0 { flex-shrink: 0; }
.w-full { width: 100%; }

/* Track area */
.track-area { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.track-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 24px; border-bottom: 1px solid #e9ecef; }
.track-title { font-size: 18px; font-weight: 600; color: #212529; margin: 0; }
.track-subtitle { font-size: 12px; color: #adb5bd; }
.track-actions { display: flex; gap: 8px; }
.btn { height: 34px; padding: 0 14px; border: none; border-radius: 8px; font-size: 12px; font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; transition: all 0.15s; }
.btn.pink { background: #fce4ec; color: #e91e63; }
.btn.pink:hover { background: #f8bbd0; }
.btn.purple { background: #f3e5f5; color: #9c27b0; }
.btn.purple:hover { background: #e1bee7; }
.btn-ghost { background: transparent; color: #868e96; }
.btn-ghost:hover { background: #e9ecef; color: #495057; }
.track-list { flex: 1; overflow-y: auto; }
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: #adb5bd; gap: 8px; }
.empty-icon { width: 48px; height: 48px; }
.track-row { display: flex; align-items: center; padding: 8px 24px; cursor: pointer; transition: background 0.15s; }
.track-row:hover { background: #f1f3f5; }
.track-row.active { background: #fce4ec; }
.track-index { width: 32px; text-align: center; font-size: 12px; color: #adb5bd; flex-shrink: 0; }
.playing-indicator { color: #e91e63; font-size: 14px; }
.index-num { color: #adb5bd; }
.track-info { flex: 1; min-width: 0; }
.track-name { font-size: 13px; font-weight: 500; color: #212529; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.track-meta { font-size: 11px; color: #adb5bd; margin-top: 1px; }
.track-row-actions { display: none; gap: 2px; }
.track-row:hover .track-row-actions { display: flex; }

/* Bottom player bar */
.player-bar { height: 72px; background: #fff; border-top: 1px solid #e9ecef; display: flex; align-items: center; padding: 0 24px; gap: 24px; flex-shrink: 0; }
.bar-track-info { display: flex; align-items: center; gap: 12px; min-width: 160px; flex-shrink: 0; }
.bar-cover { width: 44px; height: 44px; border-radius: 8px; background: #f1f3f5; display: flex; align-items: center; justify-content: center; }
.bar-cover-icon { width: 22px; height: 22px; color: #adb5bd; }
.bar-track-text { min-width: 0; }
.bar-track-name { font-size: 13px; font-weight: 500; color: #212529; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bar-track-artist { font-size: 11px; color: #adb5bd; }
.bar-controls { flex: 1; display: flex; align-items: center; gap: 16px; }
.bar-buttons { display: flex; align-items: center; gap: 4px; }
.bar-btn { width: 32px; height: 32px; border: none; border-radius: 8px; background: transparent; cursor: pointer; display: flex; align-items: center; justify-content: center; color: #495057; transition: all 0.15s; }
.bar-btn:hover { background: #f1f3f5; }
.bar-btn svg { width: 18px; height: 18px; }
.bar-play-btn { width: 40px; height: 40px; border: none; border-radius: 50%; background: #fce4ec; cursor: pointer; display: flex; align-items: center; justify-content: center; color: #e91e63; transition: all 0.15s; }
.bar-play-btn:hover { background: #f8bbd0; }
.bar-play-btn svg { width: 22px; height: 22px; }
.bar-progress { flex: 1; display: flex; align-items: center; gap: 8px; }
.bar-time { font-size: 11px; color: #868e96; min-width: 35px; }
.bar-track-bg { flex: 1; height: 4px; background: #e9ecef; border-radius: 2px; position: relative; }
.bar-track-fill { height: 100%; background: #e91e63; border-radius: 2px; pointer-events: none; }
.bar-seek { position: absolute; inset: -6px 0; width: 100%; opacity: 0; cursor: pointer; }
.bar-extras { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.bar-mode-btn { width: 28px; height: 28px; border: none; border-radius: 6px; background: transparent; cursor: pointer; display: flex; align-items: center; justify-content: center; color: #868e96; transition: all 0.15s; }
.bar-mode-btn:hover { background: #f1f3f5; color: #495057; }
.bar-volume { display: flex; align-items: center; gap: 6px; }
.bar-volume svg { width: 16px; height: 16px; color: #868e96; }
.volume-slider { width: 80px; height: 4px; }
.bar-empty { width: 100%; text-align: center; font-size: 13px; color: #adb5bd; }

/* Modal */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-content { background: #fff; border-radius: 16px; padding: 24px; min-width: 380px; max-width: 90vw; box-shadow: 0 20px 60px rgba(0,0,0,0.2); }
.modal-title { font-size: 16px; font-weight: 600; margin: 0 0 16px; }
.modal-tabs { display: flex; gap: 4px; margin-bottom: 16px; background: #f1f3f5; border-radius: 8px; padding: 3px; }
.modal-tab { flex: 1; height: 34px; border: none; border-radius: 6px; background: transparent; font-size: 12px; cursor: pointer; transition: all 0.15s; }
.modal-tab.active { background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.1); font-weight: 500; }
.modal-fields { display: flex; flex-direction: column; gap: 10px; }
.input { height: 36px; padding: 0 12px; border: 1px solid #dee2e6; border-radius: 8px; font-size: 13px; outline: none; transition: border-color 0.15s; }
.input:focus { border-color: #e91e63; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
