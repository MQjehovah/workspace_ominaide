import { Notification } from 'electron'
import WebSocket from 'ws'
import { getConfig } from './config'
import { writeLog } from './logger'

/**
 * Notification Center — a basic main-process capability.
 *
 * Maintains a WebSocket connection to the backend `/ws/notifications` and shows
 * a system notification whenever the cloud pushes one (e.g. important mail
 * identified by the LLM). Reconnects automatically and restarts on token change.
 */

let ws: WebSocket | null = null
let reconnectTimer: any = null
let lastSignature: string = ''

function wsUrl(serverUrl: string): string {
  return serverUrl.replace(/^http/, 'ws').replace(/\/+$/, '') + '/ws/notifications'
}

export async function startNotificationCenter(): Promise<void> {
  const cfg = await getConfig()
  const token = cfg.token || ''
  const serverUrl = cfg.serverUrl || 'http://localhost:8000'
  const signature = `${serverUrl}|${token}`

  if (!token) {
    stopNotificationCenter()
    lastSignature = ''
    return
  }

  if (signature !== lastSignature) {
    // Token/server changed — tear down and reconnect fresh.
    stopNotificationCenter()
    lastSignature = signature
  }
  if (ws) return // already connected

  try {
    ws = new WebSocket(`${wsUrl(serverUrl)}?token=${encodeURIComponent(token)}`)

    ws.on('message', (data) => {
      try {
        const msg = JSON.parse(data.toString())
        const title = msg?.title || '通知'
        const body = msg?.body || ''
        if (title || body) {
          new Notification({ title, body, silent: false }).show()
        }
      } catch { /* ignore */ }
    })

    ws.on('close', () => {
      ws = null
      scheduleReconnect()
    })
    ws.on('error', () => {
      try { ws?.close() } catch { /* ignore */ }
    })
  } catch (e: any) {
    writeLog('system', 'error', `notification ws error: ${e?.message || e}`)
    scheduleReconnect()
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    startNotificationCenter().catch(() => {})
  }, 10000)
}

export function stopNotificationCenter(): void {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (ws) {
    try { ws.close() } catch { /* ignore */ }
    ws = null
  }
}
