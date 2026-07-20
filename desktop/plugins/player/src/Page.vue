<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'

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
  close: () => void
}

const props = defineProps<Props>()

const audioRef = ref<HTMLAudioElement | null>(null)
const localCurrentTime = ref(0)
const localDuration = ref(0)
const localIsPlaying = ref(false)
const selectedPlaylistId = ref<string | null>(null)
const newPlaylistName = ref('')
const showNewPlaylistInput = ref(false)
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

const getModeIcon = computed(() => {
  if (props.data.playMode === 'sequence') return '▶▶'
  if (props.data.playMode === 'loop') return '🔁'
  return '🎲'
})

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

async function handleNext() {
  await props.execute('next')
}

async function handlePrev() {
  await props.execute('prev')
}

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
  if (audioRef.value) {
    audioRef.value.currentTime = time
  }
  localCurrentTime.value = time
  await props.execute('seek', { time })
}

async function createPlaylist() {
  if (!newPlaylistName.value.trim()) return
  await props.execute('createPlaylist', { name: newPlaylistName.value.trim() })
  newPlaylistName.value = ''
  showNewPlaylistInput.value = false
}

async function deletePlaylist(id: string) {
  await props.execute('deletePlaylist', { playlistId: id })
  if (selectedPlaylistId.value === id) {
    selectedPlaylistId.value = null
  }
}

async function startRename(pl: PlaylistInfo) {
  renamingPlaylistId.value = pl.id
  renameName.value = pl.name
}

async function confirmRename() {
  if (renamingPlaylistId.value && renameName.value.trim()) {
    await props.execute('renamePlaylist', {
      playlistId: renamingPlaylistId.value,
      name: renameName.value.trim()
    })
  }
  renamingPlaylistId.value = null
}

async function addTrack() {
  if (!addTrackPath.value.trim() || !activePlaylist.value) return
  const name = addTrackName.value.trim() || addTrackPath.value.split(/[/\\]/).pop() || '未知'
  await props.execute('addTrack', {
    playlistId: activePlaylist.value.id,
    name,
    path: addTrackPath.value.trim(),
    source: addTrackSource.value,
    artist: addTrackArtist.value.trim() || undefined
  })
  addTrackPath.value = ''
  addTrackName.value = ''
  addTrackArtist.value = ''
  showAddTrackModal.value = false
}

async function removeTrack(playlistId: string, trackId: string) {
  await props.execute('removeTrack', { playlistId, trackId })
}

async function moveTrackUp(playlistId: string, trackId: string) {
  await props.execute('moveTrack', { playlistId, trackId, direction: 'up' })
}

async function moveTrackDown(playlistId: string, trackId: string) {
  await props.execute('moveTrack', { playlistId, trackId, direction: 'down' })
}

async function selectPlaylist(id: string) {
  selectedPlaylistId.value = id
  await props.execute('selectPlaylist', { playlistId: id })
}

async function clearPlaylist(id: string) {
  await props.execute('clearPlaylist', { playlistId: id })
}

async function importDirectory() {
  if (!activePlaylist.value) return
  await props.execute('importDirectory', { playlistId: activePlaylist.value.id })
}
</script>

<template>
  <div class="player-page flex flex-col h-full bg-white">
    <audio ref="audioRef" preload="auto" @ended="handleAudioEnded" @timeupdate="onTimeUpdate" @durationchange="onDurationChange" />

    <div class="flex flex-1 min-h-0">
      <!-- Left: Playlist sidebar -->
      <div class="w-[200px] bg-gray-50 border-r border-gray-200 flex flex-col">
        <div class="p-3 border-b border-gray-200">
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm font-semibold text-gray-700">歌单</span>
            <button
              class="w-6 h-6 rounded-md bg-pink-500 text-white flex items-center justify-center hover:bg-pink-600"
              @click="showNewPlaylistInput = true"
            >
              <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>
              </svg>
            </button>
          </div>
          <div v-if="showNewPlaylistInput" class="flex gap-1">
            <input
              v-model="newPlaylistName"
              class="flex-1 h-7 rounded border border-gray-300 px-2 text-xs focus:border-pink-400 focus:outline-none"
              placeholder="歌单名称"
              @keyup.enter="createPlaylist"
              @keyup.escape="showNewPlaylistInput = false"
            />
            <button class="h-7 px-2 rounded bg-pink-500 text-white text-xs hover:bg-pink-600" @click="createPlaylist">确定</button>
          </div>
        </div>

        <div class="flex-1 overflow-y-auto p-2">
          <div v-if="data.playlists.length === 0" class="text-xs text-gray-400 text-center py-4">
            暂无歌单，点击 + 创建
          </div>
          <div
            v-for="pl in data.playlists"
            :key="pl.id"
            class="group flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer mb-0.5"
            :class="selectedPlaylistId === pl.id ? 'bg-pink-50 text-pink-700' : 'hover:bg-gray-100 text-gray-700'"
            @click="selectPlaylist(pl.id)"
          >
            <svg class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="currentColor">
              <path d="M4 6h16v2H4zm0 5h16v2H4zm0 5h10v2H4zm14 0v6l5-3z"/>
            </svg>
            <div class="flex-1 min-w-0" v-if="renamingPlaylistId === pl.id">
              <input
                v-model="renameName"
                class="w-full h-5 rounded border border-pink-300 px-1 text-xs"
                @keyup.enter="confirmRename"
                @keyup.escape="renamingPlaylistId = null"
                @blur="confirmRename"
              />
            </div>
            <div v-else class="flex-1 min-w-0">
              <span class="text-xs font-medium truncate block">{{ pl.name }}</span>
              <span class="text-xs text-gray-400">{{ pl.trackIds.length }} 首</span>
            </div>
            <div class="hidden group-hover:flex items-center gap-0.5">
              <button class="w-4 h-4 flex items-center justify-center rounded hover:bg-gray-200" @click.stop="startRename(pl)">
                <svg class="w-3 h-3 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
              <button class="w-4 h-4 flex items-center justify-center rounded hover:bg-red-100" @click.stop="deletePlaylist(pl.id)">
                <svg class="w-3 h-3 text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M18 6L6 18M6 6l12 12"/>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Center: Track list -->
      <div class="flex-1 flex flex-col min-w-0">
        <div class="p-3 border-b border-gray-200 flex items-center justify-between bg-white">
          <div>
            <h2 class="text-sm font-semibold text-gray-800">{{ activePlaylist?.name || '选择歌单' }}</h2>
            <span class="text-xs text-gray-400">{{ activeTracks.length }} 首歌曲</span>
          </div>
          <div class="flex gap-2" v-if="activePlaylist">
            <button
              class="h-7 rounded-md bg-pink-500 text-white text-xs px-3 hover:bg-pink-600 flex items-center gap-1"
              @click="showAddTrackModal = true"
            >
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
                <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>
              </svg>
              添加
            </button>
            <button
              class="h-7 rounded-md bg-purple-500 text-white text-xs px-3 hover:bg-purple-600 flex items-center gap-1"
              @click="importDirectory"
            >
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M3 7v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-6l-2-2H5a2 2 0 0 0-2 2z"/>
              </svg>
              导入文件夹
            </button>
            <button
              class="h-7 rounded-md bg-gray-100 text-gray-600 text-xs px-3 hover:bg-gray-200"
              @click="clearPlaylist(activePlaylist!.id)"
            >
              清空
            </button>
          </div>
        </div>

        <div class="flex-1 overflow-y-auto">
          <div v-if="!activePlaylist" class="flex flex-col items-center justify-center h-full text-gray-400">
            <svg class="w-16 h-16 mb-4 text-gray-300" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
            </svg>
            <span class="text-sm">选择或创建一个歌单</span>
          </div>

          <div v-else-if="activeTracks.length === 0" class="flex flex-col items-center justify-center h-full text-gray-400">
            <svg class="w-12 h-12 mb-3 text-gray-300" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
            </svg>
            <span class="text-sm mb-1">歌单是空的</span>
            <span class="text-xs">点击上方"添加"来添加歌曲</span>
          </div>

          <div v-else>
            <div
              v-for="(track, index) in activeTracks"
              :key="track.id"
              class="group flex items-center gap-2 px-3 py-2 hover:bg-gray-50 cursor-pointer"
              :class="{ 'bg-pink-50': data.currentTrackId === track.id }"
              @click="handlePlay(track.id)"
            >
              <span class="text-xs text-gray-400 w-5 text-right shrink-0">
                <span v-if="data.currentTrackId === track.id && data.isPlaying" class="text-pink-500">♫</span>
                <span v-else>{{ index + 1 }}</span>
              </span>
              <div class="flex-1 min-w-0">
                <div class="text-sm text-gray-800 truncate">{{ track.name }}</div>
                <div class="text-xs text-gray-400 truncate">
                  <span v-if="track.artist">{{ track.artist }} · </span>
                  <span>{{ track.source === 'url' ? '在线' : '本地' }}</span>
                </div>
              </div>
              <div class="hidden group-hover:flex items-center gap-0.5">
                <button class="w-5 h-5 flex items-center justify-center rounded hover:bg-gray-200" @click.stop="moveTrackUp(activePlaylist!.id, track.id)" title="上移">
                  <svg class="w-3 h-3 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 15l-6-6-6 6"/></svg>
                </button>
                <button class="w-5 h-5 flex items-center justify-center rounded hover:bg-gray-200" @click.stop="moveTrackDown(activePlaylist!.id, track.id)" title="下移">
                  <svg class="w-3 h-3 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
                </button>
                <button class="w-5 h-5 flex items-center justify-center rounded hover:bg-red-100" @click.stop="removeTrack(activePlaylist!.id, track.id)" title="移除">
                  <svg class="w-3 h-3 text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Add Track Modal -->
    <div v-if="showAddTrackModal" class="fixed inset-0 bg-black/30 flex items-center justify-center z-50" @click.self="showAddTrackModal = false">
      <div class="bg-white rounded-lg shadow-xl p-4 w-[360px]" @click.stop>
        <h3 class="text-sm font-semibold text-gray-800 mb-3">添加歌曲</h3>
        <div class="flex gap-2 mb-3">
          <button
            class="flex-1 h-8 rounded-md text-xs font-medium"
            :class="addTrackSource === 'local' ? 'bg-pink-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'"
            @click="addTrackSource = 'local'"
          >
            本地文件
          </button>
          <button
            class="flex-1 h-8 rounded-md text-xs font-medium"
            :class="addTrackSource === 'url' ? 'bg-pink-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'"
            @click="addTrackSource = 'url'"
          >
            在线音频
          </button>
        </div>
        <div class="flex flex-col gap-2">
          <input
            v-model="addTrackPath"
            class="h-8 rounded border border-gray-300 px-3 text-sm focus:border-pink-400 focus:outline-none"
            :placeholder="addTrackSource === 'local' ? '输入本地文件路径，如 D:\\Music\\song.mp3' : '输入音频 URL，如 https://example.com/song.mp3'"
          />
          <input
            v-model="addTrackName"
            class="h-8 rounded border border-gray-300 px-3 text-sm focus:border-pink-400 focus:outline-none"
            placeholder="歌曲名称（可选，默认取文件名）"
          />
          <input
            v-model="addTrackArtist"
            class="h-8 rounded border border-gray-300 px-3 text-sm focus:border-pink-400 focus:outline-none"
            placeholder="艺术家（可选）"
          />
        </div>
        <div class="flex justify-end gap-2 mt-3">
          <button class="h-8 rounded-md bg-gray-100 text-gray-600 text-sm px-4 hover:bg-gray-200" @click="showAddTrackModal = false">取消</button>
          <button
            class="h-8 rounded-md bg-pink-500 text-white text-sm px-4 hover:bg-pink-600 disabled:opacity-50"
            :disabled="!addTrackPath.trim()"
            @click="addTrack"
          >
            添加
          </button>
        </div>
      </div>
    </div>

    <!-- Bottom: Now playing bar -->
    <div class="border-t border-gray-200 bg-white px-4 py-3">
      <div v-if="data.currentTrack" class="flex flex-col gap-2">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-lg bg-gradient-to-br from-pink-400 to-pink-600 flex items-center justify-center shadow-sm">
            <svg class="w-5 h-5 text-white" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
            </svg>
          </div>
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-gray-800 truncate">{{ data.currentTrack.name }}</div>
            <div class="text-xs text-gray-400">{{ data.currentTrack.artist || (data.currentTrack.source === 'url' ? '在线音频' : '本地文件') }}</div>
          </div>
          <button
            class="w-7 h-7 rounded-md border border-gray-200 flex items-center justify-center hover:bg-gray-50 text-xs"
            :title="data.playMode === 'sequence' ? '顺序播放' : data.playMode === 'loop' ? '单曲循环' : '随机播放'"
            @click="execute('toggleMode')"
          >
            {{ getModeIcon }}
          </button>
        </div>

        <div class="flex items-center gap-2">
          <span class="text-xs text-gray-500 w-10 text-right">{{ formatTime(localCurrentTime || props.data.currentTime) }}</span>
          <input
            type="range"
            class="flex-1 h-1 rounded-full bg-gray-200 appearance-none cursor-pointer"
            :value="localCurrentTime || props.data.currentTime"
            :max="localDuration || props.data.duration || 100"
            step="0.1"
            @input="handleSeek"
          />
          <span class="text-xs text-gray-500 w-10">{{ formatTime(localDuration || props.data.duration) }}</span>
        </div>

        <div class="flex items-center justify-center gap-3">
          <button
            class="w-9 h-9 rounded-full bg-gray-100 flex items-center justify-center hover:bg-gray-200"
            @click="handlePrev"
          >
            <svg class="w-4 h-4 text-gray-600" viewBox="0 0 24 24" fill="currentColor">
              <path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/>
            </svg>
          </button>
          <button
            class="w-11 h-11 rounded-full bg-pink-500 flex items-center justify-center hover:bg-pink-600 shadow-md"
            @click="handlePlayPause"
          >
            <svg v-if="data.isPlaying" class="w-5 h-5 text-white" viewBox="0 0 24 24" fill="currentColor">
              <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>
            </svg>
            <svg v-else class="w-5 h-5 text-white" viewBox="0 0 24 24" fill="currentColor">
              <path d="M8 5v14l11-7z"/>
            </svg>
          </button>
          <button
            class="w-9 h-9 rounded-full bg-gray-100 flex items-center justify-center hover:bg-gray-200"
            @click="handleNext"
          >
            <svg class="w-4 h-4 text-gray-600" viewBox="0 0 24 24" fill="currentColor">
              <path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/>
            </svg>
          </button>
        </div>

        <div class="flex items-center gap-2">
          <svg class="w-4 h-4 text-gray-500" viewBox="0 0 24 24" fill="currentColor">
            <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
          </svg>
          <input
            type="range"
            class="flex-1 h-1 rounded-full bg-gray-200 appearance-none cursor-pointer"
            :value="data.volume"
            max="100"
            @input="(e: Event) => execute('setVolume', { volume: parseInt((e.target as HTMLInputElement).value) })"
          />
          <span class="text-xs text-gray-500 w-8">{{ data.volume }}%</span>
        </div>
      </div>

      <div v-else class="flex flex-col items-center justify-center py-4 text-gray-400">
        <svg class="w-10 h-10 mb-2 text-gray-300" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
        </svg>
        <span class="text-sm">选择歌曲开始播放</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.player-page {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

input[type="range"]::-webkit-slider-thumb {
  appearance: none;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #E91E63;
  cursor: pointer;
}
</style>