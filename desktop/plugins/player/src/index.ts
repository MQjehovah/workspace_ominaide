import Panel from './Panel.vue'
import Page from './Page.vue'

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

interface PlayerStorage {
  playlists: PlaylistInfo[]
  tracks: Record<string, Track>
  currentPlaylistId: string | null
  volume: number
  playMode: 'sequence' | 'loop' | 'shuffle'
}

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).substring(2, 8)
}

let playlists: PlaylistInfo[] = []
let tracks: Record<string, Track> = {}
let currentPlaylistId: string | null = null
let currentTrackId: string | null = null
let isPlaying = false
let currentTime = 0
let duration = 0
let volume = 80
let playMode: 'sequence' | 'loop' | 'shuffle' = 'sequence'

function getState() {
  const currentTrack = currentTrackId ? tracks[currentTrackId] || null : null
  const currentPlaylist = currentPlaylistId ? playlists.find(p => p.id === currentPlaylistId) : null
  const currentPlaylistTracks = currentPlaylist
    ? currentPlaylist.trackIds.map(id => tracks[id]).filter(Boolean)
    : []
  return {
    playlists,
    tracks,
    currentPlaylistId,
    currentPlaylist,
    currentTrackId,
    currentTrack,
    currentPlaylistTracks,
    isPlaying,
    currentTime,
    duration,
    volume,
    playMode
  }
}

export default {
  panel: Panel,
  page: Page,

  async activate(context: any) {
    const saved = await context.storage?.get<PlayerStorage>('playerData')
    if (saved) {
      playlists = saved.playlists || []
      tracks = saved.tracks || {}
      currentPlaylistId = saved.currentPlaylistId || null
      volume = saved.volume ?? 80
      playMode = saved.playMode || 'sequence'
    }

    if (!currentPlaylistId || !playlists.find(p => p.id === currentPlaylistId)) {
      currentPlaylistId = playlists.length > 0 ? playlists[0].id : null
    }

    async function saveState() {
      await context.storage?.set('playerData', {
        playlists,
        tracks,
        currentPlaylistId,
        volume,
        playMode
      })
    }

    context.registerCommand('getPanelData', async () => getState())
    context.registerCommand('getPageData', async () => getState())

    context.registerCommand('createPlaylist', async (args: any) => {
      const name = args?.name || '新建歌单'
      const playlist: PlaylistInfo = {
        id: generateId(),
        name,
        trackIds: []
      }
      playlists.push(playlist)
      await saveState()
      return getState()
    })

    context.registerCommand('deletePlaylist', async (args: any) => {
      const { playlistId } = args
      playlists = playlists.filter(p => p.id !== playlistId)
      if (currentPlaylistId === playlistId) {
        currentPlaylistId = playlists.length > 0 ? playlists[0].id : null
      }
      await saveState()
      return getState()
    })

    context.registerCommand('renamePlaylist', async (args: any) => {
      const { playlistId, name } = args
      const playlist = playlists.find(p => p.id === playlistId)
      if (playlist) {
        playlist.name = name
        await saveState()
      }
      return getState()
    })

    context.registerCommand('selectPlaylist', async (args: any) => {
      currentPlaylistId = args?.playlistId || null
      return getState()
    })

    context.registerCommand('addTrack', async (args: any) => {
      const { playlistId, name, path, source = 'local', artist } = args
      const track: Track = {
        id: generateId(),
        name: name || path.split(/[/\\]/).pop() || '未知',
        source,
        path,
        artist
      }
      tracks[track.id] = track
      const playlist = playlists.find(p => p.id === playlistId)
      if (playlist) {
        playlist.trackIds.push(track.id)
      }
      await saveState()
      return getState()
    })

    context.registerCommand('addTrackById', async (args: any) => {
      const { playlistId, trackId } = args
      const playlist = playlists.find(p => p.id === playlistId)
      if (playlist && tracks[trackId] && !playlist.trackIds.includes(trackId)) {
        playlist.trackIds.push(trackId)
        await saveState()
      }
      return getState()
    })

    context.registerCommand('removeTrack', async (args: any) => {
      const { playlistId, trackId } = args
      const playlist = playlists.find(p => p.id === playlistId)
      if (playlist) {
        playlist.trackIds = playlist.trackIds.filter(id => id !== trackId)
      }
      if (currentTrackId === trackId) {
        isPlaying = false
        currentTrackId = null
        currentTime = 0
        duration = 0
      }
      await saveState()
      return getState()
    })

    context.registerCommand('moveTrack', async (args: any) => {
      const { playlistId, trackId, direction } = args
      const playlist = playlists.find(p => p.id === playlistId)
      if (!playlist) return getState()
      const index = playlist.trackIds.indexOf(trackId)
      if (index === -1) return getState()
      const newIndex = direction === 'up' ? index - 1 : index + 1
      if (newIndex < 0 || newIndex >= playlist.trackIds.length) return getState()
      ;[playlist.trackIds[index], playlist.trackIds[newIndex]] = [playlist.trackIds[newIndex], playlist.trackIds[index]]
      await saveState()
      return getState()
    })

    context.registerCommand('play', async (args: any) => {
      if (args?.trackId) {
        currentTrackId = args.trackId
        isPlaying = true
        currentTime = 0
        const track = tracks[currentTrackId]
        if (track && !currentPlaylistId) {
          const pl = playlists.find(p => p.trackIds.includes(currentTrackId!))
          if (pl) currentPlaylistId = pl.id
        }
      } else if (args?.playlistId) {
        currentPlaylistId = args.playlistId
        const playlist = playlists.find(p => p.id === currentPlaylistId)
        if (playlist && playlist.trackIds.length > 0) {
          currentTrackId = playlist.trackIds[0]
          isPlaying = true
          currentTime = 0
        }
      } else if (currentTrackId) {
        isPlaying = true
      } else if (currentPlaylistId) {
        const playlist = playlists.find(p => p.id === currentPlaylistId)
        if (playlist && playlist.trackIds.length > 0) {
          currentTrackId = playlist.trackIds[0]
          isPlaying = true
          currentTime = 0
        }
      }
      return getState()
    })

    context.registerCommand('pause', async () => {
      isPlaying = false
      return getState()
    })

    context.registerCommand('stop', async () => {
      isPlaying = false
      currentTrackId = null
      currentTime = 0
      duration = 0
      return getState()
    })

    context.registerCommand('next', async () => {
      const playlist = playlists.find(p => p.id === currentPlaylistId)
      if (!playlist || playlist.trackIds.length === 0) return getState()

      const currentIndex = playlist.trackIds.indexOf(currentTrackId || '')
      let nextIndex: number

      if (playMode === 'shuffle') {
        nextIndex = Math.floor(Math.random() * playlist.trackIds.length)
      } else if (playMode === 'loop') {
        nextIndex = currentIndex
      } else {
        nextIndex = (currentIndex + 1) % playlist.trackIds.length
      }

      currentTrackId = playlist.trackIds[nextIndex]
      currentTime = 0
      isPlaying = true

      return getState()
    })

    context.registerCommand('prev', async () => {
      const playlist = playlists.find(p => p.id === currentPlaylistId)
      if (!playlist || playlist.trackIds.length === 0) return getState()

      const currentIndex = playlist.trackIds.indexOf(currentTrackId || '')
      let prevIndex: number

      if (playMode === 'shuffle') {
        prevIndex = Math.floor(Math.random() * playlist.trackIds.length)
      } else if (playMode === 'loop') {
        prevIndex = currentIndex
      } else {
        prevIndex = currentIndex <= 0 ? playlist.trackIds.length - 1 : currentIndex - 1
      }

      currentTrackId = playlist.trackIds[prevIndex]
      currentTime = 0
      isPlaying = true

      return getState()
    })

    context.registerCommand('seek', async (args: any) => {
      if (args) {
        if (args.time !== undefined) {
          currentTime = Math.max(0, Math.min(duration, args.time))
        } else if (args.percent !== undefined) {
          currentTime = Math.max(0, Math.min(duration, duration * args.percent))
        }
      }
      return getState()
    })

    context.registerCommand('setVolume', async (args: any) => {
      if (args?.volume !== undefined) {
        volume = Math.max(0, Math.min(100, args.volume))
        await saveState()
      }
      return getState()
    })

    context.registerCommand('toggleMode', async () => {
      const modes: ('sequence' | 'loop' | 'shuffle')[] = ['sequence', 'loop', 'shuffle']
      const currentIndex = modes.indexOf(playMode)
      playMode = modes[(currentIndex + 1) % modes.length]
      await saveState()
      return getState()
    })

    context.registerCommand('onTrackEnded', async () => {
      const playlist = playlists.find(p => p.id === currentPlaylistId)
      if (!playlist || playlist.trackIds.length === 0) {
        isPlaying = false
        return getState()
      }

      const currentIndex = playlist.trackIds.indexOf(currentTrackId || '')
      let nextIndex: number

      if (playMode === 'shuffle') {
        nextIndex = Math.floor(Math.random() * playlist.trackIds.length)
      } else if (playMode === 'loop') {
        nextIndex = currentIndex
      } else {
        nextIndex = currentIndex + 1
        if (nextIndex >= playlist.trackIds.length) {
          isPlaying = false
          currentTrackId = null
          return getState()
        }
      }

      currentTrackId = playlist.trackIds[nextIndex]
      currentTime = 0
      isPlaying = true

      return getState()
    })

    context.registerCommand('updateProgress', async (args: any) => {
      if (args) {
        if (args.currentTime !== undefined) currentTime = args.currentTime
        if (args.duration !== undefined) duration = args.duration
      }
      return getState()
    })

    context.registerCommand('clearPlaylist', async (args: any) => {
      const playlist = playlists.find(p => p.id === args?.playlistId)
      if (playlist) {
        playlist.trackIds = []
        if (currentPlaylistId === playlist.id) {
          currentTrackId = null
          isPlaying = false
          currentTime = 0
          duration = 0
        }
      }
      await saveState()
      return getState()
    })

    context.registerCommand('importDirectory', async (args: any) => {
      console.log('[player] importDirectory called, files API:', !!context.files, !!context.files?.openDirectory)
      const playlistId = args?.playlistId || currentPlaylistId
      if (!playlistId) return getState()
      const playlist = playlists.find(p => p.id === playlistId)
      if (!playlist) return getState()

      const dirPath = await context.files?.openDirectory?.()
      console.log('[player] openDirectory result:', dirPath)
      if (!dirPath) return getState()

      const audioFiles: { name: string; path: string }[] = await context.files?.listAudio?.(dirPath) || []
      for (const file of audioFiles) {
        const track: Track = {
          id: generateId(),
          name: file.name,
          source: 'local',
          path: file.path
        }
        tracks[track.id] = track
        playlist.trackIds.push(track.id)
      }

      await saveState()
      return getState()
    })

    context.registerSearchProvider({
      keyword: 'play',
      name: '播放器',
      priority: 20,
      onSearch: async (query: string) => {
        if (!query) {
          return [{
            title: '打开播放器',
            subtitle: '管理播放列表',
            icon: 'player',
            action: 'player:open',
            pluginId: 'player'
          }]
        }
        const results: any[] = [{
          title: `播放: ${query}`,
          subtitle: '搜索并播放',
          icon: 'player',
          action: 'player:search',
          actionArgs: { query },
          pluginId: 'player'
        }]
        for (const pl of playlists) {
          for (const tid of pl.trackIds) {
            const t = tracks[tid]
            if (t && t.name.toLowerCase().includes(query.toLowerCase())) {
              results.push({
                title: t.name,
                subtitle: `${pl.name} - ${t.source === 'url' ? '在线' : '本地'}`,
                icon: 'player',
                action: 'player:play',
                actionArgs: { trackId: t.id },
                pluginId: 'player'
              })
            }
          }
        }
        return results
      }
    })
  },

  deactivate() {}
}