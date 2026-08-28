import { Notification } from 'electron'
import { randomUUID } from 'crypto'
import { getConfig, setConfig } from './config'
import { writeLog } from './logger'

const WebSocket: any = require('ws')

/**
 * Backend Channel — the single multiplexed WebSocket every desktop plugin
 * shares (`/ws/host`). Messages carry a `channel` namespace; the backend
 * routes them to the owning backend plugin, and inbound messages are routed
 * back to the desktop plugin that subscribed to that channel.
 *
 * The channel `notifications` is host-owned: pushes show a system
 * notification directly.
 */

type InboundDispatcher = (channel: string, msg: any) => void

let ws: any = null
let reconnectTimer: any = null
let pingTimer: any = null
let lastSignature: string = ''
let deviceId = ''
let dispatcher: InboundDispatcher | null = null
const queue: any[] = []

const MAX_QUEUE = 500

export function setInboundDispatcher(fn: InboundDispatcher): void {
  dispatcher = fn
}

export function channelSend(channel: string, msg: Record<string, unknown>): void {
  const wrapped = { channel, ...msg }
  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify(wrapped))
      return
    } catch {}
  }
  queue.push(wrapped)
  if (queue.length > MAX_QUEUE) queue.shift()
}

export function channelStatus() {
  return {
    enabled: true,
    connected: !!(ws && ws.readyState === WebSocket.OPEN),
    deviceId,
    queued: queue.length,
  }
}

export async function startBackendChannel(): Promise<void> {
  const cfg = await getConfig()
  const token = cfg.token || ''
  const serverUrl = cfg.serverUrl || 'http://localhost:8000'
  const signature = `${serverUrl}|${token}`

  if (!token) {
    stopBackendChannel()
    lastSignature = ''
    return
  }

  if (signature !== lastSignature) {
    stopBackendChannel()
    lastSignature = signature
  }
  if (ws) return

  if (!deviceId) {
    deviceId = cfg.hostDeviceId || ''
    if (!deviceId) {
      deviceId = randomUUID()
      await setConfig('hostDeviceId', deviceId)
    }
  }

  try {
    const base = serverUrl.replace(/^http/, 'ws').replace(/\/+$/, '')
    ws = new WebSocket(
      `${base}/ws/host?token=${encodeURIComponent(token)}&device_id=${encodeURIComponent(deviceId)}&device_name=${encodeURIComponent(require('os').hostname())}`
    )

    ws.on('message', (data: any) => handleInbound(data))
    ws.on('open', () => {
      const pending = queue.splice(0, queue.length)
      for (const msg of pending) {
        try { ws?.send(JSON.stringify(msg)) } catch { break }
      }
      if (!pingTimer) {
        pingTimer = setInterval(() => {
          try { ws?.send(JSON.stringify({ type: 'ping' })) } catch {}
        }, 30000)
      }
    })
    ws.on('close', () => {
      ws = null
      if (pingTimer) { clearInterval(pingTimer); pingTimer = null }
      scheduleReconnect()
    })
    ws.on('error', () => {
      try { ws?.close() } catch { /* ignore */ }
    })
  } catch (e: any) {
    writeLog('system', 'error', `backend channel error: ${e?.message || e}`)
    scheduleReconnect()
  }
}

function handleInbound(data: any): void {
  try {
    const msg = JSON.parse(String(data))
    if (!msg || typeof msg !== 'object') return
    if (msg.channel === 'notifications' || (!msg.channel && (msg.title || msg.body))) {
      const title = msg.title || '通知'
      const body = msg.body || ''
      if (title || body) new Notification({ title, body, silent: false }).show()
      return
    }
    if (msg.channel && dispatcher) dispatcher(String(msg.channel), msg)
  } catch { /* ignore */ }
}

function scheduleReconnect() {
  if (reconnectTimer) return
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    startBackendChannel().catch(() => {})
  }, 10000)
}

export function stopBackendChannel(): void {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (pingTimer) {
    clearInterval(pingTimer)
    pingTimer = null
  }
  if (ws) {
    try { ws.close() } catch { /* ignore */ }
    ws = null
  }
}
