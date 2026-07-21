# 统一本地与云端歌单逻辑 - 设计文档

日期: 2026-07-21
状态: 已确认

## 背景

当前桌面播放器 (`desktop/plugins/player/src/`) 把"本地歌单"和"云端歌单"实现成两套独立系统：

- `index.ts` 同时存在 `createPlaylist`/`addTrack`/... 与 `cloudCreatePlaylist`/`cloudAddSong`/... 两套命令
- `Page.vue` 存在两个独立侧边栏（"歌单" + "云端歌单"）、两套曲目列表
- 云端播放靠一个隐藏的 `__cloud__` 本地歌单 hack：把云端歌曲复制成 URL track 灌进本地状态，next/prev 才能工作

用户诉求："在线歌单也是歌单，逻辑和本地歌单一样，请不要分开实现。应该逻辑一致，只有播放时一个取本地地址，一个取云端流，track 的逻辑不一致，其他应该完全一致。"

## 目标

- 一套数据结构、一套代码路径承载本地+云端歌单
- 彻底删除 `__cloud__` hack 及所有 `cloudXxx` 命令
- UI 用统一组件，仅以分组标题区分来源
- 后端补齐 rename / reorder 端点，使云端能力与本地"完全一致"

## 非目标

- 不改变本地歌单的 storage 持久化方式
- 不改变云端歌单的服务器存储结构（仍用现有 `playlists` / `playlist_items` 表）

## 数据模型（统一）

`desktop/plugins/player/src/index.ts`:

```ts
interface PlaylistInfo {
  id: string              // 本地: uuid; 云端: 'cloud_<serverId>'
  name: string
  source: 'local' | 'cloud'
  serverId?: number       // 云端歌单的服务器 ID
  trackIds: string[]
}

interface Track {
  id: string              // 本地: uuid; 云端: 'cloud_file_<fileId>'
  name: string
  source: 'local' | 'url' | 'cloud'
  path: string            // source=local|url 用
  fileId?: number         // source=cloud 用
  artist?: string
  size?: number
  mime?: string
}
```

## 加载流程

1. `activate` 时从 storage 读本地歌单 → 调 `GET /music/playlists` 读云端歌单 → 统一注入同一个 `playlists[]`（云端项标 `source:'cloud'` + `serverId`，`trackIds` 暂为空）
2. 选中云端歌单时：调 `GET /music/playlists/{id}/songs` → 把每首歌注入 `tracks{}`（id=`cloud_file_<fileId>`, source='cloud', fileId）→ 填充该歌单的 `trackIds`
3. `saveState()` 仅持久化 `source==='local'` 的 playlist 和被本地引用的 track；云端数据每次现拉不缓存到 storage

## 操作分发（UI 只调一套命令）

| 命令 | source=local | source=cloud |
|---|---|---|
| `createPlaylist({name, source})` | push 本地数组 | POST `/music/playlists` → push 云端项 |
| `deletePlaylist({playlistId})` | filter 本地数组 | DELETE `/music/playlists/{serverId}` → filter |
| `renamePlaylist({playlistId, name})` | 改本地数组 | PUT `/music/playlists/{serverId}` |
| `selectPlaylist({playlistId})` | 设当前 | 设当前；若 trackIds 空则触发懒加载 |
| `addTrack({playlistId, ...})` | 加 tracks map + push trackIds | POST `/music/playlists/{serverId}/songs` → 加 map + push |
| `removeTrack({playlistId, trackId})` | filter trackIds | DELETE `/music/playlists/{serverId}/songs/{itemId}` → filter |
| `moveTrack({playlistId, trackId, direction})` | 本地交换 | PUT `/music/playlists/{serverId}/reorder` |
| `clearPlaylist({playlistId})` | 清空 trackIds | 循环 DELETE 所有 items |
| `importDirectory({playlistId})` | 本地（仅 local 可用） | 不适用，UI 对云端隐藏此按钮 |

云端 track 的 `itemId`（playlist_item 主键）需保留以支持 remove/reorder。Track 接口扩展 `itemId?: number`。

## 播放（唯一真实差异）

`getAudioUrl(track)`：
- `local` → `local-file:///${track.path.replace(/\\/g,'/')}`
- `url` → `track.path`
- `cloud` → `${serverUrl}/api/files/${track.fileId}/stream?token=${token}`

`serverUrl`/`token` 沿用现有 `cloudGetStreamUrl` 的读取逻辑（从 `omniaide-config/config.json`），下沉为模块级 helper。next/prev/seek/底栏全部走统一路径，无云端分支。

## UI 改造 (`Page.vue`)

- **侧边栏**：保留"本地歌单""云端歌单"两个分组标题；同一组件渲染，选中/删除/重命名交互一致
- **新建**：点 + 弹小窗选"本地/云端"，再输入名称
- **曲目区**：一个 track list 组件。"添加"按钮按当前歌单 source 决定行为：
  - local → 现有"本地文件/在线音频"tab 弹窗
  - cloud → 现有"云端音频文件选择器"弹窗
- **删除项**：`__cloud__` 隐藏歌单逻辑、`playCloudSong` 中"复制全部歌曲到隐藏歌单"的循环、`selectedCloudId`/`cloudSongs` 等云端专用 ref（改为统一 `activeTracks` computed）
- **重命名/上移/下移/清空**：对云端歌单也显示（之前只本地有）

## 后端改动 (`backend/plugins/music/`)

### 1. PUT `/api/music/playlists/{playlist_id}` — 重命名
- schema: `PlaylistRenameRequest { name: str }`
- service: `rename_playlist(db, user_id, playlist_id, name) -> bool`
- 复用现有 `PlaylistResponse`

### 2. PUT `/api/music/playlists/{playlist_id}/reorder` — 调整顺序
- schema: `ReorderRequest { item_id: int, direction: 'up'|'down' }`（与前端 moveTrack 语义一致，最小改动）
- service: 交换相邻两个 `PlaylistItem.position` 并刷新
- 返回新的 songs 列表（复用 list_playlist_songs 的序列化）

### 3. DELETE 清空
- 不新增端点，前端循环调用现有 `DELETE /songs/{item_id}`

## 风险与回退

- **风险**：云端歌单懒加载导致首次打开曲目列表短暂为空 → UI 显示 loading
- **风险**：storage 中残留旧 `__cloud__` 歌单 → activate 时过滤 `name === '__cloud__'` 的本地歌单并清理
- **回退**：改动集中在 player 插件 + music 后端，不影响其他模块；如出问题可单独 revert

## 验收标准

1. 侧边栏点任一云端歌单，曲目列表正确显示，双击可播放，next/prev 跨云端歌曲正常
2. 云端歌单可重命名、可上下移动歌曲、可清空（与本地操作完全一致）
3. 新建歌单可选本地/云端
4. 代码中不再出现 `__cloud__`、`cloudPlaylists`、`selectedCloudId`、`playCloudSong` 等独立云端分支
5. `index.ts` 命令 `createPlaylist`/`deletePlaylist`/`renamePlaylist`/`addTrack`/`removeTrack`/`moveTrack`/`clearPlaylist` 对 local/cloud 均生效
6. 后端 PUT rename / PUT reorder 端点可用，移动端 (`mobile/`) 的 music_screen 无需改动（接口向下兼容）
