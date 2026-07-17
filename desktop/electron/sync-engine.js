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
    this._pollTimer = setInterval(() => this._pollOnce(), 30000) // every 30 seconds
  }

  _stopPolling() {
    if (this._pollTimer) { clearInterval(this._pollTimer); this._pollTimer = null }
  }

  async _pollOnce() {
    try {
      const folder = this.config.serverPath || '/'
      const res = await axios.get(`${this.config.serverUrl}/api/files?page_size=200&folder_path=${encodeURIComponent(folder)}`, {
        headers: { Authorization: 'Bearer ' + this.config.token }
      })
      const files = res.data?.files || []
      const localPath = this.config.localPath
      for (const f of files) {
        if (f.is_folder) continue
        const relPath = f.folder_path.replace(/\/$/, '') + '/' + f.original_name
        const localFile = path.join(localPath, relPath)
        if (!fs.existsSync(localFile)) {
          this._downloadFile(f.id, localFile, relPath)
        }
      }
    } catch (err) {
      // Silent
    }
  }

  async _downloadFile(fileId, localPath, relPath) {
    try {
      const res = await axios.get(`${this.config.serverUrl}/api/files/${fileId}/download-url`, {
        headers: { Authorization: 'Bearer ' + this.config.token }
      })
      const downloadUrl = res.data.download_url
      if (!downloadUrl) return
      const fileRes = await axios.get(downloadUrl, { responseType: 'stream' })
      const dir = path.dirname(localPath)
      if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true })
      const writer = fs.createWriteStream(localPath)
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

      // Upload file to server
      if (eventType !== 'delete') {
        try {
          const serverPath = (this.config.serverPath || '/').replace(/\/?$/, '/') + relativePath.replace(/\\/g, '/')
          const filename = path.basename(filePath)
          const urlRes = await axios.post(`${this.config.serverUrl}/api/files/upload-url`, {
            filename, folder_path: serverPath
          }, { headers: { Authorization: 'Bearer ' + this.config.token } })
          if (urlRes.data?.upload_url) {
            const fs = require('fs')
            const fileContent = fs.readFileSync(filePath)
            await axios.put(urlRes.data.upload_url, fileContent, { headers: { 'Content-Type': 'application/octet-stream' } })
            await axios.post(`${this.config.serverUrl}/api/files/confirm`, { file_id: urlRes.data.file_id }, { headers: { Authorization: 'Bearer ' + this.config.token } })
          }
        } catch (err) {
          console.error('Upload failed:', err.message)
        }
      }
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
