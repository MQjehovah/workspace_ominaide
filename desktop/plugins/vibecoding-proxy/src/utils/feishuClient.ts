import WebSocket from 'ws'
import protobuf from 'protobufjs'

const protoDefinition = `
syntax = "proto2";
package pbbp2;
message Header {
  required string key = 1;
  required string value = 2;
}
message Frame {
  required uint64 SeqID = 1;
  required uint64 LogID = 2;
  required int32 service = 3;
  required int32 method = 4;
  repeated Header headers = 5;
  optional string payload_encoding = 6;
  optional string payload_type = 7;
  optional bytes payload = 8;
  optional string LogIDNew = 9;
}
`

const FEISHU_BASE = 'https://open.feishu.cn/open-apis'
const ENDPOINT_URL = 'https://open.feishu.cn/callback/ws/endpoint'

interface FeishuConfig {
  appId: string
  appSecret: string
}

interface EventHandler {
  onMessage?: (chatId: string, userId: string, text: string, messageId: string) => Promise<void>
}

export class FeishuClient {
  private config: FeishuConfig
  private ws: WebSocket | null = null
  private running = false
  private rootType: protobuf.Type | null = null
  private seenEvents = new Set<string>()
  private handler: EventHandler = {}
  private seqId = 0
  private reconnectTimer: any = null
  lastMessageId = ''
  lastChatId = ''
  onStatusChange?: (status: string) => void

  constructor(config: FeishuConfig) {
    this.config = config
  }

  setHandler(h: EventHandler) { this.handler = h }

  async start() {
    this.running = true
    this.rootType = await this.loadProto()
    this.connect()
  }

  stop() {
    this.running = false
    if (this.reconnectTimer) { clearTimeout(this.reconnectTimer); this.reconnectTimer = null }
    if (this.ws) { try { this.ws.close() } catch {} this.ws = null }
    this.onStatusChange?.('disconnected')
  }

  private async loadProto(): Promise<protobuf.Type> {
    const root = protobuf.parse(protoDefinition).root
    return root.lookupType('pbbp2.Frame')
  }

  private async getEndpoint(): Promise<string> {
    const resp = await fetch(ENDPOINT_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', locale: 'zh' },
      body: JSON.stringify({ AppID: this.config.appId, AppSecret: this.config.appSecret }),
    })
    const data: any = await resp.json()
    if (data.code !== 0) throw new Error(`获取飞书 WS endpoint 失败: ${data.msg}`)
    if (!data.data?.URL) throw new Error('飞书 WS endpoint 返回空 URL')
    return data.data.URL
  }

  private async getToken(): Promise<string> {
    const resp = await fetch(`${FEISHU_BASE}/auth/v3/tenant_access_token/internal`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ app_id: this.config.appId, app_secret: this.config.appSecret }),
    })
    const data: any = await resp.json()
    if (data.code !== 0) throw new Error(`获取飞书 token 失败: ${data.msg}`)
    return data.tenant_access_token
  }

  private async connect() {
    while (this.running) {
      try {
        const url = await this.getEndpoint()
        this.onStatusChange?.('connecting')
        this.ws = new WebSocket(url)

        this.ws.on('open', () => {
          this.onStatusChange?.('connected')
        })

        this.ws.on('message', (raw: Buffer) => this.handleFrame(raw))

        this.ws.on('close', () => {
          this.ws = null
          if (this.running) { this.onStatusChange?.('reconnecting'); this.scheduleReconnect() }
          else this.onStatusChange?.('disconnected')
        })

        this.ws.on('error', () => {})
        await new Promise<void>((resolve) => { this.ws!.once('close', () => resolve()) })

      } catch (e: any) {
        this.onStatusChange?.(`error: ${e.message}`)
        if (this.running) await this.sleep(5000)
        else break
      }
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.reconnectTimer = setTimeout(() => this.connect(), 5000)
  }

  private handleFrame(raw: Buffer) {
    try {
      if (!this.rootType) return
      const frame = this.rootType.decode(raw)
      const headers: Record<string, string> = {}
      if (frame.headers) {
        for (const h of frame.headers as any[]) {
          headers[h.key] = h.value
        }
      }
      const msgType = headers['type'] || ''
      if (msgType === 'ping') return

      const payloadStr = frame.payload?.toString('utf-8') || '{}'
      let payload: any
      try { payload = JSON.parse(payloadStr) } catch { return }

      // ACK
      const ackFrame = this.rootType.encode({
        SeqID: ++this.seqId,
        LogID: Number(frame.LogID) || 0,
        service: Number(frame.service) || 0,
        method: Number(frame.method) || 0,
        headers: frame.headers || [],
        payload: Buffer.from(JSON.stringify({ code: 200 })),
      }).finish()
      this.ws?.send(ackFrame)

      // Handle event
      const header = payload.header || {}
      const eventType = header.event_type || ''
      const eventId = header.event_id || ''

      if (eventId && this.seenEvents.has(eventId)) return
      if (eventId) { this.seenEvents.add(eventId); if (this.seenEvents.size > 5000) this.seenEvents.clear() }

      if (eventType === 'im.message.receive_v1') {
        this.processMessage(payload.event || {})
      }

    } catch {}
  }

  private async processMessage(eventData: any) {
    const sender = eventData.sender || {}
    const userId = sender.sender_id?.user_id || ''
    const message = eventData.message || {}
    const chatId = message.chat_id || ''
    const messageId = message.message_id || ''
    const msgType = message.message_type || ''

    let contentStr = message.content || '{}'
    let contentObj: any = {}
    try { contentObj = JSON.parse(contentStr) } catch {}

    let text = ''
    if (msgType === 'text') text = (contentObj.text || '').trim()
    else if (msgType === 'post') {
      const parts = contentObj.content || []
      for (const plist of parts) for (const p of plist) text += p.text || ''
    }

    if (!text) return

    this.lastMessageId = messageId
    this.lastChatId = chatId
    this.handler.onMessage?.(chatId, userId, text, messageId)
  }

  async replyMessage(messageId: string, text: string) {
    try {
      const token = await this.getToken()
      const chunks = this.splitMarkdown(text, 3800)
      for (let i = 0; i < chunks.length; i++) {
        let chunk = chunks[i]
        if (chunks.length > 1) chunk += `\n\n(${i + 1}/${chunks.length})`
        const content = JSON.stringify({
          config: { wide_screen_mode: true },
          header: { title: { tag: 'plain_text', content: chunk.split('\n')[0].replace(/^#+\s*/, '').slice(0, 50) || '回复' } },
          elements: [{ tag: 'markdown', content: chunk }],
        })
        await fetch(`${FEISHU_BASE}/im/v1/messages/${messageId}/reply`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ msg_type: 'interactive', content }),
        })
      }
    } catch {}
  }

  private splitMarkdown(text: string, maxLen: number): string[] {
    if (text.length <= maxLen) return [text]
    const chunks: string[] = []
    let remaining = text
    while (remaining) {
      if (remaining.length <= maxLen) { chunks.push(remaining); break }
      let cut = remaining.lastIndexOf('\n\n', maxLen)
      if (cut < maxLen / 2) cut = remaining.lastIndexOf('\n', maxLen)
      if (cut < maxLen / 2) cut = maxLen
      chunks.push(remaining.slice(0, cut))
      remaining = remaining.slice(cut).replace(/^\n+/, '')
    }
    return chunks
  }

  private sleep(ms: number) { return new Promise(r => setTimeout(r, ms)) }
}
