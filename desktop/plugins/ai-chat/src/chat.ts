export interface ChatConfig {
  mode: 'backend' | 'direct'
  apiKey: string
  baseUrl: string
  model: string
}

export function loadConfig(): ChatConfig {
  try {
    const raw = localStorage.getItem('ai_chat_config')
    if (raw) return JSON.parse(raw)
  } catch {}
  return { mode: 'backend', apiKey: '', baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' }
}

export function saveConfig(cfg: ChatConfig) {
  localStorage.setItem('ai_chat_config', JSON.stringify(cfg))
}

export async function sendMessage(
  message: string,
  history: { role: string; content: string }[],
  config: ChatConfig,
): Promise<string> {
  if (config.mode === 'backend') {
    const w = window as any
    const su = (await w.mqbox?.config?.get('serverUrl')) || 'http://localhost:8000'
    const tk = (await w.mqbox?.config?.get('token')) || ''
    const r = await fetch(`${su}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + tk },
      body: JSON.stringify({ message, history }),
    }).then(r => { if (!r.ok) throw new Error(r.statusText); return r.json() })
    return r.reply || '(no response)'
  } else {
    const messages = [...history, { role: 'user', content: message }]
    const r = await fetch(`${config.baseUrl}/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + config.apiKey },
      body: JSON.stringify({ model: config.model, messages, temperature: 0.7 }),
    }).then(r => { if (!r.ok) throw new Error(r.statusText); return r.json() })
    if (r.error) throw new Error(r.error.message || JSON.stringify(r.error))
    return r.choices?.[0]?.message?.content || '(no response)'
  }
}
