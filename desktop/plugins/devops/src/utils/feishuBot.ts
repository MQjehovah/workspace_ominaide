export interface FeishuConfig {
  webhookUrl: string
  secret: string
  enabled: boolean
}

export interface FeishuMessage {
  sender: string
  content: string
  timestamp: number
  chatType: 'group' | 'private'
}

const DEFAULT_CONFIG: FeishuConfig = { webhookUrl: '', secret: '', enabled: false }

let config: FeishuConfig = { ...DEFAULT_CONFIG }

export function getConfig(): FeishuConfig { return config }

export async function loadConfig(storage: { get: (k: string) => Promise<any> }) {
  const saved = await storage.get('feishu_config')
  if (saved) config = { ...DEFAULT_CONFIG, ...saved }
}

export async function saveConfig(storage: { set: (k: string, v: any) => Promise<void> }, cfg: FeishuConfig) {
  config = { ...cfg }
  await storage.set('feishu_config', config)
}

export async function sendFeishuMessage(text: string): Promise<boolean> {
  if (!config.webhookUrl || !config.enabled) return false
  try {
    const payload: any = { msg_type: 'text', content: { text } }
    if (config.secret) {
      const ts = Math.floor(Date.now() / 1000)
      const sign = await signWithSecret(config.secret, ts)
      payload.sign = sign
      payload.timestamp = ts
    }
    const res = await fetch(config.webhookUrl, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    return res.ok
  } catch {
    return false
  }
}

export async function sendCardMessage(title: string, content: string, buttons?: Array<{ text: string; value: string }>): Promise<boolean> {
  if (!config.webhookUrl || !config.enabled) return false
  try {
    const elements: any[] = [{ tag: 'div', text: { tag: 'lark_md', content } }]
    if (buttons?.length) {
      elements.push({
        tag: 'action',
        actions: buttons.map(b => ({
          tag: 'button',
          text: { tag: 'plain_text', content: b.text },
          value: { action: b.value },
        })),
      })
    }
    const payload: any = {
      msg_type: 'interactive',
      card: { header: { title: { tag: 'plain_text', content: title } }, elements },
    }
    if (config.secret) {
      const ts = Math.floor(Date.now() / 1000)
      const sign = await signWithSecret(config.secret, ts)
      payload.sign = sign
      payload.timestamp = ts
    }
    const res = await fetch(config.webhookUrl, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    return res.ok
  } catch {
    return false
  }
}

export async function handleFeishuWebhook(body: any, api: { get: (p: string) => Promise<any>; post: (p: string, b?: any) => Promise<any> }) {
  const { event } = body
  if (!event) return { code: 0 }

  const msg: FeishuMessage = {
    sender: event.sender?.sender_id?.user_id || 'unknown',
    content: event.message?.content || '',
    timestamp: Number(event.ts || Date.now()),
    chatType: event.message?.chat_type === 'group' ? 'group' : 'private',
  }

  return { code: 0, message: msg }
}

async function signWithSecret(secret: string, timestamp: number): Promise<string> {
  const enc = new TextEncoder()
  const key = await crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'])
  const data = enc.encode(`${timestamp}`)
  const sig = await crypto.subtle.sign('HMAC', key, data)
  return Array.from(new Uint8Array(sig)).map(b => b.toString(16).padStart(2, '0')).join('')
}
