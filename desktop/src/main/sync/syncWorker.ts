import axios from 'axios'
import { join, relative, dirname } from 'path'
import { existsSync, readFileSync, statSync, mkdirSync, writeFileSync, readdirSync, unlinkSync, createReadStream } from 'fs'
import { getConfig } from '../config'
import { watch } from 'chokidar'

interface SyncPair {
  id: number
  server_path: string
  local_path: string
  enabled: boolean
}

let watchers: any[] = []
let syncPairs: SyncPair[] = []
let syncTimer: any = null
let isSyncing = false

// 持久化同步状态：记录每个文件最后一次同步时的 size
function statePath(localDir: string) {
  return join(localDir, '.omniaidesync')
}

function loadState(localDir: string): Record<string, number> {
  try {
    return JSON.parse(readFileSync(statePath(localDir), 'utf-8'))
  } catch { return {} }
}

function saveState(localDir: string, state: Record<string, number>) {
  writeFileSync(statePath(localDir), JSON.stringify(state, null, 2))
}

async function api() {
  const c = await getConfig()
  return { serverUrl: c.serverUrl || 'http://localhost:8000', token: c.token || '' }
}

async function loadPairs() {
  try {
    const { serverUrl, token } = await api()
    if (!token) { console.log('[sync] no token, skipping'); return }
    const res = await axios.get(`${serverUrl}/api/sync/folders`, {
      headers: { Authorization: 'Bearer ' + token }
    })
    syncPairs = (res.data?.folders || []).filter((f: any) => f.enabled)
    console.log('[sync] loaded pairs:', syncPairs.length)
  } catch (e: any) { console.log('[sync] loadPairs error:', e.message); syncPairs = [] }
}

function getPair(localPath: string) {
  return syncPairs.find(s => localPath.startsWith(s.local_path))
}

// ---- Upload: local → server ----
async function uploadFile(localPath: string) {
  const pair = getPair(localPath)
  if (!pair) return
  const st = statSync(localPath)
  if (!st.isFile()) return

  const relPath = relative(pair.local_path, localPath).replace(/\\/g, '/')
  const baseFolder = pair.server_path.replace(/\/+$/, '') + '/'
  const filename = relPath.split('/').pop() || relPath
  const parentPath = relPath.split('/').slice(0, -1).filter(Boolean).join('/')
  const uploadFolder = parentPath ? baseFolder + parentPath + '/' : baseFolder

  try {
    const { serverUrl, token } = await api()
    if (!token) return

    const uploadInfo = await axios.post(`${serverUrl}/api/files/upload-url`,
      { filename, mime_type: 'application/octet-stream', folder_path: uploadFolder },
      { headers: { Authorization: 'Bearer ' + token } }
    )
    const { upload_url, file_id } = uploadInfo.data

    if (upload_url) {
      const fileData = readFileSync(localPath)
      await axios.put(upload_url, fileData, { headers: { 'Content-Type': 'application/octet-stream' } })
    } else {
      const FormData = require('form-data')
      const form = new FormData()
      form.append('file', createReadStream(localPath), filename)
      await axios.post(`${serverUrl}/api/files/upload/direct?folder_path=${encodeURIComponent(uploadFolder)}`, form, {
        headers: { ...form.getHeaders(), Authorization: 'Bearer ' + token },
        maxContentLength: Infinity,
        maxBodyLength: Infinity,
      })
      console.log('[sync] uploaded (direct):', relPath)
      try {
        const state = loadState(pair.local_path)
        state[relPath] = st.size
        saveState(pair.local_path, state)
      } catch {}
      return
    }
    if (file_id) {
      await axios.post(`${serverUrl}/api/files/confirm`, { file_id },
        { headers: { Authorization: 'Bearer ' + token } }
      )
    }
    console.log('[sync] uploaded:', relPath)
  } catch (e: any) { console.log('[sync] upload error:', relPath, e.message) }

  // 更新持久化状态
  try {
    const state = loadState(pair.local_path)
    state[relPath] = st.size
    saveState(pair.local_path, state)
  } catch {}
}

// ---- Full sync ----
async function syncDown() {
  if (isSyncing) return
  isSyncing = true
  try {
    for (const pair of syncPairs) {
      await syncPair(pair)
    }
  } finally {
    isSyncing = false
  }
}

async function syncPair(pair: SyncPair) {
  try {
    const { serverUrl, token } = await api()
    if (!token) { console.log('[sync] syncDown: no token'); return }
    const folderPath = pair.server_path.replace(/\/+$/, '') + '/'
    const localDir = pair.local_path
    ensureDir(localDir)

    // 1. Fetch all server files, filter by folder prefix
    const res = await axios.get(`${serverUrl}/api/files?page_size=200`,
      { headers: { Authorization: 'Bearer ' + token } }
    )
    const allFiles = (res.data?.files || [])
    const serverFiles = allFiles.filter((f: any) =>
      !f.is_folder && f.size && f.folder_path?.startsWith(folderPath)
    )

    // Dedup by name, keep the one with largest size
    const serverMap: Record<string, any> = {}
    for (const f of serverFiles) {
      const key = f.original_name
      const existing = serverMap[key]
      if (existing && existing.size >= f.size) continue
      serverMap[key] = f
    }

    // 2. List local files
    const localFiles = listLocalFiles(localDir).filter(f => !f.endsWith('.omniaidesync'))
    const localSet = new Set(localFiles.map(f => relative(localDir, f).replace(/\\/g, '/')))

    // 3. Load persistent sync state
    const state = loadState(localDir)

    let dlCount = 0, ulCount = 0, delCount = 0

    // 4. Process server files
    for (const [relPath, sf] of Object.entries(serverMap)) {
      const localPath = join(localDir, relPath)
      if (existsSync(localPath)) {
        const localSize = statSync(localPath).size
        if (localSize === sf.size) {
          state[relPath] = localSize  // 已同步
          continue
        }
        // 大小不同 → 本地修改了，上传覆盖云端
        try {
          await uploadFile(localPath)
          state[relPath] = localSize
          ulCount++
        } catch (e: any) { console.log('[sync] ul error:', relPath, e.message) }
      } else {
        // 本地不存在 → 下载
        ensureDir(dirname(localPath))
        try {
          const fileRes = await axios.get(`${serverUrl}/api/files/${sf.id}/download`,
            { headers: { Authorization: 'Bearer ' + token }, responseType: 'arraybuffer' }
          )
          writeFileSync(localPath, Buffer.from(fileRes.data))
          state[relPath] = sf.size
          dlCount++
        } catch (e: any) { console.log('[sync] dl error:', relPath, e.message) }
      }
    }

    // 5. Process local files not on server
    for (const relPath of localSet) {
      if (serverMap[relPath]) continue
      const localPath = join(localDir, relPath)
      if (state[relPath] !== undefined) {
        // 之前同步过，云端删了 → 删除本地
        const localSize = statSync(localPath).size
        if (localSize === state[relPath]) {
          // 本地未修改 → 跟随云端删除
          try { unlinkSync(localPath); delete state[relPath]; delCount++ }
          catch (e: any) { console.log('[sync] del local error:', relPath, e.message) }
        } else {
          // 本地修改了 → 上传（本地方修改优先于云端删除）
          try { await uploadFile(localPath); state[relPath] = localSize; ulCount++ }
          catch (e: any) { console.log('[sync] ul error:', relPath, e.message) }
        }
      } else {
        // 从未同步过 → 新本地文件，上传
        try { await uploadFile(localPath); state[relPath] = statSync(localPath).size; ulCount++ }
        catch (e: any) { console.log('[sync] ul error:', relPath, e.message) }
      }
    }

    // 6. Remove stale state entries (文件在本地和云端都不存在)
    for (const relPath of Object.keys(state)) {
      if (!serverMap[relPath] && !localSet.has(relPath)) {
        // 云端删了，本地也删了 → 清理状态
        delete state[relPath]
        delCount++
      }
    }

    // 7. Save state
    saveState(localDir, state)

    if (dlCount || ulCount || delCount) {
      console.log(`[sync] ${pair.server_path}: ${dlCount} dl, ${ulCount} ul, ${delCount} clean`)
    } else {
      console.log(`[sync] ${pair.server_path}: up to date (${Object.keys(serverMap).length} server, ${localSet.size} local)`)
    }
  } catch (e: any) { console.log('[sync] syncPair error:', pair?.server_path, e.message) }
}

async function toTrash(serverUrl: string, token: string, fileId: number) {
  try {
    await axios.delete(`${serverUrl}/api/files/${fileId}`, { headers: { Authorization: 'Bearer ' + token } })
  } catch {}
}

function ensureDir(dir: string) {
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
}

function listLocalFiles(dir: string): string[] {
  const results: string[] = []
  try {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.name === '.omniaidesync') continue
      const fullPath = join(dir, entry.name)
      if (entry.isDirectory()) results.push(...listLocalFiles(fullPath))
      else results.push(fullPath)
    }
  } catch {}
  return results
}

// ---- Local watcher ----
function startWatcher(pair: SyncPair) {
  ensureDir(pair.local_path)
  console.log('[sync] watching:', pair.local_path)
  const w = watch(pair.local_path, { ignoreInitial: true, depth: 10 })
  w.on('add', (p) => {
    if (isSyncing || p.endsWith('.omniaidesync')) return
    uploadFile(p)
  })
  w.on('change', (p) => {
    if (isSyncing || p.endsWith('.omniaidesync')) return
    uploadFile(p)
  })
  w.on('unlink', (p) => {
    if (isSyncing || p.endsWith('.omniaidesync')) return
    console.log('[sync] local unlink:', p)
    deleteServerFile(pair, p)
  })
  watchers.push(w)
}

async function deleteServerFile(pair: SyncPair, localPath: string) {
  try {
    const { serverUrl, token } = await api()
    if (!token) return
    const relPath = relative(pair.local_path, localPath).replace(/\\/g, '/')
    const filename = relPath.split('/').pop() || relPath
    const parentPath = relPath.split('/').slice(0, -1).filter(Boolean).join('/')
    const folderPath = pair.server_path.replace(/\/+$/, '') + '/'
    const fileFolder = parentPath ? folderPath + parentPath + '/' : folderPath

    const res = await axios.get(`${serverUrl}/api/files?page_size=200`,
      { headers: { Authorization: 'Bearer ' + token } }
    )
    const files = (res.data?.files || []).filter((f: any) =>
      f.original_name === filename && f.folder_path === fileFolder && !f.is_folder && f.size
    )
    for (const f of files) {
      await toTrash(serverUrl, token, f.id)
    }
  } catch (e: any) { console.log('[sync] del server error:', e.message) }
}

function stopWatchers() {
  watchers.forEach(w => w.close())
  watchers = []
}

export async function startSync() {
  console.log('[sync] starting...')
  stopWatchers()
  if (syncTimer) clearInterval(syncTimer)
  await loadPairs()
  syncPairs.forEach(p => startWatcher(p))
  console.log('[sync] watchers started:', syncPairs.length)
  await syncDown()
  syncTimer = setInterval(async () => {
    await loadPairs()
    await syncDown()
  }, 30000)
  console.log('[sync] running (30s interval)')
}

export function stopSync() {
  stopWatchers()
  if (syncTimer) { clearInterval(syncTimer); syncTimer = null }
}
