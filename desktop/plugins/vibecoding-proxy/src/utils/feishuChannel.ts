import { FeishuClient } from './feishuClient'
import type { ChannelConfig, ChannelInstance } from './channelManager'

type Handler = (text: string, replyId: string, chatId: string, userId: string) => void

export class FeishuChannel implements ChannelInstance {
  type = 'feishu' as const
  config: ChannelConfig
  private client: FeishuClient | null = null
  private handler: Handler
  private statusText = 'stopped'

  constructor(config: ChannelConfig, handler: Handler) {
    this.config = config
    this.handler = handler
  }

  async start(): Promise<boolean> {
    this.stop()
    const { appId, appSecret } = this.config.config || {}
    if (!appId || !appSecret) return false
    try {
      this.client = new FeishuClient({ appId, appSecret })
      this.client.onStatusChange = (s: string) => { this.statusText = s }
      this.client.setHandler({
        onMessage: async (chatId, userId, text, messageId) => {
          this.handler(text, messageId, chatId, userId)
        },
      })
      this.client.start()
      this.statusText = 'connecting'
      return true
    } catch { return false }
  }

  stop() {
    if (this.client) { try { this.client.stop() } catch {} this.client = null }
    this.statusText = 'stopped'
  }

  status(): string {
    return this.statusText || (this.client ? 'connected' : 'stopped')
  }

  async reply(replyId: string, text: string): Promise<void> {
    if (!this.client) throw new Error('飞书未连接')
    if (replyId) {
      await this.client.replyMessage(replyId, text)
    } else {
      await this.client.sendDirect(text)
    }
  }
}
