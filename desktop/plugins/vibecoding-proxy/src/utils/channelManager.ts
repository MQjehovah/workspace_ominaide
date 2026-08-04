import { FeishuChannel } from './feishuChannel'
import { TelegramChannel } from './telegramChannel'
import { WebhookChannel } from './webhookChannel'

export type ChannelType = 'feishu' | 'telegram' | 'webhook'

export interface ChannelConfig {
  id: string
  type: ChannelType
  name: string
  enabled: boolean
  config: Record<string, any>
}

export interface IncomingMessage {
  channelId: string
  text: string
  replyId: string
  chatId: string
  userId: string
}

export interface ChannelInstance {
  type: ChannelType
  config: ChannelConfig
  start: () => Promise<boolean>
  stop: () => void
  status: () => string
  reply: (replyId: string, text: string) => Promise<void>
}

export interface ChannelManager {
  getChannels: () => ChannelConfig[]
  getChannel: (id: string) => ChannelInstance | null
  saveChannel: (cfg: ChannelConfig) => Promise<void>
  removeChannel: (id: string) => Promise<boolean>
  startAll: () => Promise<void>
  stopAll: () => void
  getStatus: () => { id: string; type: ChannelType; name: string; enabled: boolean; status: string }[]
  sendTest: (id: string) => Promise<boolean>
}

export const CHANNEL_TYPES: { type: ChannelType; label: string; desc: string }[] = [
  { type: 'feishu', label: '飞书', desc: '飞书机器人（WebSocket 长连接，免公网）' },
  { type: 'telegram', label: 'Telegram', desc: 'Telegram Bot（长轮询，免公网）' },
  { type: 'webhook', label: 'HTTP Webhook', desc: '本地 HTTP 服务，任意客户端可 POST 消息' },
]

const STORAGE_KEY = 'channels'

export function createChannelManager(storage: { get: (k: string) => Promise<any>; set: (k: string, v: any) => Promise<void> }, onMessage: (msg: IncomingMessage) => void): ChannelManager {
  let channels: ChannelConfig[] = []
  const instances = new Map<string, ChannelInstance>()

  async function loadChannels() {
    const saved = await storage.get(STORAGE_KEY)
    channels = Array.isArray(saved) ? saved : []
    // Migrate legacy feishu_config into a channel
    if (channels.length === 0) {
      try {
        const old = await storage.get('feishu_config')
        if (old && (old.appId || old.appSecret)) {
          channels.push({
            id: 'feishu',
            type: 'feishu',
            name: '飞书',
            enabled: !!old.enabled,
            config: { appId: old.appId || '', appSecret: old.appSecret || '' },
          })
          await save()
        }
      } catch {}
    }
    return channels
  }

  async function save() {
    try { await storage.set(STORAGE_KEY, channels) } catch {}
  }

  function buildInstance(cfg: ChannelConfig): ChannelInstance | null {
    const handler = (text: string, replyId: string, chatId: string, userId: string) => {
      if (!text) return
      onMessage({ channelId: cfg.id, text, replyId, chatId, userId })
    }
    switch (cfg.type) {
      case 'feishu':
        return new FeishuChannel(cfg, handler)
      case 'telegram':
        return new TelegramChannel(cfg, handler)
      case 'webhook':
        return new WebhookChannel(cfg, handler)
      default:
        return null
    }
  }

  async function startAll() {
    for (const cfg of channels) {
      if (!cfg.enabled) continue
      try {
        const inst = buildInstance(cfg)
        if (inst) {
          instances.set(cfg.id, inst)
          await inst.start()
        }
      } catch (e: any) {
        console.error(`[channel:${cfg.id}] start error:`, e.message)
      }
    }
  }

  function stopAll() {
    for (const [, inst] of instances) { try { inst.stop() } catch {} }
    instances.clear()
  }

  return {
    getChannels: () => channels.map(c => ({ ...c })),
    getChannel: (id: string) => instances.get(id) || null,
    async saveChannel(cfg) {
      const idx = channels.findIndex(c => c.id === cfg.id)
      if (idx >= 0) channels[idx] = cfg
      else channels.push(cfg)
      await save()
      // (Re)start this channel if enabled
      const existing = instances.get(cfg.id)
      if (existing) { try { existing.stop() } catch {} }
      instances.delete(cfg.id)
      if (cfg.enabled) {
        const inst = buildInstance(cfg)
        if (inst) { instances.set(cfg.id, inst); await inst.start() }
      }
    },
    async removeChannel(id) {
      const idx = channels.findIndex(c => c.id === id)
      if (idx === -1) return false
      channels.splice(idx, 1)
      const inst = instances.get(id)
      if (inst) { try { inst.stop() } catch {} }
      instances.delete(id)
      await save()
      return true
    },
    startAll,
    stopAll,
    getStatus() {
      return channels.map(c => {
        const inst = instances.get(c.id)
        return {
          id: c.id,
          type: c.type,
          name: c.name,
          enabled: c.enabled,
          status: inst ? inst.status() : (c.enabled ? 'starting' : 'stopped'),
        }
      })
    },
    async sendTest(id) {
      const inst = instances.get(id)
      if (!inst) return false
      try {
        await inst.reply('', '✅ VibeCoding Proxy 测试消息')
        return true
      } catch { return false }
    },
  }
}
