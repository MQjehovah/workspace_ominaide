import { FeishuClient } from './feishuClient'

export interface FeishuConfig {
  appId: string
  appSecret: string
  enabled: boolean
}

export interface FeishuMessage {
  sender: string
  content: string
  timestamp: number
  chatType: 'group' | 'private'
}

const DEFAULT_CONFIG: FeishuConfig = { appId: '', appSecret: '', enabled: false }

export let config: FeishuConfig = { ...DEFAULT_CONFIG }
let feishuClient: FeishuClient | null = null
let onMessageCallback: ((text: string, chatId: string, userId: string, msgId: string) => void) | null = null

export function setOnMessage(cb: (text: string, chatId: string, userId: string, msgId: string) => void) {
  onMessageCallback = cb
}

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
  if (!config.enabled) return false
  try {
    // Use direct API call instead of webhook
    const token = await getTenantToken()
    const payload = {
      receive_id: 'all',
      msg_type: 'interactive',
      content: JSON.stringify({
        config: { wide_screen_mode: true },
        header: { title: { tag: 'plain_text', content: text.split('\n')[0].slice(0, 50) } },
        elements: [{ tag: 'markdown', content: text }],
      }),
    }
    const res = await fetch('https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    return res.ok
  } catch {
    return false
  }
}

let tokenCache = { token: '', expires: 0 }
async function getTenantToken(): Promise<string> {
  if (tokenCache.token && Date.now() < tokenCache.expires - 60000) return tokenCache.token
  const res = await fetch('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ app_id: config.appId, app_secret: config.appSecret }),
  })
  const data: any = await res.json()
  if (data.code !== 0) throw new Error(`获取飞书 token 失败: ${data.msg}`)
  tokenCache = { token: data.tenant_access_token, expires: Date.now() + data.expire * 1000 }
  return data.tenant_access_token
}

export async function startFeishuClient() {
  stopFeishuClient()
  if (!config.appId || !config.appSecret || !config.enabled) return false
  feishuClient = new FeishuClient({ appId: config.appId, appSecret: config.appSecret })
  feishuClient.setHandler({
    onMessage: async (chatId, userId, text, messageId) => {
      if (onMessageCallback) onMessageCallback(text, chatId, userId, messageId)
    },
  })
  feishuClient.start()
  return true
}

export function stopFeishuClient() {
  if (feishuClient) { feishuClient.stop(); feishuClient = null }
}

export function getFeishuStatus(): string {
  return feishuClient ? 'running' : 'stopped'
}

export function getFeishuClient(): FeishuClient | null {
  return feishuClient
}
