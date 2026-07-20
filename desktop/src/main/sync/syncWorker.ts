import axios from 'axios'
import { join, relative } from 'path'
import { existsSync, readFileSync, statSync, mkdirSync, writeFileSync, readdirSync, unlinkSync, rmdirSync } from 'fs'
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
  const stat = statSync(localPath)
  if (!stat.isFile()) return

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
    if (!upload_url) { console.log('[sync] no upload_url'); return }

    const fileData = readFileSync(localPath)
    await axios.put(upload_url, fileData, { headers: { 'Content-Type': 'application/octet-stream' } })
    await axios.post(`${serverUrl}/api/files/confirm`, { file_id },
      { headers: { Authorization: 'Bearer ' + token } }
    )
    console.log('[sync] uploaded:', relPath)
  } catch (e: any) { console.log('[sync] upload error:', e.message) }
}

// ---- Download: server → local ----
async function syncDown() {
  for (const pair of syncPairs) {
    try {
      const { serverUrl, token } = await api()
      if (!token) { console.log('[sync] syncDown: no token'); continue }
      const folderPath = pair.server_path.replace(/\/+$/, '') + '/'
      const localDir = pair.local_path

      if (!existsSync(localDir)) { mkdirSync(localDir, { recursive: true }); console.log('[sync] created local:', localDir) }

      const res = await axios.get(`${serverUrl}/api/files?page_size=200&folder_path=${encodeURIComponent(folderPath)}`,
        { headers: { Authorization: 'Bearer ' + token } }
      )
      const serverFiles = (res.data?.files || []).filter((f: any) => !f.is_folder)

      const serverMap: Record<string, any> = {}
      for (const f of serverFiles) {
        serverMap[f.original_name] = f
      }

      const localFiles = listLocalFiles(localDir)
      const localMap: Record<string, boolean> = {}
      for (const lf of localFiles) {
        const relPath = relative(localDir, lf).replace(/\\/g, '/')
        localMap[relPath] = true
      }

      let dlCount = 0, delCount = 0
      for (const [relPath, sf] of Object.entries(serverMap)) {
        const localFilePath = join(localDir, relPath)
        if (existsSync(localFilePath)) {
          const localStat = statSync(localFilePath)
          if (localStat.size === sf.size) continue
        }
        try {
          const dlRes = await axios.get(`${serverUrl}/api/files/${sf.id}/download-url`,
            { headers: { Authorization: 'Bearer ' + token } }
          )
          const dlUrl = dlRes.data?.download_url
          if (!dlUrl) { console.log('[sync] no dl url for', relPath); continue }
          mkdirSync(join(localDir, relPath.split('/').slice(0, -1).join('/')), { recursive: true })
          const fileRes = await axios.get(dlUrl, { responseType: 'arraybuffer' })
          writeFileSync(localFilePath, Buffer.from(fileRes.data))
          dlCount++
        } catch (e: any) { console.log('[sync] dl error:', relPath, e.message) }
      }

      for (const [relPath] of Object.entries(localMap)) {
        if (!serverMap[relPath]) {
          const localFilePath = join(localDir, relPath)
          try { unlinkSync(localFilePath); delCount++ } catch (e: any) { console.log('[sync] del error:', relPath, e.message) }
        }
      }
      if (dlCount || delCount) console.log(`[sync] ${pair.server_path}: ${dlCount} dl, ${delCount} del`)
      else console.log(`[sync] ${pair.server_path}: up to date (${serverFiles.length} server, ${localFiles.length} local)`)
    } catch (e: any) { console.log('[sync] syncDown error:', pair?.server_path, e.message) }
  }
}

function listLocalFiles(dir: string): string[] {
  const results: string[] = []
  try {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const fullPath = join(dir, entry.name)
      if (entry.isDirectory()) results.push(...listLocalFiles(fullPath))
      else results.push(fullPath)
    }
  } catch {}
  return results
}

// ---- Local watcher ----
function startWatcher(pair: SyncPair) {
  if (!existsSync(pair.local_path)) mkdirSync(pair.local_path, { recursive: true })
  console.log('[sync] watching:', pair.local_path)
  const w = watch(pair.local_path, { ignoreInitial: true, depth: 10 })
  w.on('add', (p) => { console.log('[sync] local add:', p); uploadFile(p) })
  w.on('change', (p) => { console.log('[sync] local change:', p); uploadFile(p) })
  w.on('unlink', (p) => { console.log('[sync] local unlink:', p) })
  watchers.push(w)
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
