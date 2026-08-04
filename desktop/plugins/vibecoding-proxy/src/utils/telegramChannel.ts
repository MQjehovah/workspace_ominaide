import type { ChannelConfig, ChannelInstance } from './channelManager'

type Handler = (text: string, replyId: string, chatId: string, userId: string) => void

const API = 'https://api.telegram.org'

export class TelegramChannel implements ChannelInstance {
  type = 'telegram' as const
  config: ChannelConfig
  private handler: Handler
  private token = ''
  private running = false
  private pollTimer: any = null
  private offset = 0
  private lastChatId = ''
  private statusText = 'stopped'

  constructor(config: ChannelConfig, handler: Handler) {
    this.config = config
    this.handler = handler
    this.token = (config.config || {}).botToken || ''
  }

  async start(): Promise<boolean> {
    this.stop()
    if (!this.token) return false
    this.running = true
    this.statusText = 'connecting'
    this.poll()
    return true
  }

  stop() {
    this.running = false
    if (this.pollTimer) { clearTimeout(this.pollTimer); this.pollTimer = null }
    this.statusText = 'stopped'
  }

  status(): string { return this.statusText }

  private async poll() {
    if (!this.running) return
    try {
      const url = `${API}/bot${this.token}/getUpdates?timeout=25&offset=${this.offset}`
      const res = await fetch(url)
      const data: any = await res.json()
      if (data.ok) {
        this.statusText = 'connected'
        for (const update of data.result || []) {
          this.offset = Math.max(this.offset, update.update_id + 1)
          const msg = update.message || update.edited_message
          if (!msg) continue
          const text = msg.text || ''
          if (!text) continue
          const chatId = String(msg.chat?.id || '')
          const userId = String(msg.from?.id || '')
          const messageId = String(msg.message_id || '')
          this.lastChatId = chatId
          this.handler(text, messageId, chatId, userId)
        }
      } else if (data.error_code === 401) {
        this.statusText = 'error: 无效 token'
        this.running = false
        return
      }
    } catch {
      this.statusText = 'reconnecting'
    }
    if (this.running) this.pollTimer = setTimeout(() => this.poll(), 500)
  }

  async reply(replyId: string, text: string): Promise<void> {
    const chatId = this.lastChatId
    if (!chatId) throw new Error('Telegram 未收到过消息')
    // Telegram allows replying to a message via reply_to_message_id
    const body: any = { chat_id: chatId, text, parse_mode: 'Markdown' }
    if (replyId) body.reply_to_message_id = Number(replyId)
    const res = await fetch(`${API}/bot${this.token}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error('Telegram 发送失败')
  }
}
