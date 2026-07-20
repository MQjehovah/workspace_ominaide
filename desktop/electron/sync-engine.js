const chokidar = require('chokidar')
const fs = require('fs')
const path = require('path')
const axios = require('axios')

class SyncEngine {
  constructor() {
    this.watcher = null
    this.ws = null
    this.config = null
    this.status = 'disconnected'
    this.pendingEvents = 0
    this.onStatusChange = null
    this.onEvent = null
    this.ignoreNextChange = false
    this._syncedPaths = new Set()  // tracks files that were synced in previous cycle
    this._prevServerPaths = new Set()
    this._prevLocalPaths = new Set()
  }

  async start(config) {
    this.config = config
    this.setStatus('syncing')
    this._startWatching()
    this._startPolling()
  }

  stop() {
    this._stopWatching()
    this._stopPolling()
    this.config = null
    this.setStatus('disconnected')
  }

  getStatus() {
    return {
      status: this.status,
      pendingEvents: this.pendingEvents,
      localPath: this.config?.localPath || ''
    }
  }

  _startPolling() {
    if (!this.config?.localPath || !this.config?.serverUrl) return
    this._pollOnce()
    this._pollTimer = setInterval(() => this._pollOnce(), 30000)
  }

  _stopPolling() {
    if (this._pollTimer) { clearInterval(this._pollTimer); this._pollTimer = null }
  }

  async _pollOnce() {
    try {
      const serverPrefix = (this.config.serverPath || '/').replace(/\/+$/, '')
      const localPath = this.config.localPath
      if (!localPath) return

      // Fetch all active files from server
      let allServerFiles = []
      let page = 1
      while (true) {
        const res = await axios.get(`${this.config.serverUrl}/api/files?page=${page}&page_size=200`, {
          headers: { Authorization: 'Bearer ' + this.config.token }
        })
        const data = res.data
        if (!data || !data.files) break
        allServerFiles = allServerFiles.concat(data.files)
        if (data.files.length < 200) break
        page++
      }

      // Build current server paths set
      const currentServerPaths = new Set()
      const serverFileMap = {}
      for (const f of allServerFiles) {
        if (f.is_folder) continue
        const fp = (f.folder_path || '/').replace(/\/+$/, '')
        const fn = f.original_name || ''
        const fileRel = fp.endsWith('/' + fn) ? fp : (fp + '/' + fn).replace(/\/+/g, '/')
        if (serverPrefix === '' || serverPrefix === '/' || fileRel.startsWith(serverPrefix + '/') || fileRel === serverPrefix) {
          const rel = (serverPrefix === '' || serverPrefix === '/') ? fileRel.replace(/^\//, '') : fileRel.slice(serverPrefix.length + 1)
          currentServerPaths.add(rel)
          serverFileMap[rel] = f
        }
      }

      // Handle server deletions (was synced, now gone from server)
      for (const rel of this._prevServerPaths) {
        if (!currentServerPaths.has(rel)) {
          const localFile = path.join(localPath, rel)
          if (fs.existsSync(localFile)) {
            try { fs.unlinkSync(localFile); if (this.onEvent) this.onEvent({ direction: 'remote', file_path: rel, event_type: 'delete' }) } catch {}
          }
        }
      }

      // Download new/modified server files
      for (const [rel, f] of Object.entries(serverFileMap)) {
        const localFile = path.join(localPath, rel)
        if (!fs.existsSync(localFile)) {
          this._downloadFile(f.id, localFile, rel)
        }
      }

      // Walk local files
      const currentLocalPaths = new Set()
      const walkDir = (dir, prefix) => {
        let entries
        try { entries = fs.readdirSync(dir, { withFileTypes: true }) } catch { return }
        for (const entry of entries) {
          if (entry.name.startsWith('.')) continue
          const fullPath = path.join(dir, entry.name)
          const relPath = prefix ? prefix + '/' + entry.name : entry.name
          if (entry.isDirectory()) {
            walkDir(fullPath, relPath)
          } else {
            currentLocalPaths.add(relPath)
          }
        }
      }
      walkDir(localPath, '')

      // Handle local deletions (was synced, now gone from local)
      for (const rel of this._prevLocalPaths) {
        if (!currentLocalPaths.has(rel) && this._syncedPaths.has(rel)) {
          const serverFile = serverFileMap[rel]
          if (serverFile?.id) {
            try {
              await axios.delete(`${this.config.serverUrl}/api/files/${serverFile.id}`, {
                headers: { Authorization: 'Bearer ' + this.config.token }
              })
              if (this.onEvent) this.onEvent({ direction: 'local', file_path: rel, event_type: 'delete' })
            } catch {}
          }
        }
      }

      // Upload new local files
      for (const rel of currentLocalPaths) {
        if (!currentServerPaths.has(rel) && !this._syncedPaths.has(rel)) {
          this._uploadFile(path.join(localPath, rel), rel)
        }
      }

      // Update state
      this._prevServerPaths = new Set(currentServerPaths)
      this._prevLocalPaths = new Set(currentLocalPaths)
      for (const rel of currentServerPaths) this._syncedPaths.add(rel)
      for (const rel of currentLocalPaths) this._syncedPaths.add(rel)

    } catch (err) {
      if (err.response?.status === 401 && this.onUnauthorized) this.onUnauthorized()
    }
  }

  async _uploadFile(filePath, relativePath) {
    try {
      const relParts = relativePath.replace(/\\/g, '/').split('/')
      const filename = relParts.pop()
      const base = (this.config.serverPath || '/').replace(/\/+$/, '') || ''
      const sub = relParts.length ? '/' + relParts.join('/') : ''
      const folderPath = base + sub + '/'
      const urlRes = await axios.post(`${this.config.serverUrl}/api/files/upload-url`, {
        filename, folder_path: folderPath
      }, { headers: { Authorization: 'Bearer ' + this.config.token } })
      if (urlRes.data?.upload_url && urlRes.data?.file_id) {
        const fileContent = fs.readFileSync(filePath)
        await axios.put(urlRes.data.upload_url, fileContent, { headers: { 'Content-Type': 'application/octet-stream' } })
        await axios.post(`${this.config.serverUrl}/api/files/confirm`, { file_id: urlRes.data.file_id }, { headers: { Authorization: 'Bearer ' + this.config.token } })
        if (this.onEvent) this.onEvent({ direction: 'local', file_path: relativePath, event_type: 'create' })
      }
    } catch (err) {
      if (err.response?.status === 401 && this.onUnauthorized) this.onUnauthorized()
    }
  }

  async _downloadFile(fileId, localPath, relPath) {
    try {
      const res = await axios.get(`${this.config.serverUrl}/api/files/${fileId}/download-url`, {
        headers: { Authorization: 'Bearer ' + this.config.token }
      })
      const downloadUrl = res.data.download_url
      if (!downloadUrl) return
      // Ensure parent directory exists and localPath is a file, not a directory
      let targetPath = localPath
      if (fs.existsSync(targetPath) && fs.statSync(targetPath).isDirectory()) {
        targetPath = path.join(targetPath, path.basename(targetPath))
      }
      const dir = path.dirname(targetPath)
      if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true })
      const fileRes = await axios.get(downloadUrl, { responseType: 'stream' })
      const writer = fs.createWriteStream(targetPath)
      fileRes.data.pipe(writer)
      await new Promise((resolve, reject) => {
        writer.on('finish', () => {
          if (this.onEvent) this.onEvent({ direction: 'remote', file_path: relPath, event_type: 'create' })
          resolve()
        })
        writer.on('error', reject)
      })
    } catch (err) {
      console.error('Download failed:', err.message)
    }
  }

  _startWatching() {
    if (!this.config?.localPath) return
    this.setStatus('syncing')

    this.watcher = chokidar.watch(this.config.localPath, {
      ignoreInitial: true,
      awaitWriteFinish: { stabilityThreshold: 500, pollInterval: 100 },
      ignored: /(^|[\/\\])\../  // ignore dot files
    })

    const sendEvent = async (eventType, filePath) => {
      const relativePath = path.relative(this.config.localPath, filePath)
      if (!relativePath || relativePath.startsWith('.')) return

      this.pendingEvents++
      const event = {
        type: 'file_change',
        event_type: eventType,
        file_path: relativePath.replace(/\\/g, '/'),
        timestamp: new Date().toISOString()
      }

      if (this.onEvent) this.onEvent(event)
      this.setStatus('syncing')

      if (eventType !== 'delete') this._uploadFile(filePath, relativePath)
    }

    this.watcher.on('add', p => sendEvent('create', p))
    this.watcher.on('change', p => sendEvent('modify', p))
    this.watcher.on('unlink', p => sendEvent('delete', p))
  }

  _stopWatching() {
    if (this.watcher) {
      this.watcher.close()
      this.watcher = null
    }
  }

  setStatus(status) {
    this.status = status
    if (this.onStatusChange) this.onStatusChange(status)
  }
}

module.exports = { SyncEngine }
