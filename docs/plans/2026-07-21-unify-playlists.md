# 统一本地与云端歌单逻辑 - 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把桌面播放器的"本地歌单"和"云端歌单"合并为一套数据结构与代码路径，仅播放时区分本地路径与云端流地址；后端补齐 rename/reorder 端点。

**Architecture:** `index.ts` 中所有歌单（无论来源）进入同一个 `playlists[]` 和 `tracks{}`，用 `source` 字段区分；操作命令按 `source` 分发到本地 storage 或服务器 API。`Page.vue` 删除全部 `cloudXxx` 独立分支和 `__cloud__` hack，侧边栏按来源分组但用同一组件。后端 `plugins/music` 新增 PUT rename 和 PUT reorder 两个端点。

**Tech Stack:** 后端 FastAPI + SQLAlchemy async + Pydantic v2；前端 Vue 3 + TypeScript + Vite（插件式构建，`vite build` 产出 `dist/index.js`）。无测试框架，验证方式：后端 curl，前端 `vipe build` + 手动。

**参考设计:** `docs/plans/2026-07-21-unify-playlists-design.md`

---

## Task 1: 后端 - 新增 rename 与 reorder 端点

**Files:**
- Modify: `backend/plugins/music/backend/schemas.py`
- Modify: `backend/plugins/music/backend/service.py`
- Modify: `backend/plugins/music/backend/router.py`

### Step 1: schemas.py 增加两个请求体

在 `backend/plugins/music/backend/schemas.py` 末尾追加：

```python
class PlaylistRenameRequest(BaseModel):
    name: str


class PlaylistReorderRequest(BaseModel):
    item_id: int
    direction: str  # 'up' | 'down'
```

并在文件顶部 router.py 的 import 中追加这两个类名（Step 3 处理）。

### Step 2: service.py 增加 rename 和 reorder 函数

在 `backend/plugins/music/backend/service.py` 末尾追加：

```python
async def rename_playlist(db: AsyncSession, user_id: int, playlist_id: int, name: str) -> bool:
    result = await db.execute(select(Playlist).where(Playlist.id == playlist_id, Playlist.user_id == user_id))
    pl = result.scalar_one_or_none()
    if not pl:
        return False
    pl.name = name
    await db.flush()
    return True


async def reorder_playlist_song(db: AsyncSession, user_id: int, playlist_id: int, item_id: int, direction: str) -> list[tuple[PlaylistItem, File]]:
    # 校验歌单归属
    pl_result = await db.execute(select(Playlist).where(Playlist.id == playlist_id, Playlist.user_id == user_id))
    if not pl_result.scalar_one_or_none():
        return []
    # 取出该歌单所有 item 按 position 排序
    items_result = await db.execute(
        select(PlaylistItem).where(PlaylistItem.playlist_id == playlist_id).order_by(PlaylistItem.position)
    )
    items = list(items_result.scalars().all())
    idx = next((i for i, it in enumerate(items) if it.id == item_id), -1)
    if idx < 0:
        return []
    swap = idx - 1 if direction == 'up' else idx + 1
    if swap < 0 or swap >= len(items):
        return []
    items[idx].position, items[swap].position = items[swap].position, items[idx].position
    await db.flush()
    # 返回新顺序
    return await list_playlist_songs(db, user_id, playlist_id)
```

### Step 3: router.py 增加两个端点

修改 `backend/plugins/music/backend/router.py` 顶部 import，把新增 schema 加进来：

```python
from plugins.music.backend.schemas import (
    PlaylistCreateRequest, PlaylistAddSongRequest,
    PlaylistResponse, PlaylistListResponse,
    PlaylistRenameRequest, PlaylistReorderRequest,
)
```

在文件末尾（`remove_song_from_playlist` 路由之后）追加：

```python
@router.put("/playlists/{playlist_id}")
async def rename_playlist(
    playlist_id: int,
    req: PlaylistRenameRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await music_service.rename_playlist(db, user["id"], playlist_id, req.name)
    if not ok:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return {"message": "Renamed"}


@router.put("/playlists/{playlist_id}/reorder")
async def reorder_playlist_song(
    playlist_id: int,
    req: PlaylistReorderRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await music_service.reorder_playlist_song(db, user["id"], playlist_id, req.item_id, req.direction)
    if rows == []:
        raise HTTPException(status_code=404, detail="Playlist or item not found")
    return {"songs": [{"item_id": item.id, "file_id": f.id, "name": f.original_name, "size": f.size, "mime": f.mime_type}
                      for item, f in rows]}
```

### Step 4: 重启后端并 curl 验证

Run（在 `backend/` 目录）：
```bash
# 假设后端已在跑，重启它；然后：
# 1. 登录拿 token
curl -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"admin"}'
# 2. 列出歌单拿 id
curl http://localhost:8000/api/music/playlists -H "Authorization: Bearer <TOKEN>"
# 3. 测 rename
curl -X PUT http://localhost:8000/api/music/playlists/<ID> -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" -d '{"name":"重命名测试"}'
# 4. 测 reorder（需要先有歌曲，拿 item_id）
curl -X PUT http://localhost:8000/api/music/playlists/<ID>/reorder -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" -d '{"item_id":<ITEM_ID>,"direction":"down"}'
```
Expected: rename 返回 `{"message":"Renamed"}`；reorder 返回 `{"songs":[...]}` 顺序已变。

### Step 5: 提交

```bash
git add backend/plugins/music/backend/schemas.py backend/plugins/music/backend/service.py backend/plugins/music/backend/router.py
git commit -m "feat(music): 新增歌单 rename 和 reorder 端点"
```

---

## Task 2: 前端 index.ts - 统一数据模型与命令分发

**Files:**
- Modify: `desktop/plugins/player/src/index.ts` (整文件重写核心部分)

### Step 1: 更新接口定义（文件顶部）

把现有 `Track`/`PlaylistInfo`/`PlayerStorage` 替换为：

```ts
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
```

### Step 2: 加模块级 cloud helper（替换原 `cloudGetStreamUrl` 命令实现）

在 `let pluginCtx` 声明附近加入：

```ts
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

function cloudStreamUrl(fileId: number): string {
  const { serverUrl, token } = getServerConfig()
  return `${serverUrl}/api/files/${fileId}/stream?token=${token}`
}
```

### Step 3: 改写 `activate` 内的加载逻辑（合并云端歌单）

替换原 `activate` 开头读 storage 的部分。在读完本地后追加云端加载：

```ts
async function activate(context: any) {
  pluginCtx = context
  const saved = await context.storage?.get<PlayerStorage>('playerData')
  if (saved) {
    // 仅恢复本地歌单，过滤掉历史残留的 __cloud__
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
    // 只持久化本地
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
      // 移除旧的云端项，按 serverId 同步
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
  // ...其余 registerCommand 见 Step 4
```

### Step 4: 重写所有命令为 source 分发

把原本地命令 + 原 `cloudXxx` 命令合并为下列一套（替换 `activate` 中所有 `context.registerCommand(...)` 块，搜索/panel/page 命令保留）：

```ts
  context.registerCommand('getPanelData', async () => getState())
  context.registerCommand('getPageData', async () => getState())

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
      try { await api.delete(`/music/playlists/${pl.serverId}`) } catch (e) { console.error(e) }
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
      try { await api.put(`/music/playlists/${pl.serverId}`, { name: args.name }) } catch (e) { console.error(e) }
    } else {
      pl.name = args.name
      await saveState()
    }
    return getState()
  })

  context.registerCommand('selectPlaylist', async (args: any) => {
    currentPlaylistId = args?.playlistId || null
    const pl = playlists.find(p => p.id === currentPlaylistId)
    if (pl?.source === 'cloud' && pl.trackIds.length === 0) {
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
      try {
        await api.post(`/music/playlists/${pl.serverId}/songs`, { file_id: fileId })
        await loadCloudSongs(pl.id)   // 重新拉以拿到 item_id
      } catch (e) { console.error(e) }
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
      try { await api.delete(`/music/playlists/${pl.serverId}/songs/${track.itemId}`) } catch (e) { console.error(e) }
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
      // 循环 delete
      for (const tid of [...pl.trackIds]) {
        const t = tracks[tid]
        if (t?.itemId) {
          try { await api.delete(`/music/playlists/${pl.serverId}/songs/${t.itemId}`) } catch (e) { console.error(e) }
        }
      }
      pl.trackIds = []
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
    // 仅本地
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

  // 播放控制（无云端分支，URL 在 Page.vue 用 getAudioUrl 解析）
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

  // next / prev / onTrackEnded 完全沿用原实现（不依赖 source）
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

  // 暴露给 Page.vue 的辅助命令
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
  context.registerCommand('refreshCloudPlaylists', async () => { await loadCloudPlaylists(); return getState() })
  context.registerCommand('getCloudStreamBaseUrl', async () => getServerConfig())
```

**删除**：原 `playTrack`、`addTrackById`（如未在他处引用）、所有 `cloudCreatePlaylist`/`cloudDeletePlaylist`/`cloudListPlaylists`/`cloudListSongs`/`cloudAddSong`/`cloudRemoveSong`/`cloudGetStreamUrl` 命令（逻辑已合并）。若 `addTrackById` 在 Page.vue 未用，一并删。

### Step 5: getState 保持返回新结构

`getState()` 不需改动（已读 `playlists`/`tracks` 全局变量），但确认 `currentPlaylistTracks` 计算无误即可。

### Step 6: 构建验证

Run（在 `desktop/plugins/player/`）：
```bash
npm run build
```
Expected: `dist/index.js` 生成，无 TS 报错。

### Step 7: 提交

```bash
git add desktop/plugins/player/src/index.ts
git commit -m "refactor(player): 统一本地与云端歌单数据模型与命令分发"
```

---

## Task 3: 前端 Page.vue - 统一 UI，删除云端独立分支

**Files:**
- Modify: `desktop/plugins/player/src/Page.vue`

### Step 1: 更新 Track 接口与 getAudioUrl

`<script setup>` 顶部 `Track` 接口替换为：

```ts
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
```

`PlaylistInfo` 接口加字段：

```ts
interface PlaylistInfo {
  id: string
  name: string
  source: 'local' | 'cloud'
  serverId?: number
  trackIds: string[]
}
```

替换 `getAudioUrl`（处理 cloud）：

```ts
function getAudioUrl(track: Track | null): string {
  if (!track) return ''
  if (track.source === 'cloud' && track.fileId) {
    const cfg = (props as any).data // 占位，实际用下面 helper
    return ''
  }
  if (track.source === 'url') return track.path
  return `local-file:///${track.path.replace(/\\/g, '/')}`
}
```

实际 cloud URL 需要从命令拿配置。改为 async + 调 `execute('getCloudStreamBaseUrl')` 一次缓存。最简方案：

```ts
const serverConfig = ref<{ serverUrl: string; token: string }>({ serverUrl: '', token: '' })
onMounted(async () => {
  const cfg = await props.execute('getCloudStreamBaseUrl')
  if (cfg) serverConfig.value = cfg as any
  // ...其余 mount 逻辑
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
```

### Step 2: 删除云端专用 ref，改为统一 computed

**删除**：`cloudPlaylists`、`selectedCloudId`、`cloudSongs`、`selectedCloudName`、`showCloudNew`/`cloudNewName`（改用统一新建弹窗）、`showCloudAddSong`/`cloudAudioList`/`cloudAddLoading`/`cloudSelectedIds`（保留弹窗状态但不再绑定到"当前云端歌单"，改为按 activePlaylist.source 决定）。

**保留新建歌单弹窗状态**（统一）：

```ts
const showNewPlaylist = ref(false)
const newPlaylistSource = ref<'local' | 'cloud'>('local')
const newPlaylistName = ref('')
```

**保留添加歌曲弹窗**（按 activePlaylist.source 区分内容）：

```ts
const showAddTrackModal = ref(false)
// local 分支：现有 addTrackSource/addTrackPath/addTrackName/addTrackArtist
// cloud 分支：cloudAudioList/cloudAddLoading/cloudSelectedIds
const cloudAudioList = ref<any[]>([])
const cloudAddLoading = ref(false)
const cloudSelectedIds = ref<Set<number>>(new Set())
```

**统一 computed**（替代原 activePlaylist + cloud 分支）：

```ts
const activePlaylist = computed(() => {
  return props.data.playlists.find(p => p.id === selectedPlaylistId.value) || null
})
const activeTracks = computed(() => {
  if (!activePlaylist.value) return []
  return activePlaylist.value.trackIds.map(id => props.data.tracks[id]).filter(Boolean)
})
```

`selectedPlaylistId` 初始化时优先取 `props.data.currentPlaylistId`（沿用原逻辑）。

### Step 3: 重写操作函数为统一分发

```ts
function selectPlaylist(id: string) {
  selectedPlaylistId.value = id
  props.execute('selectPlaylist', { playlistId: id })
}

async function confirmNewPlaylist() {
  const name = newPlaylistName.value.trim()
  if (!name) { showNewPlaylist.value = false; return }
  await props.execute('createPlaylist', { name, source: newPlaylistSource.value })
  if (newPlaylistSource.value === 'cloud') await props.execute('refreshCloudPlaylists')
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
    if (props.data.playlists.find(p => p.id === renamingPlaylistId.value)?.source === 'cloud') {
      await props.execute('refreshCloudPlaylists')
    }
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
async function clearPlaylist() {
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
```

**删除**：`playCloudSong`、`removeCloudSong`、`confirmCloudAdd`、`loadCloudPlaylists`、`createCloudPlaylist`、`confirmCloudNew`、`deleteCloudPlaylist`、`selectCloudPlaylist`、`openCloudAddSong`。

### Step 4: onMounted 简化

```ts
onMounted(async () => {
  const cfg = await props.execute('getCloudStreamBaseUrl')
  if (cfg) serverConfig.value = cfg as any
  if (audioRef.value) audioRef.value.volume = props.data.volume / 100
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
```

删除原来的 `onMounted(loadCloudPlaylists)`。

### Step 5: 重写模板 - 侧边栏按来源分组（同一组件）

替换整个 `<div class="sidebar">` 块为：

```html
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
    <!-- 本地歌单分组 -->
    <div class="group-label">本地歌单</div>
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

    <!-- 云端歌单分组 -->
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
```

加 `.group-label` 样式：

```css
.group-label { font-size: 11px; font-weight: 600; color: #adb5bd; text-transform: uppercase; letter-spacing: 0.5px; padding: 8px 10px 4px; }
```

### Step 6: 重写模板 - 统一曲目区

替换整个 `<div class="track-area">` 块（删除 `v-if="!selectedCloudId"` / `v-else` 两分支）为单一列表：

```html
<div class="track-area">
  <div class="track-header">
    <div>
      <h2 class="track-title">{{ activePlaylist?.name || '选择歌单' }}</h2>
      <span class="track-subtitle">{{ activeTracks.length }} 首歌曲 · {{ activePlaylist?.source === 'cloud' ? '云端' : '本地' }}</span>
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
      <button class="btn btn-ghost" @click="clearPlaylist">清空</button>
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
```

### Step 7: 重写模板 - 新建歌单弹窗 + 添加歌曲弹窗

新建歌单弹窗（替换原内联 input 和 cloud new）：

```html
<div v-if="showNewPlaylist" class="modal-overlay" @click.self="showNewPlaylist = false">
  <div class="modal-content" style="max-width:360px;">
    <h3 class="modal-title">新建歌单</h3>
    <div class="modal-tabs">
      <button class="modal-tab" :class="{ active: newPlaylistSource === 'local' }" @click="newPlaylistSource = 'local'">本地</button>
      <button class="modal-tab" :class="{ active: newPlaylistSource === 'cloud' }" @click="newPlaylistSource = 'cloud'">云端</button>
    </div>
    <input v-model="newPlaylistName" class="input" placeholder="歌单名称" autofocus @keyup.enter="confirmNewPlaylist" />
    <div class="modal-actions">
      <button class="btn btn-ghost" @click="showNewPlaylist = false">取消</button>
      <button class="btn btn-pink" :disabled="!newPlaylistName.trim()" @click="confirmNewPlaylist">创建</button>
    </div>
  </div>
</div>
```

添加歌曲弹窗：根据 `activePlaylist.source` 显示不同内容（local=原 modal，cloud=原 cloud modal）。把两个原弹窗合并到一个 `v-if="showAddTrackModal"`，内部用 `activePlaylist?.source` 切换。具体：保留原 `<div v-if="showAddTrackModal">` 结构但用 `v-if="activePlaylist?.source === 'cloud'"` 切分内部内容。

### Step 8: 删除原内联新建 input、原 cloud sidebar、原 cloud new inline、原两个独立 modal

清理所有被新模板取代的旧 DOM。

### Step 9: 构建验证

Run（在 `desktop/plugins/player/`）：
```bash
npm run build
```
Expected: 无 TS/Vue 编译错误，`dist/index.js` 生成。

### Step 10: 提交

```bash
git add desktop/plugins/player/src/Page.vue
git commit -m "refactor(player): 统一歌单 UI，删除云端独立分支与 __cloud__ hack"
```

---

## Task 4: 集成验证

### Step 1: 重启桌面端

Run（在 `desktop/`）：
```bash
npm run dev
```

### Step 2: 手动验证清单

- [ ] 侧边栏显示"本地歌单""云端歌单"两个分组，云端歌单从服务器加载
- [ ] 点 + 弹窗可选本地/云端，创建后出现在对应分组
- [ ] 点云端歌单，曲目列表加载（loading 期间无报错）
- [ ] 点云端歌曲可播放，底栏显示"云端"，进度条/暂停/seek 正常
- [ ] 云端歌单内 next/prev 跨歌曲正常（无 `__cloud__` hack）
- [ ] 云端歌单可重命名（标题更新）
- [ ] 云端歌单歌曲可上移/下移（顺序变化持久化到服务器）
- [ ] 云端歌单可清空
- [ ] 本地歌单所有原功能不受影响（创建/重命名/添加本地/添加URL/导入文件夹/移动/清空/删除）
- [ ] 播放本地歌曲仍走 `local-file:///`
- [ ] 重启 app 后本地歌单持久化、云端歌单重新拉取
- [ ] 代码搜索：`__cloud__`、`selectedCloudId`、`playCloudSong`、`cloudCreatePlaylist` 等已不存在

### Step 3: 移动端回归

`mobile/lib/screens/music_screen.dart` 未改动，确认 `flutter run` 仍能列云端歌单/播放（接口向下兼容）。

### Step 4: 提交（如有修复）

```bash
git add -A
git commit -m "fix(player): 集成验证修复"
```

---

## 完成标志

1. 后端 PUT rename / PUT reorder 端点存在并工作
2. `desktop/plugins/player/src/index.ts` 无 `cloudXxx` 命令、无 `__cloud__`
3. `desktop/plugins/player/src/Page.vue` 无 `selectedCloudId`、`cloudSongs`、`playCloudSong` 等独立分支
4. 云端歌单的所有操作与本地完全一致（创建/删除/重命名/添加/移除/移动/清空）
5. 仅播放 URL 解析区分 local/url/cloud 三种 source
6. 移动端不受影响
