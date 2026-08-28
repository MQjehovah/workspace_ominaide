export interface ChannelClientStatus {
  enabled: boolean
  connected: boolean
  deviceId: string
  queued: number
}

export type VibeEventType = 'started' | 'milestone' | 'output' | 'tool' | 'file' | 'done' | 'failed'

export interface VibeChannelClient {
  start: () => void
  stop: () => void
  emit: (taskId: string, event: VibeEventType, data: Record<string, unknown>) => void
  send: (msg: Record<string, unknown>) => void
  status: () => Promise<ChannelClientStatus>
  setServerMessageHandler: (fn: (msg: any) => void) => void
}

export const VIBE_CHANNEL = 'vibecoding'

/**
 * Thin client over the host's shared backend channel. All transport concerns
 * (websocket, reconnect, offline queue, auth, device identity) live in the
 * host main process; this just bridges signal calls to `channel:send` and
 * receives inbound via the `channelMessage` command.
 */
export function createVibeChannelClient(context: any): VibeChannelClient {
  const signal = (method: string, ...args: any[]): Promise<any> => {
    try {
      return Promise.resolve(context.signal(method, ...args))
    } catch {
      return Promise.resolve(null)
    }
  }

  return {
    start: () => { signal('channel:subscribe', VIBE_CHANNEL).catch(() => {}) },
    stop: () => { signal('channel:unsubscribe', VIBE_CHANNEL).catch(() => {}) },
    emit: (taskId, event, data) => {
      signal('channel:send', VIBE_CHANNEL, { type: 'task.event', task_id: taskId, event, data, ts: Date.now() }).catch(() => {})
    },
    send: (msg) => { signal('channel:send', VIBE_CHANNEL, msg).catch(() => {}) },
    status: async () => {
      try {
        const st = await signal('channel:status')
        return st || { enabled: false, connected: false, deviceId: '', queued: 0 }
      } catch {
        return { enabled: false, connected: false, deviceId: '', queued: 0 }
      }
    },
    setServerMessageHandler: (fn) => {
      context.registerCommand('channelMessage', async (args: any) => {
        if (args?.channel === VIBE_CHANNEL && args.msg) fn(args.msg)
      })
    },
  }
}
