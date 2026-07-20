<script setup lang="ts">
import { computed, ref } from 'vue'

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

const showPlaylistMenu = ref(false)

const progress = computed(() => {
  if (!props.data.duration) return 0
  return (props.data.currentTime / props.data.duration) * 100
})

function formatTime(seconds: number) {
  if (!seconds || isNaN(seconds)) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

const handlePlayPause = () => {
  if (props.data.isPlaying) {
    props.execute('pause')
  } else {
    props.execute('play', { trackId: props.data.currentTrackId })
  }
}

function selectPlaylist(id: string) {
  props.execute('selectPlaylist', { playlistId: id })
}

function playTrack(id: string) {
  props.execute('play', { trackId: id })
  showPlaylistMenu.value = false
}
</script>

<template>
  <div class="player-panel rounded-lg bg-white border border-gray-200 p-2.5 flex flex-col gap-2">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2">
        <div class="w-8 h-8 rounded-lg bg-pink-50 flex items-center justify-center">
          <svg class="w-4.5 h-4.5 text-pink-500" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
          </svg>
        </div>
        <span class="text-sm text-gray-800 font-semibold">播放器</span>
      </div>
      <div class="flex items-center gap-1">
        <button
          class="w-5 h-5 rounded flex items-center justify-center hover:bg-gray-100 text-xs"
          :title="data.playMode === 'sequence' ? '顺序播放' : data.playMode === 'loop' ? '循环播放' : '随机播放'"
          @click="execute('toggleMode')"
        >
          {{ data.playMode === 'sequence' ? '▶▶' : data.playMode === 'loop' ? '🔁' : '🎲' }}
        </button>
        <button class="text-gray-400 cursor-pointer hover:text-gray-600" @click="openPage">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="m9 18 6-6-6-6"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- Now playing -->
    <div v-if="data.currentTrack" class="flex flex-col gap-1.5">
      <div class="flex flex-col">
        <span class="text-xs text-gray-800 truncate font-medium">{{ data.currentTrack.name }}</span>
        <span v-if="data.currentTrack.artist" class="text-xs text-gray-400 truncate">{{ data.currentTrack.artist }}</span>
      </div>

      <div class="flex items-center gap-1">
        <span class="text-xs text-gray-500 w-8">{{ formatTime(data.currentTime) }}</span>
        <div
          class="flex-1 h-1 rounded-full bg-gray-200 overflow-hidden cursor-pointer relative"
          @click="(e: MouseEvent) => execute('seek', { percent: e.offsetX / (e.target as HTMLElement).offsetWidth })"
        >
          <div class="h-full rounded-full bg-pink-500" :style="{ width: progress + '%' }"></div>
        </div>
        <span class="text-xs text-gray-500 w-8">{{ formatTime(data.duration) }}</span>
      </div>
    </div>

    <!-- Controls (centered) + playlist icon (absolute right) -->
    <div class="relative flex items-center justify-center gap-2">
      <button
        class="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center hover:bg-gray-200"
        @click="execute('prev')"
      >
        <svg class="w-3 h-3 text-gray-600" viewBox="0 0 24 24" fill="currentColor">
          <path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/>
        </svg>
      </button>
      <button
        class="w-8 h-8 rounded-full bg-pink-500 flex items-center justify-center hover:bg-pink-600"
        @click="handlePlayPause"
      >
        <svg v-if="data.isPlaying" class="w-4 h-4 text-white" viewBox="0 0 24 24" fill="currentColor">
          <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>
        </svg>
        <svg v-else class="w-4 h-4 text-white" viewBox="0 0 24 24" fill="currentColor">
          <path d="M8 5v14l11-7z"/>
        </svg>
      </button>
      <button
        class="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center hover:bg-gray-200"
        @click="execute('next')"
      >
        <svg class="w-3 h-3 text-gray-600" viewBox="0 0 24 24" fill="currentColor">
          <path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/>
        </svg>
      </button>

      <!-- Playlist icon (absolute right, doesn't affect centering) -->
      <div v-if="data.playlists.length > 0" class="absolute right-0">
        <button
          class="w-6 h-6 rounded-md bg-gray-50 hover:bg-gray-100 flex items-center justify-center border border-gray-200"
          :title="data.currentPlaylist?.name"
          @click="showPlaylistMenu = !showPlaylistMenu"
        >
          <svg class="w-3.5 h-3.5 text-pink-500" viewBox="0 0 24 24" fill="currentColor">
            <path d="M4 6h16v2H4zm0 5h16v2H4zm0 5h10v2H4zm14 0v6l5-3z"/>
          </svg>
        </button>

        <!-- Dropdown: playlist tabs + track list -->
        <div
          v-if="showPlaylistMenu"
          class="absolute bottom-full right-0 mb-1 bg-white rounded-md shadow-lg border border-gray-200 z-50 w-[200px]"
        >
          <!-- Playlist switcher row -->
          <div v-if="data.playlists.length > 1" class="flex gap-0.5 p-1 border-b border-gray-100 overflow-x-auto">
            <button
              v-for="pl in data.playlists"
              :key="pl.id"
              class="shrink-0 px-2 py-1 rounded text-xs whitespace-nowrap"
              :class="data.currentPlaylistId === pl.id ? 'bg-pink-500 text-white' : 'text-gray-500 hover:bg-gray-100'"
              @click="selectPlaylist(pl.id)"
            >
              {{ pl.name }}
            </button>
          </div>

          <!-- Track list -->
          <div class="max-h-48 overflow-y-auto p-1">
            <div v-if="!data.currentPlaylist || data.currentPlaylistTracks.length === 0" class="text-xs text-gray-400 text-center py-3">
              歌单为空
            </div>
            <button
              v-for="(track, index) in data.currentPlaylistTracks"
              :key="track.id"
              class="w-full px-2 py-1 rounded text-left text-xs flex items-center gap-1.5 hover:bg-gray-50"
              :class="{ 'bg-pink-50 text-pink-600': data.currentTrackId === track.id, 'text-gray-600': data.currentTrackId !== track.id }"
              @click="playTrack(track.id)"
            >
              <span class="w-4 text-gray-400 shrink-0">{{ index + 1 }}</span>
              <span class="truncate flex-1">{{ track.name }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!data.currentTrack && data.playlists.length === 0" class="flex items-center justify-center gap-2 py-1">
      <button
        class="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center hover:bg-gray-200"
        @click="openPage"
      >
        <svg class="w-4 h-4 text-gray-600" viewBox="0 0 24 24" fill="currentColor">
          <path d="M8 5v14l11-7z"/>
        </svg>
      </button>
      <span class="text-xs text-gray-400">打开播放器添加歌曲</span>
    </div>
  </div>
</template>

<style scoped>
.player-panel {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
</style>
