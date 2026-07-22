import Panel from './Panel.vue'
import Page from './Page.vue'

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
let pluginCtx: any = null

function getServerConfig(): { serverUrl: string; token: string } {
  try {
    const { join } = require('path')
    const { readFileSync, existsSync } = require('fs')
    const { app } = require('electron')
    const configPath = join(app.getPath('userData'), 'omniaide-config', 'config.json')
    let serverUrl = 'http://localhost:8000'
    let token = ''
    if (existsSync(configPath)) {
      const cfg = JSON.parse(readFileSync(configPath, 'utf-8'))
      serverUrl = cfg.serverUrl || serverUrl
      token = cfg.token || ''
    }
    return { serverUrl, token }
  } catch {
    return { serverUrl: 'http://localhost:8000', token: '' }
  }
}

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
    pluginCtx = context
    const saved = await context.storage?.get<PlayerStorage>('playerData')
    if (saved) {
      playlists = (saved.playlists || []).filter(p => p.source !== 'cloud' && p.name !== '__cloud__')
      tracks = {}
      for (const [id, t] of Object.entries(saved.tracks || {})) {
        if (t.source !== 'cloud') tracks[id] = t
      }
      currentPlaylistId = saved.currentPlaylistId || null
      volume = saved.volume ?? 80
      playMode = saved.playMode || 'sequence'
    }

    if (!currentPlaylistId || !playlists.find(p => p.id === currentPlaylistId)) {
      currentPlaylistId = playlists.length > 0 ? playlists[0].id : null
    }

    const api = context.api

    async function saveState() {
      const localPlaylists = playlists.filter(p => p.source === 'local')
      const localTrackIds = new Set(localPlaylists.flatMap(p => p.trackIds))
      const localTracks: Record<string, Track> = {}
      for (const id of localTrackIds) {
        if (tracks[id]) localTracks[id] = tracks[id]
      }
      await context.storage?.set('playerData', {
        playlists: localPlaylists,
        tracks: localTracks,
        currentPlaylistId,
        volume,
        playMode,
      })
    }

    async function loadCloudPlaylists() {
      try {
        const res = await api.get('/music/playlists')
        const cloudList = res?.playlists || []
        playlists = playlists.filter(p => p.source !== 'cloud')
        for (const cpl of cloudList) {
          playlists.push({
            id: `cloud_${cpl.id}`,
            name: cpl.name,
            source: 'cloud',
            serverId: cpl.id,
            trackIds: [],
          })
        }
      } catch (e) {
        console.error('[player] loadCloudPlaylists error:', e)
      }
    }

    async function loadCloudSongs(playlistId: string) {
      const pl = playlists.find(p => p.id === playlistId && p.source === 'cloud')
      if (!pl || !pl.serverId) return
      try {
        const res = await api.get(`/music/playlists/${pl.serverId}/songs`)
        const songs = res?.songs || []
        pl.trackIds = []
        for (const s of songs) {
          const tid = `cloud_file_${s.file_id}`
          tracks[tid] = {
            id: tid, name: s.name, source: 'cloud', path: '',
            fileId: s.file_id, itemId: s.item_id, size: s.size, mime: s.mime,
          }
          pl.trackIds.push(tid)
        }
      } catch (e) {
        console.error('[player] loadCloudSongs error:', e)
      }
    }

    await loadCloudPlaylists()

    context.registerCommand('getPanelData', async () => {
      await loadCloudPlaylists()
      const st = getState()
      return {
        title: '音乐播放器',
        subtitle: st.currentTrack?.name || '未播放',
        items: [
          ...(st.currentTrack ? [{ title: st.currentTrack.name, subtitle: st.currentTrack.artist || '', action: 'play' }] : []),
          ...(st.playlists?.slice(0, 3).map((p: any) => ({ title: p.name, action: 'selectPlaylist', actionArgs: { playlistId: p.id } })) || []),
        ],
        buttons: [
          ...(st.isPlaying ? [{ label: '暂停', command: 'pause' }] : [{ label: '播放', command: 'play' }]),
          { label: '下一首', command: 'next' },
        ],
      }
    })
    context.registerCommand('getPageData', async () => {
      await loadCloudPlaylists()
      return getState()
    })

    context.registerCommand('open', async () => { context.openPage('player') })
    context.registerCommand('search', async (args: any) => { context.openPage('player') })

    context.registerCommand('createPlaylist', async (args: any) => {
      const name = args?.name || '新建歌单'
      const source: 'local' | 'cloud' = args?.source === 'cloud' ? 'cloud' : 'local'
      if (source === 'cloud') {
        try {
          const res = await api.post('/music/playlists', { name })
          playlists.push({ id: `cloud_${res.id}`, name: res.name, source: 'cloud', serverId: res.id, trackIds: [] })
        } catch (e) { console.error('[player] createPlaylist cloud error:', e) }
      } else {
        playlists.push({ id: generateId(), name, source: 'local', trackIds: [] })
        await saveState()
      }
      return getState()
    })

    context.registerCommand('deletePlaylist', async (args: any) => {
      const pl = playlists.find(p => p.id === args?.playlistId)
      if (!pl) return getState()
      if (pl.source === 'cloud' && pl.serverId) {
        try { await api.delete(`/music/playlists/${pl.serverId}`) }
        catch (e) { console.error(e); return getState() }
      }
      playlists = playlists.filter(p => p.id !== pl.id)
      if (currentPlaylistId === pl.id) currentPlaylistId = playlists.length > 0 ? playlists[0].id : null
      if (pl.source === 'local') await saveState()
      return getState()
    })

    context.registerCommand('renamePlaylist', async (args: any) => {
      const pl = playlists.find(p => p.id === args?.playlistId)
      if (!pl) return getState()
      if (pl.source === 'cloud' && pl.serverId) {
        try { await api.put(`/music/playlists/${pl.serverId}`, { name: args?.name || '' }); pl.name = args?.name || '' }
        catch (e) { console.error(e); return getState() }
      } else {
        pl.name = args?.name || ''
        await saveState()
      }
      return getState()
    })

    context.registerCommand('selectPlaylist', async (args: any) => {
      currentPlaylistId = args?.playlistId || null
      const pl = playlists.find(p => p.id === currentPlaylistId)
      if (pl?.source === 'cloud') {
        await loadCloudSongs(pl.id)
      }
      if (pl?.source === 'local') await saveState()
      return getState()
    })

    context.registerCommand('addTrack', async (args: any) => {
      const { playlistId, name, path, source = 'local', artist, fileId } = args
      const pl = playlists.find(p => p.id === playlistId)
      if (!pl) return getState()
      if (pl.source === 'cloud' && pl.serverId) {
        try { await api.post(`/music/playlists/${pl.serverId}/songs`, { file_id: fileId }) }
        catch (e) { console.error(e); return getState() }
      } else {
        const track: Track = {
          id: generateId(),
          name: name || path.split(/[/\\]/).pop() || '未知',
          source, path, artist,
        }
        tracks[track.id] = track
        pl.trackIds.push(track.id)
        await saveState()
      }
      return getState()
    })

    context.registerCommand('removeTrack', async (args: any) => {
      const { playlistId, trackId } = args
      const pl = playlists.find(p => p.id === playlistId)
      const track = tracks[trackId]
      if (pl?.source === 'cloud' && pl.serverId && track?.itemId) {
        try { await api.delete(`/music/playlists/${pl.serverId}/songs/${track.itemId}`) }
        catch (e) { console.error(e); return getState() }
        pl.trackIds = pl.trackIds.filter(id => id !== trackId)
      } else if (pl) {
        pl.trackIds = pl.trackIds.filter(id => id !== trackId)
        await saveState()
      }
      if (currentTrackId === trackId) {
        isPlaying = false; currentTrackId = null; currentTime = 0; duration = 0
      }
      return getState()
    })

    context.registerCommand('moveTrack', async (args: any) => {
      const { playlistId, trackId, direction } = args
      const pl = playlists.find(p => p.id === playlistId)
      if (!pl) return getState()
      const track = tracks[trackId]
      if (pl.source === 'cloud' && pl.serverId && track?.itemId) {
        try { await api.put(`/music/playlists/${pl.serverId}/reorder`, { item_id: track.itemId, direction }) } catch (e) { console.error(e) }
        await loadCloudSongs(pl.id)
      } else {
        const index = pl.trackIds.indexOf(trackId)
        const newIndex = direction === 'up' ? index - 1 : index + 1
        if (index > -1 && newIndex >= 0 && newIndex < pl.trackIds.length) {
          ;[pl.trackIds[index], pl.trackIds[newIndex]] = [pl.trackIds[newIndex], pl.trackIds[index]]
        }
        await saveState()
      }
      return getState()
    })

    context.registerCommand('clearPlaylist', async (args: any) => {
      const pl = playlists.find(p => p.id === args?.playlistId)
      if (!pl) return getState()
      if (pl.source === 'cloud' && pl.serverId) {
        let allOk = true
        for (const tid of [...pl.trackIds]) {
          const t = tracks[tid]
          if (t?.itemId) {
            try { await api.delete(`/music/playlists/${pl.serverId}/songs/${t.itemId}`) }
            catch (e) { console.error(e); allOk = false }
          }
        }
        if (allOk) pl.trackIds = []
        else await loadCloudSongs(pl.id)
      } else {
        pl.trackIds = []
        await saveState()
      }
      if (currentPlaylistId === pl.id) {
        currentTrackId = null; isPlaying = false; currentTime = 0; duration = 0
      }
      return getState()
    })

    context.registerCommand('importDirectory', async (args: any) => {
      const playlistId = args?.playlistId || currentPlaylistId
      const pl = playlists.find(p => p.id === playlistId && p.source === 'local')
      if (!pl) return getState()
      const dirPath = await context.files?.openDirectory?.()
      if (!dirPath) return getState()
      const audioFiles: { name: string; path: string }[] = await context.files?.listAudio?.(dirPath) || []
      for (const file of audioFiles) {
        const track: Track = { id: generateId(), name: file.name, source: 'local', path: file.path }
        tracks[track.id] = track
        pl.trackIds.push(track.id)
      }
      await saveState()
      return getState()
    })

    context.registerCommand('play', async (args: any) => {
      if (args?.trackId) {
        currentTrackId = args.trackId
        isPlaying = true; currentTime = 0
        if (!currentPlaylistId) {
          const pl = playlists.find(p => p.trackIds.includes(currentTrackId!))
          if (pl) currentPlaylistId = pl.id
        }
      } else if (args?.playlistId) {
        currentPlaylistId = args.playlistId
        const pl = playlists.find(p => p.id === currentPlaylistId)
        if (pl && pl.trackIds.length > 0) { currentTrackId = pl.trackIds[0]; isPlaying = true; currentTime = 0 }
      } else if (currentTrackId) {
        isPlaying = true
      } else if (currentPlaylistId) {
        const pl = playlists.find(p => p.id === currentPlaylistId)
        if (pl && pl.trackIds.length > 0) { currentTrackId = pl.trackIds[0]; isPlaying = true; currentTime = 0 }
      }
      return getState()
    })

    context.registerCommand('pause', async () => { isPlaying = false; return getState() })
    context.registerCommand('stop', async () => {
      isPlaying = false; currentTrackId = null; currentTime = 0; duration = 0
      return getState()
    })

    context.registerCommand('next', async () => {
      const pl = playlists.find(p => p.id === currentPlaylistId)
      if (!pl || pl.trackIds.length === 0) return getState()
      const idx = pl.trackIds.indexOf(currentTrackId || '')
      let n: number
      if (playMode === 'shuffle') n = Math.floor(Math.random() * pl.trackIds.length)
      else if (playMode === 'loop') n = idx
      else n = (idx + 1) % pl.trackIds.length
      currentTrackId = pl.trackIds[n]; currentTime = 0; isPlaying = true
      return getState()
    })

    context.registerCommand('prev', async () => {
      const pl = playlists.find(p => p.id === currentPlaylistId)
      if (!pl || pl.trackIds.length === 0) return getState()
      const idx = pl.trackIds.indexOf(currentTrackId || '')
      let n: number
      if (playMode === 'shuffle') n = Math.floor(Math.random() * pl.trackIds.length)
      else if (playMode === 'loop') n = idx
      else n = idx <= 0 ? pl.trackIds.length - 1 : idx - 1
      currentTrackId = pl.trackIds[n]; currentTime = 0; isPlaying = true
      return getState()
    })

    context.registerCommand('seek', async (args: any) => {
      if (args?.time !== undefined) currentTime = Math.max(0, Math.min(duration, args.time))
      else if (args?.percent !== undefined) currentTime = Math.max(0, Math.min(duration, duration * args.percent))
      return getState()
    })
    context.registerCommand('setVolume', async (args: any) => {
      if (args?.volume !== undefined) { volume = Math.max(0, Math.min(100, args.volume)); await saveState() }
      return getState()
    })
    context.registerCommand('toggleMode', async () => {
      const modes: ('sequence' | 'loop' | 'shuffle')[] = ['sequence', 'loop', 'shuffle']
      playMode = modes[(modes.indexOf(playMode) + 1) % modes.length]
      await saveState()
      return getState()
    })
    context.registerCommand('onTrackEnded', async () => {
      const pl = playlists.find(p => p.id === currentPlaylistId)
      if (!pl || pl.trackIds.length === 0) { isPlaying = false; return getState() }
      const idx = pl.trackIds.indexOf(currentTrackId || '')
      let n: number
      if (playMode === 'shuffle') n = Math.floor(Math.random() * pl.trackIds.length)
      else if (playMode === 'loop') n = idx
      else {
        n = idx + 1
        if (n >= pl.trackIds.length) { isPlaying = false; currentTrackId = null; return getState() }
      }
      currentTrackId = pl.trackIds[n]; currentTime = 0; isPlaying = true
      return getState()
    })
    context.registerCommand('updateProgress', async (args: any) => {
      if (args?.currentTime !== undefined) currentTime = args.currentTime
      if (args?.duration !== undefined) duration = args.duration
      return getState()
    })

    context.registerCommand('reloadCloudPlaylists', async () => {
      await loadCloudPlaylists()
      return getState()
    })
    context.registerCommand('cloudListAudioFiles', async () => {
      try {
        const res = await api.get('/files?page_size=200')
        const files = res?.files || []
        const audioExts = ['mp3', 'wav', 'flac', 'ogg', 'm4a', 'aac', 'wma']
        return files.filter((f: any) => !f.is_folder && (
          f.mime_type?.startsWith('audio/') ||
          audioExts.includes(f.original_name?.split('.').pop()?.toLowerCase())
        )).map((f: any) => ({ file_id: f.id, name: f.original_name, size: f.size }))
      } catch { return [] }
    })
    context.registerCommand('getCloudStreamBaseUrl', async () => getServerConfig())

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
                subtitle: `${pl.name} - ${t.source === 'cloud' ? '云端' : (t.source === 'url' ? '在线' : '本地')}`,
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

  deactivate() {
    if (pluginCtx?.storage) {
      const localPlaylists = playlists.filter(p => p.source === 'local')
      const localTrackIds = new Set(localPlaylists.flatMap(p => p.trackIds))
      const localTracks: Record<string, Track> = {}
      for (const id of localTrackIds) { if (tracks[id]) localTracks[id] = tracks[id] }
      pluginCtx.storage.set('playerData', { playlists: localPlaylists, tracks: localTracks, currentPlaylistId, volume, playMode })
    }
  }
}
