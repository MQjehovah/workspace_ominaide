import { createServer } from 'http'
import type { ChannelConfig, ChannelInstance } from './channelManager'

type Handler = (text: string, replyId: string, chatId: string, userId: string) => void

export class WebhookChannel implements ChannelInstance {
  type = 'webhook' as const
  config: ChannelConfig
  private handler: Handler
  private server: any = null
  private statusText = 'stopped'
  private callbackUrl = ''

  constructor(config: ChannelConfig, handler: Handler) {
    this.config = config
    this.handler = handler
    this.callbackUrl = (config.config || {}).callbackUrl || ''
  }

  async start(): Promise<boolean> {
    this.stop()
    const port = Number((this.config.config || {}).port || 8841)
    try {
      this.server = createServer((req: any, res: any) => {
        let body = ''
        req.on('data', (c: Buffer) => { body += c.toString() })
        req.on('end', () => {
          res.setHeader('Content-Type', 'application/json')
          if (req.method === 'POST') {
            try {
              const payload = JSON.parse(body || '{}')
              const text = payload.text || payload.message || payload.content || ''
              const chatId = String(payload.chat_id || 'webhook')
              const userId = String(payload.user_id || '')
              const replyId = String(payload.reply_id || '')
              if (text) {
                // Reply inline in the HTTP response when possible
                this.handler(text, replyId, chatId, userId)
                res.end(JSON.stringify({ ok: true }))
              } else {
                res.end(JSON.stringify({ ok: false, error: 'no text field' }))
              }
            } catch (e: any) {
              res.end(JSON.stringify({ ok: false, error: e.message }))
            }
          } else if (req.method === 'GET') {
            res.end(JSON.stringify({ ok: true, status: 'webhook running' }))
          } else {
            res.end(JSON.stringify({ ok: false, error: 'method not allowed' }))
          }
        })
      })
      await new Promise<void>((resolve, reject) => {
        this.server.once('error', reject)
        this.server.listen(port, '127.0.0.1', () => resolve())
      })
      this.statusText = `listening:${port}`
      return true
    } catch (e: any) {
      this.statusText = `error: ${e.message}`
      return false
    }
  }

  stop() {
    if (this.server) { try { this.server.close() } catch {} this.server = null }
    this.statusText = 'stopped'
  }

  status(): string { return this.statusText }

  async reply(replyId: string, text: string): Promise<void> {
    if (this.callbackUrl) {
      const res = await fetch(this.callbackUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reply_id: replyId || '', text }),
      })
      if (!res.ok) throw new Error('callbackUrl 发送失败')
    }
    // If no callbackUrl, the reply is delivered via the response to the original POST.
    // In that case there is nothing to push back (the caller already got {ok:true}).
  }
}
