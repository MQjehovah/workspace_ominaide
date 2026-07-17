const chokidar = require('chokidar')
const WebSocket = require('ws')
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
    this.setStatus('connecting')

    try {
      // Connect WebSocket
      this.ws = new WebSocket(
        `${this._wsUrl()}/ws/sync/${config.workspaceId}?token=${config.token}`
      )

      this.ws.on('open', () => {
        this.setStatus('connected')
        this._startWatching()
      })

      this.ws.on('message', (data) => {
        const event = JSON.parse(data.toString())
        this._handleRemoteEvent(event)
      })

      this.ws.on('close', () => {
        this.setStatus('disconnected')
        this._stopWatching()
        // Auto-reconnect after 5 seconds
        setTimeout(() => {
          if (this.config) this.start(this.config)
        }, 5000)
      })

      this.ws.on('error', () => {
        this.setStatus('disconnected')
      })

    } catch (err) {
      this.setStatus('disconnected')
      throw err
    }
  }

  stop() {
    this._stopWatching()
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
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

  _startWatching() {
    if (!this.config?.localPath) return
    this.setStatus('syncing')

    this.watcher = chokidar.watch(this.config.localPath, {
      ignoreInitial: true,
      awaitWriteFinish: { stabilityThreshold: 500, pollInterval: 100 },
      ignored: /(^|[\/\\])\../  // ignore dot files
    })

    const sendEvent = (eventType, filePath) => {
      const relativePath = path.relative(this.config.localPath, filePath)
      if (!relativePath || relativePath.startsWith('.')) return
      
      this.pendingEvents++
      const event = {
        type: 'file_change',
        event_type: eventType,
        file_path: relativePath.replace(/\\/g, '/'),
        timestamp: new Date().toISOString()
      }

      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify(event))
      }
      
      if (this.onEvent) this.onEvent(event)
      this.setStatus('syncing')
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

  _handleRemoteEvent(event) {
    // Server tells us a file changed remotely
    if (this.onEvent) this.onEvent({ ...event, direction: 'remote' })
    
    if (!this.config?.localPath) return
    
    const localPath = path.join(this.config.localPath, event.file_path)
    
    if (event.event_type === 'delete') {
      try { fs.unlinkSync(localPath) } catch {}
    } else {
      // Download file from server
      this._downloadFile(event.file_id, localPath)
    }
  }

  async _downloadFile(fileId, localPath) {
    try {
      const res = await axios.get(
        `${this.config.serverUrl}/api/v1/files/${fileId}/download-url`,
        { headers: { Authorization: `Bearer ${this.config.token}` } }
      )
      const downloadUrl = res.data.download_url
      const fileRes = await axios.get(downloadUrl, { responseType: 'stream' })
      
      const dir = path.dirname(localPath)
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true })
      }
      
      const writer = fs.createWriteStream(localPath)
      fileRes.data.pipe(writer)
      await new Promise((resolve, reject) => {
        writer.on('finish', resolve)
        writer.on('error', reject)
      })
    } catch (err) {
      console.error('Download failed:', err.message)
    }
  }

  _wsUrl() {
    return this.config.serverUrl.replace(/^http/, 'ws')
  }

  setStatus(status) {
    this.status = status
    if (this.onStatusChange) this.onStatusChange(status)
  }
}

module.exports = { SyncEngine }
