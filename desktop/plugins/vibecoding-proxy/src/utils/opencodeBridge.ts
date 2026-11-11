import { exec } from 'child_process'
import { existsSync, readFileSync } from 'fs'
import { homedir } from 'os'
import { join } from 'path'

/**
 * Bridge to a local OpenCode 2 server (`opencode serve`).
 *
 * The server keeps sessions, messages and the agent loop. This module only
 * forwards normalized requests from remote thin clients (mobile) and streams
 * OpenCode SSE events back over the vibecoding host channel.
 */

export interface OpenCodeServer {
  url: string
  password: string
}

export interface OpenCodeBridge {
  start: () => void
  stop: () => void
  handleRequest: (payload: any) => Promise<void>
  status: () => Promise<Record<string, unknown>>
}

type Emit = (msg: Record<string, unknown>) => void

const EVENT_TYPES = [
  'session.text.started',
  'session.text.delta',
  'session.text.ended',
  'session.reasoning.started',
  'session.reasoning.delta',
  'session.reasoning.ended',
  'session.tool.input.started',
  'session.tool.input.ended',
  'session.tool.called',
  'session.tool.success',
  'session.tool.failed',
  'session.execution.started',
  'session.execution.succeeded',
  'session.execution.failed',
  'session.execution.interrupted',
  'session.renamed',
  'session.deleted',
  'session.forked',
  'permission.asked',
]

function eventQuery(): string {
  return EVENT_TYPES.map((type) => `types=${encodeURIComponent(type)}`).join('&')
}

function stateDir(): string {
  if (process.env.XDG_STATE_HOME) return process.env.XDG_STATE_HOME
  if (process.platform === 'win32') {
    return join(process.env.LOCALAPPDATA || join(homedir(), 'AppData', 'Local'), 'opencode')
  }
  return join(homedir(), '.local', 'state', 'opencode')
}

/** Read the service descriptor written by the OpenCode background service. */
export function discoverOpenCode(): OpenCodeServer | null {
  const envUrl = (process.env.OPENCODE_SERVER_URL || '').trim()
  if (envUrl) {
    return {
      url: envUrl.replace(/\/+$/, ''),
      password: process.env.OPENCODE_SERVER_PASSWORD || '',
    }
  }
  const candidates = [
    process.env.OPENCODE_SERVICE_FILE || '',
    join(stateDir(), 'service.json'),
  ].filter(Boolean)
  for (const file of candidates) {
    try {
      if (!existsSync(file)) continue
      const data = JSON.parse(readFileSync(file, 'utf8'))
      const url = String(data?.url || '').trim()
      if (!url) continue
      return { url: url.replace(/\/+$/, ''), password: String(data?.password || '') }
    } catch {
      // Try the next candidate.
    }
  }
  return null
}

let startAttempted = false

/** Best effort: bring up the OpenCode background service when it is not running. */
function ensureService(): Promise<void> {
  if (startAttempted) return Promise.resolve()
  startAttempted = true
  return new Promise((resolvePromise) => {
    const done = () => resolvePromise()
    try {
      const child = exec(
        'opencode service start',
        { timeout: 10_000, windowsHide: true },
        done,
      )
      child.on('error', done)
      setTimeout(done, 10_500)
    } catch {
      done()
    }
  })
}

function authHeaders(server: OpenCodeServer, extra: Record<string, string> = {}) {
  const headers: Record<string, string> = { ...extra }
  if (server.password) {
    const token = Buffer.from(`opencode:${server.password}`).toString('base64')
    headers.Authorization = `Basic ${token}`
  }
  return headers
}

function errorText(error: any): string {
  if (!error) return '未知错误'
  if (typeof error === 'string') return error
  const detail = error?.message || error?.error || ''
  return String(detail || JSON.stringify(error)).slice(0, 400)
}

async function requestJson(
  server: OpenCodeServer,
  method: string,
  path: string,
  body?: unknown,
  timeoutMs = 30_000,
): Promise<any> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(`${server.url}${path}`, {
      method,
      headers: authHeaders(server, {
        Accept: 'application/json',
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      }),
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    })
    const text = await response.text()
    let data: any = null
    if (text) {
      try {
        data = JSON.parse(text)
      } catch {
        data = text
      }
    }
    if (!response.ok) {
      const message =
        (data && typeof data === 'object' && (data.message || data.error)) ||
        (typeof data === 'string' ? data : '') ||
        `HTTP ${response.status}`
      throw new Error(String(message))
    }
    return data
  } finally {
    clearTimeout(timer)
  }
}

function normalizeSession(raw: any, running: boolean) {
  const time = raw?.time || {}
  return {
    id: String(raw?.id || ''),
    title: String(raw?.title || '(未命名会话)'),
    directory: String(raw?.location?.directory || ''),
    project_id: String(raw?.projectID || ''),
    agent: String(raw?.agent || ''),
    model: String(raw?.model?.id || ''),
    provider: String(raw?.model?.providerID || ''),
    outcome: String(raw?.outcome || ''),
    created: Number(time.created || 0),
    updated: Number(time.updated || time.created || 0),
    busy: running || Boolean(time.busy && (!time.idle || time.busy > time.idle)),
  }
}

function summarizeInput(input: any): Record<string, unknown> {
  if (!input || typeof input !== 'object') return {}
  const out: Record<string, unknown> = {}
  for (const key of ['command', 'filePath', 'path', 'pattern', 'description', 'url']) {
    const value = (input as any)[key]
    if (typeof value === 'string' && value) out[key] = value.slice(0, 300)
  }
  if (!Object.keys(out).length) {
    try {
      out.preview = JSON.stringify(input).slice(0, 300)
    } catch {
      // Ignore unserializable input.
    }
  }
  return out
}

function normalizePart(part: any) {
  const type = String(part?.type || '')
  if (type === 'text') {
    return { type: 'text', text: String(part.text || '') }
  }
  if (type === 'reasoning') {
    const text = String(part.text || '')
    return { type: 'reasoning', text: text.length > 4000 ? text.slice(-4000) : text }
  }
  if (type === 'tool') {
    return {
      type: 'tool',
      name: String(part.name || 'tool'),
      status: String(part.state?.status || ''),
      input: summarizeInput(part.state?.input),
      error: part.state?.status === 'failed' ? String(part.state?.error || '') : undefined,
    }
  }
  if (type === 'file') {
    return { type: 'file', name: String(part.name || part.path || 'file') }
  }
  return null
}

function normalizeMessage(raw: any) {
  const time = Number(raw?.time?.created || 0)
  if (raw?.type === 'user') {
    return {
      id: String(raw.id || ''),
      role: 'user',
      time,
      agent: String(raw.agent || ''),
      parts: [{ type: 'text', text: String(raw.text || '') }],
    }
  }
  const parts = (Array.isArray(raw?.content) ? raw.content : [])
    .map(normalizePart)
    .filter(Boolean)
  return {
    id: String(raw?.id || ''),
    role: 'assistant',
    time,
    agent: String(raw?.agent || ''),
    model: String(raw?.model?.id || ''),
    parts,
  }
}

function eventData(name: string, data: any): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  switch (name) {
    case 'session.text.started':
    case 'session.text.ended':
      out.message_id = String(data?.assistantMessageID || '')
      if (name === 'session.text.ended') out.text = String(data?.text || '')
      break
    case 'session.text.delta':
    case 'session.reasoning.delta':
      out.message_id = String(data?.assistantMessageID || '')
      out.delta = String(data?.delta || '')
      break
    case 'session.tool.called':
      out.call_id = String(data?.id || '')
      out.input = summarizeInput(data?.input)
      break
    case 'session.tool.success':
    case 'session.tool.failed':
      out.call_id = String(data?.id || '')
      break
    case 'permission.asked':
      out.title = String(data?.title || data?.permission || '需要确认')
      out.kind = String(data?.type || data?.permission || '')
      break
    default:
      break
  }
  return out
}

export function createOpenCodeBridge(context: any, emit: Emit): OpenCodeBridge {
  let server: OpenCodeServer | null = null
  let configured: { url?: string; password?: string } = {}
  let streamAbort: AbortController | null = null
  let streamTimer: any = null
  let running = false
  let retry = 0
  let lastEventAt = 0
  const busySessions = new Set<string>()

  async function resolveServer(force = false): Promise<OpenCodeServer | null> {
    if (!force && configured.url) {
      return { url: configured.url, password: configured.password || '' }
    }
    try {
      const url = await context.storage.get('opencode_url')
      const password = await context.storage.get('opencode_password')
      if (url) {
        configured = { url: String(url).replace(/\/+$/, ''), password: String(password || '') }
        return { url: configured.url, password: configured.password || '' }
      }
    } catch {
      // Storage is optional.
    }
    configured = {}
    return discoverOpenCode()
  }

  async function withServer(): Promise<OpenCodeServer> {
    let resolved = await resolveServer()
    if (!resolved) {
      await ensureService()
      resolved = await resolveServer(true)
    }
    if (!resolved) {
      throw new Error('未发现 OpenCode 2 服务，请先在电脑上运行 opencode（或 opencode serve）')
    }
    server = resolved
    return resolved
  }

  function scheduleStream(delayMs: number) {
    if (!running) return
    if (streamTimer) clearTimeout(streamTimer)
    streamTimer = setTimeout(() => {
      streamTimer = null
      void openStream()
    }, delayMs)
  }

  async function openStream(): Promise<void> {
    if (!running) return
    const target = await resolveServer().catch(() => null)
    if (!target) {
      scheduleStream(10_000)
      return
    }
    const controller = new AbortController()
    streamAbort = controller
    try {
      const response = await fetch(`${target.url}/api/event?${eventQuery()}`, {
        headers: authHeaders(target, { Accept: 'text/event-stream' }),
        signal: controller.signal,
      })
      if (!response.ok || !response.body) {
        throw new Error(`event stream HTTP ${response.status}`)
      }
      retry = 0
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (running) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let index = buffer.indexOf('\n\n')
        while (index >= 0) {
          const frame = buffer.slice(0, index)
          buffer = buffer.slice(index + 2)
          handleFrame(frame)
          index = buffer.indexOf('\n\n')
        }
      }
      throw new Error('event stream closed')
    } catch (error: any) {
      if (!running) return
      if (controller.signal.aborted) return
      retry = Math.min(retry + 1, 6)
      scheduleStream(Math.min(30_000, 1000 * 2 ** retry))
    } finally {
      if (streamAbort === controller) streamAbort = null
    }
  }

  function handleFrame(frame: string): void {
    if (!frame.trim()) return
    let eventName = ''
    const dataLines: string[] = []
    for (const line of frame.split('\n')) {
      if (line.startsWith('event:')) eventName = line.slice(6).trim()
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
    }
    if (!dataLines.length) return
    let payload: any = null
    try {
      payload = JSON.parse(dataLines.join('\n'))
    } catch {
      return
    }
    const name = String(payload?.type || eventName || '')
    const data = payload?.data || {}
    const sessionId = String(data?.sessionID || '')
    if (!sessionId) return
    lastEventAt = Date.now()

    if (name === 'session.execution.started') busySessions.add(sessionId)
    else if (
      name === 'session.execution.succeeded' ||
      name === 'session.execution.failed' ||
      name === 'session.execution.interrupted'
    ) {
      busySessions.delete(sessionId)
    }

    if (name === 'session.renamed' || name === 'session.deleted' || name === 'session.forked') {
      emit({ type: 'oc.event', session_id: sessionId, event: 'sessions.changed', data: {} })
      return
    }
    if (!name.startsWith('session.') && name !== 'permission.asked') return

    emit({
      type: 'oc.event',
      session_id: sessionId,
      event: name,
      data: eventData(name, data),
      ts: Date.now(),
    })
  }

  async function actionSessionsList(payload: any): Promise<any> {
    const target = await withServer()
    const limit = Math.max(1, Math.min(Number(payload?.limit) || 100, 300))
    const [sessions, active] = await Promise.all([
      requestJson(target, 'GET', `/api/session?limit=${limit}&parentID=null`),
      requestJson(target, 'GET', '/api/session/active').catch(() => null),
    ])
    const runningIds = new Set<string>(
      Object.entries(active?.data || {})
        .filter(([, value]: any) => value?.type === 'running')
        .map(([key]) => key),
    )
    for (const id of busySessions) runningIds.add(id)
    const items = Array.isArray(sessions?.data) ? sessions.data : []
    return {
      sessions: items
        .map((raw: any) => normalizeSession(raw, runningIds.has(String(raw?.id))))
        .filter((s: any) => s.id),
      server: { url: target.url },
    }
  }

  async function actionSessionHistory(payload: any): Promise<any> {
    const target = await withServer()
    const sessionId = String(payload?.session_id || '')
    if (!sessionId) throw new Error('缺少 session_id')
    const limit = Math.max(1, Math.min(Number(payload?.limit) || 60, 200))
    const cursor = String(payload?.cursor || '')
    const query = new URLSearchParams({ limit: String(limit), order: 'desc' })
    if (cursor) {
      query.delete('order')
      query.set('cursor', cursor)
    }
    const response = await requestJson(
      target,
      'GET',
      `/api/session/${encodeURIComponent(sessionId)}/message?${query.toString()}`,
    )
    const items = Array.isArray(response?.data) ? response.data : []
    const messages = items.map(normalizeMessage).filter((m: any) => m.id || m.parts.length)
    messages.reverse()
    return {
      session_id: sessionId,
      messages,
      cursor: response?.cursor?.previous || null,
    }
  }

  async function actionSessionPrompt(payload: any): Promise<any> {
    const target = await withServer()
    const sessionId = String(payload?.session_id || '')
    const text = String(payload?.text || '').trim()
    if (!sessionId) throw new Error('缺少 session_id')
    if (!text) throw new Error('内容不能为空')
    const response = await requestJson(
      target,
      'POST',
      `/api/session/${encodeURIComponent(sessionId)}/prompt`,
      { text },
      60_000,
    )
    busySessions.add(sessionId)
    return { accepted: true, session_id: sessionId, message: response?.data || null }
  }

  async function actionSessionInterrupt(payload: any): Promise<any> {
    const target = await withServer()
    const sessionId = String(payload?.session_id || '')
    if (!sessionId) throw new Error('缺少 session_id')
    await requestJson(
      target,
      'POST',
      `/api/session/${encodeURIComponent(sessionId)}/interrupt`,
      {},
      30_000,
    )
    busySessions.delete(sessionId)
    return { interrupted: true, session_id: sessionId }
  }

  async function handleRequest(payload: any): Promise<void> {
    const requestId = String(payload?.request_id || '')
    const action = String(payload?.action || '')
    const respond = (body: Record<string, unknown>) => {
      emit({
        type: 'oc.response',
        request_id: requestId,
        action,
        machine_id: payload?.machine_id,
        ...body,
      })
    }
    try {
      switch (action) {
        case 'server.status': {
          const target = await withServer()
          const info = await requestJson(target, 'GET', '/api/info').catch(() => null)
          respond({
            ok: true,
            data: {
              connected: true,
              url: target.url,
              version: String(info?.version || ''),
              hostname: String(info?.hostname || ''),
              streaming: Boolean(streamAbort),
              last_event: lastEventAt,
            },
          })
          return
        }
        case 'sessions.list':
          respond({ ok: true, data: await actionSessionsList(payload?.payload || {}) })
          return
        case 'session.history':
          respond({ ok: true, data: await actionSessionHistory(payload?.payload || {}) })
          return
        case 'session.prompt':
          respond({ ok: true, data: await actionSessionPrompt(payload?.payload || {}) })
          return
        case 'session.interrupt':
          respond({ ok: true, data: await actionSessionInterrupt(payload?.payload || {}) })
          return
        default:
          respond({ ok: false, error: `不支持的操作: ${action || '(空)'}` })
      }
    } catch (error: any) {
      respond({ ok: false, error: errorText(error) })
    }
  }

  return {
    start() {
      if (running) return
      running = true
      void resolveServer(true)
      void openStream()
    },
    stop() {
      running = false
      if (streamTimer) clearTimeout(streamTimer)
      streamTimer = null
      try {
        streamAbort?.abort()
      } catch {
        // Ignore abort failures.
      }
      streamAbort = null
    },
    handleRequest,
    async status() {
      const target = await resolveServer().catch(() => null)
      return {
        available: Boolean(target),
        url: target?.url || '',
        streaming: Boolean(streamAbort),
        busy_sessions: Array.from(busySessions),
        last_event: lastEventAt,
      }
    },
  }
}
