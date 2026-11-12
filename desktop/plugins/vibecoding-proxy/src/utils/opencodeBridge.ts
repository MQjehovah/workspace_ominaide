import { exec, execFile } from 'child_process'
import { existsSync, readFileSync } from 'fs'
import { homedir } from 'os'
import { join } from 'path'

/**
 * Bridge to a local OpenCode 2 server.
 *
 * Transport is picked automatically:
 *  1. HTTP + SSE against the background service discovered from service.json.
 *  2. Fallback to `opencode api ...` which discovers the service and handles
 *     authentication itself. This is what makes the bridge work on Windows
 *     where the service file lives in a platform specific directory.
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
  listSessions: (limit?: number) => Promise<any[]>
  createSession: (directory: string, title?: string) => Promise<any>
  deleteSession: (sessionId: string) => Promise<void>
  history: (sessionId: string, limit?: number) => Promise<any>
  prompt: (sessionId: string, text: string) => Promise<any>
  interrupt: (sessionId: string) => Promise<any>
  isBusy: (sessionId: string) => boolean
}

type Emit = (msg: Record<string, unknown>) => void

interface LiveTool {
  id: string
  name: string
  status: string
  detail: string
}

interface LiveState {
  text: string
  messageId: string
  tools: LiveTool[]
  running: boolean
}

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

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** Every place OpenCode 2 may have written its service descriptor. */
export function serviceFileCandidates(): string[] {
  const files: string[] = []
  const push = (value?: string) => {
    if (value) files.push(value)
  }
  push(process.env.OPENCODE_SERVICE_FILE)
  const home = homedir()
  push(
    process.env.XDG_STATE_HOME
      ? join(process.env.XDG_STATE_HOME, 'opencode', 'service.json')
      : '',
  )
  push(join(home, '.local', 'state', 'opencode', 'service.json'))
  if (process.platform === 'win32') {
    const local = process.env.LOCALAPPDATA || join(home, 'AppData', 'Local')
    const roaming = process.env.APPDATA || join(home, 'AppData', 'Roaming')
    push(join(local, 'opencode', 'service.json'))
    push(join(local, 'opencode', 'Data', 'service.json'))
    push(join(roaming, 'opencode', 'service.json'))
    push(join(roaming, 'opencode', 'Data', 'service.json'))
  }
  return [...new Set(files)]
}

function readServiceFile(file: string): OpenCodeServer | null {
  try {
    if (!existsSync(file)) return null
    const data = JSON.parse(readFileSync(file, 'utf8'))
    const url = String(data?.url || '').trim()
    if (!url) return null
    return { url: url.replace(/\/+$/, ''), password: String(data?.password || '') }
  } catch {
    return null
  }
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
  for (const file of serviceFileCandidates()) {
    const target = readServiceFile(file)
    if (target) return target
  }
  return null
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

// -- CLI transport ---------------------------------------------------------

interface CliTarget {
  cmd: string
  shell: boolean
}

let cliTarget: CliTarget | null = null

function execText(command: string, timeout = 10_000): Promise<string> {
  return new Promise((resolve) => {
    try {
      exec(
        command,
        { timeout, windowsHide: true, maxBuffer: 4 * 1024 * 1024 },
        (error, stdout) => resolve(error ? '' : String(stdout)),
      )
    } catch {
      resolve('')
    }
  })
}

function execFileText(
  cmd: string,
  args: string[],
  options: Record<string, unknown> = {},
): Promise<string> {
  return new Promise((resolve, reject) => {
    try {
      execFile(
        cmd,
        args,
        {
          timeout: 90_000,
          windowsHide: true,
          maxBuffer: 32 * 1024 * 1024,
          ...options,
        },
        (error, stdout, stderr) => {
          if (error) {
            const detail = String(stderr || error.message || '').trim()
            reject(new Error(detail.slice(0, 400) || 'opencode CLI failed'))
            return
          }
          resolve(String(stdout))
        },
      )
    } catch (error: any) {
      reject(error)
    }
  })
}

/** Locate a spawnable opencode executable. Prefers a real .exe on Windows. */
async function resolveCli(): Promise<CliTarget> {
  if (cliTarget) return cliTarget
  const configured = (process.env.OPENCODE_BIN || '').trim()
  if (configured) {
    cliTarget = { cmd: configured, shell: false }
    return cliTarget
  }
  if (process.platform !== 'win32') {
    cliTarget = { cmd: 'opencode', shell: false }
    return cliTarget
  }
  const located = await execText('where opencode')
  const lines = located
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
  const exe = lines.find((line) => /\.exe$/i.test(line))
  if (exe && existsSync(exe)) {
    cliTarget = { cmd: exe, shell: false }
    return cliTarget
  }
  const appData = process.env.APPDATA || ''
  const localAppData = process.env.LOCALAPPDATA || ''
  const guesses = [
    appData && join(appData, 'npm', 'node_modules', '@opencode', 'cli', 'bin', 'opencode.exe'),
    appData && join(appData, 'npm', 'node_modules', '@opencode', 'cli-win32-x64', 'bin', 'opencode.exe'),
    appData && join(appData, 'npm', 'node_modules', '@opencode', 'cli-win32-arm64', 'bin', 'opencode.exe'),
    localAppData && join(localAppData, 'Programs', 'opencode', 'opencode.exe'),
    localAppData && join(localAppData, 'opencode', 'bin', 'opencode.exe'),
  ].filter((value): value is string => Boolean(value))
  for (const guess of guesses) {
    if (existsSync(guess)) {
      cliTarget = { cmd: guess, shell: false }
      return cliTarget
    }
  }
  // Last resort: the npm shim. Reads still work, JSON bodies may not.
  cliTarget = { cmd: 'opencode', shell: true }
  return cliTarget
}

async function cliApi(
  method: string,
  path: string,
  body?: unknown,
): Promise<any> {
  const target = await resolveCli()
  const args = ['api', method, path]
  if (body !== undefined) args.push('-d', JSON.stringify(body))
  const output = await execFileText(target.cmd, args, { shell: target.shell })
  const text = output.trim()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

// -- normalization ---------------------------------------------------------

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
      out.message_id = String(data?.assistantMessageID || data?.message_id || '')
      if (name === 'session.text.ended') out.text = String(data?.text || '')
      break
    case 'session.text.delta':
    case 'session.reasoning.delta':
      out.message_id = String(data?.assistantMessageID || data?.message_id || '')
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
  let serverAt = 0
  let configured: { url?: string; password?: string } = {}
  let streamAbort: AbortController | null = null
  let streamTimer: any = null
  let running = false
  let retry = 0
  let lastEventAt = 0
  let lastStartAt = 0
  let startAttempted = false
  const busySessions = new Set<string>()
  const live = new Map<string, LiveState>()
  const polls = new Map<string, { timer: any; msgId: string; text: string; idle: number }>()

  function cacheServer(target: OpenCodeServer): OpenCodeServer {
    server = target
    serverAt = Date.now()
    return target
  }

  async function probeServer(target: OpenCodeServer): Promise<boolean> {
    try {
      const info = await requestJson(target, 'GET', '/api/info', undefined, 2500)
      return typeof info?.version === 'string'
    } catch {
      return false
    }
  }

  /** Try to bring up the OpenCode background service (rate limited). */
  async function ensureService(): Promise<void> {
    const now = Date.now()
    if (startAttempted && now - lastStartAt < 60_000) return
    startAttempted = true
    lastStartAt = now
    const cli = await resolveCli()
    await execFileText(cli.cmd, ['service', 'start'], {
      shell: cli.shell,
      timeout: 25_000,
    }).catch(() => '')
    await sleep(1200)
  }

  async function resolveServer(force = false): Promise<OpenCodeServer | null> {
    if (!force && configured.url) {
      return { url: configured.url, password: configured.password || '' }
    }
    if (!force && server && Date.now() - serverAt < 45_000) return server
    try {
      const url = await context.storage.get('opencode_url')
      const password = await context.storage.get('opencode_password')
      if (url) {
        configured = {
          url: String(url).replace(/\/+$/, ''),
          password: String(password || ''),
        }
        return { url: configured.url, password: configured.password || '' }
      }
    } catch {
      // Storage is optional.
    }
    configured = {}
    server = null

    const scan = async (): Promise<OpenCodeServer | null> => {
      for (const file of serviceFileCandidates()) {
        const target = readServiceFile(file)
        if (!target) continue
        if (await probeServer(target)) return cacheServer(target)
      }
      return null
    }

    const found = await scan()
    if (found) return found
    await ensureService()
    return scan()
  }

  /** Route a request through HTTP when possible, otherwise through the CLI. */
  async function apiJson(
    method: string,
    path: string,
    body?: unknown,
    timeout = 30_000,
  ): Promise<any> {
    const target = await resolveServer()
    if (target) {
      try {
        return await requestJson(target, method, path, body, timeout)
      } catch (error: any) {
        const message = errorText(error)
        if (/fetch failed|ECONNREFUSED|ECONNRESET|aborted|timed out|HTTP 502/i.test(message)) {
          server = null
          serverAt = 0
          const retried = await resolveServer(true)
          if (retried) {
            try {
              return await requestJson(retried, method, path, body, timeout)
            } catch {
              // Fall through to the CLI below.
            }
          }
        } else {
          throw error
        }
      }
    }
    return cliApi(method, path, body)
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
    } catch {
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

    const state =
      live.get(sessionId) ||
      ({ text: '', messageId: '', tools: [], running: false } as LiveState)
    live.set(sessionId, state)
    if (name === 'session.execution.started') {
      state.running = true
      state.text = ''
      state.messageId = ''
      state.tools = []
    } else if (name === 'session.text.started') {
      state.running = true
      state.messageId = String(data?.assistantMessageID || '')
      state.text = ''
    } else if (name === 'session.text.delta') {
      state.running = true
      if (!state.messageId) {
        state.messageId = String(data?.assistantMessageID || '')
      }
      state.text += String(data?.delta || '')
    } else if (name === 'session.text.ended') {
      const finalText = String(data?.text || '')
      if (finalText) state.text = finalText
    } else if (name === 'session.tool.called') {
      state.running = true
      const input = summarizeInput(data?.input)
      const detail =
        String(
          input.command || input.filePath || input.path || input.preview || '',
        )
          .split('\n')[0]
          .slice(0, 100)
      state.tools.push({
        id: String(data?.id || ''),
        name: '工具调用',
        status: 'running',
        detail,
      })
    } else if (name === 'session.tool.success' || name === 'session.tool.failed') {
      const callId = String(data?.id || '')
      const tool = state.tools.find((item) => item.id === callId)
      if (tool) {
        tool.status = name === 'session.tool.success' ? 'success' : 'failed'
      }
    } else if (
      name === 'session.execution.succeeded' ||
      name === 'session.execution.failed' ||
      name === 'session.execution.interrupted'
    ) {
      state.running = false
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

  // -- CLI-mode streaming: poll the message list and emit text deltas ------

  function stopPolling(sessionId: string): void {
    const state = polls.get(sessionId)
    if (!state) return
    clearTimeout(state.timer)
    polls.delete(sessionId)
  }

  function emitEvent(sessionId: string, event: string, data: Record<string, unknown>) {
    emit({
      type: 'oc.event',
      session_id: sessionId,
      event,
      data,
      ts: Date.now(),
    })
  }

  function startPolling(sessionId: string): void {
    if (polls.has(sessionId)) return
    const state = { timer: null as any, msgId: '', text: '', idle: 0 }
    polls.set(sessionId, state)

    const tick = async () => {
      if (!polls.has(sessionId)) return
      try {
        const response = await apiJson(
          'GET',
          `/api/session/${encodeURIComponent(sessionId)}/message?limit=6&order=desc`,
          undefined,
          20_000,
        )
        const items = Array.isArray(response?.data) ? response.data : []
        const latest = items.find((item: any) => item?.type === 'assistant')
        if (latest) {
          if (String(latest.id) !== state.msgId) {
            state.msgId = String(latest.id)
            state.text = ''
            emitEvent(sessionId, 'session.text.started', { message_id: state.msgId })
          }
          const text = (Array.isArray(latest.content) ? latest.content : [])
            .filter((part: any) => part?.type === 'text')
            .map((part: any) => String(part.text || ''))
            .join('\n\n')
          if (text.length > state.text.length && text.startsWith(state.text)) {
            const delta = text.slice(state.text.length)
            state.text = text
            emitEvent(sessionId, 'session.text.delta', {
              message_id: state.msgId,
              delta,
            })
          } else if (text !== state.text) {
            state.text = text
            emitEvent(sessionId, 'session.text.ended', {
              message_id: state.msgId,
              text,
            })
          }
          if (latest.time?.completed) {
            if (state.text) {
              emitEvent(sessionId, 'session.text.ended', {
                message_id: state.msgId,
                text: state.text,
              })
            }
            busySessions.delete(sessionId)
            emitEvent(sessionId, 'session.execution.succeeded', {})
            stopPolling(sessionId)
            return
          }
        }
        const active = await apiJson('GET', '/api/session/active', undefined, 15_000)
        const isRunning = String(active?.data?.[sessionId]?.type || '') === 'running'
        if (isRunning) {
          state.idle = 0
        } else {
          state.idle += 1
          if (state.idle >= 2) {
            if (state.text) {
              emitEvent(sessionId, 'session.text.ended', {
                message_id: state.msgId,
                text: state.text,
              })
            }
            busySessions.delete(sessionId)
            emitEvent(sessionId, 'session.execution.succeeded', {})
            stopPolling(sessionId)
            return
          }
        }
      } catch {
        state.idle += 1
        if (state.idle > 12) {
          stopPolling(sessionId)
          return
        }
      }
      state.timer = setTimeout(tick, 900)
    }
    state.timer = setTimeout(tick, 800)
  }

  // -- actions -------------------------------------------------------------

  async function actionSessionsList(payload: any): Promise<any> {
    const limit = Math.max(1, Math.min(Number(payload?.limit) || 100, 300))
    const [sessions, active] = await Promise.all([
      apiJson('GET', `/api/session?limit=${limit}&parentID=null`),
      apiJson('GET', '/api/session/active').catch(() => null),
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
        .filter((value: any) => value.id),
      server: { mode: server ? 'http' : 'cli', url: server?.url || '' },
    }
  }

  async function actionSessionHistory(payload: any): Promise<any> {
    const sessionId = String(payload?.session_id || '')
    if (!sessionId) throw new Error('缺少 session_id')
    const limit = Math.max(1, Math.min(Number(payload?.limit) || 60, 200))
    const cursor = String(payload?.cursor || '')
    const query = new URLSearchParams({ limit: String(limit), order: 'desc' })
    if (cursor) {
      query.delete('order')
      query.set('cursor', cursor)
    }
    const response = await apiJson(
      'GET',
      `/api/session/${encodeURIComponent(sessionId)}/message?${query.toString()}`,
    )
    const items = Array.isArray(response?.data) ? response.data : []
    const messages = items
      .map(normalizeMessage)
      .filter((m: any) => m.id || m.parts.length)
      .map((message: any) => {
        const parts = Array.isArray(message.parts) ? message.parts : []
        const text = parts
          .filter((part: any) => part.type === 'text')
          .map((part: any) => part.text)
          .join('\n\n')
        const tools = parts
          .filter((part: any) => part.type === 'tool')
          .map((part: any) => {
            const icon =
              part.status === 'running'
                ? '⏳'
                : part.status === 'failed'
                  ? '✗'
                  : part.status === 'completed' || part.status === 'success'
                    ? '✓'
                    : '🛠'
            const detail =
              part.input?.command ||
              part.input?.filePath ||
              part.input?.path ||
              part.input?.preview ||
              ''
            const suffix = detail
              ? `: ${String(detail).split('\n')[0].slice(0, 100)}`
              : ''
            return `${icon} ${part.name}${suffix}`
          })
        return { ...message, text, tools }
      })
    messages.reverse()
    const state = live.get(sessionId)
    return {
      session_id: sessionId,
      messages,
      cursor: response?.cursor?.previous || null,
      running: busySessions.has(sessionId) || !!state?.running,
      streaming: state?.text || '',
      streaming_id: state?.messageId || '',
      live_tools: state?.tools || [],
    }
  }

  async function actionSessionPrompt(payload: any): Promise<any> {
    const sessionId = String(payload?.session_id || '')
    const text = String(payload?.text || '').trim()
    if (!sessionId) throw new Error('缺少 session_id')
    if (!text) throw new Error('内容不能为空')
    const response = await apiJson(
      'POST',
      `/api/session/${encodeURIComponent(sessionId)}/prompt`,
      { text },
      60_000,
    )
    busySessions.add(sessionId)
    live.set(sessionId, { text: '', messageId: '', tools: [], running: true })
    if (!streamAbort) {
      emitEvent(sessionId, 'session.execution.started', {})
      startPolling(sessionId)
    }
    return { accepted: true, session_id: sessionId, message: response?.data || null }
  }

  async function actionSessionInterrupt(payload: any): Promise<any> {
    const sessionId = String(payload?.session_id || '')
    if (!sessionId) throw new Error('缺少 session_id')
    await apiJson(
      'POST',
      `/api/session/${encodeURIComponent(sessionId)}/interrupt`,
      {},
      30_000,
    )
    busySessions.delete(sessionId)
    stopPolling(sessionId)
    return { interrupted: true, session_id: sessionId }
  }

  async function actionSessionDelete(payload: any): Promise<any> {
    const sessionId = String(payload?.session_id || '')
    if (!sessionId) throw new Error('缺少 session_id')
    await apiJson(
      'DELETE',
      `/api/session/${encodeURIComponent(sessionId)}`,
      undefined,
      30_000,
    )
    busySessions.delete(sessionId)
    stopPolling(sessionId)
    return { deleted: true, session_id: sessionId }
  }

  async function actionSessionCreate(payload: any): Promise<any> {
    const directory = String(payload?.directory || payload?.project || '').trim()
    if (!directory) throw new Error('缺少项目目录')
    const title = String(payload?.title || '').trim()
    const body: Record<string, unknown> = { location: { directory } }
    if (title) body.title = title
    const created = await apiJson('POST', '/api/session', body, 45_000)
    const raw = created?.data && typeof created.data === 'object' ? created.data : created
    if (!raw?.id) throw new Error('创建会话失败')

    // New sessions fall back to the global default model, which may point at a
    // provider without credentials. Inherit the model of the newest session.
    try {
      const list = await apiJson('GET', '/api/session?limit=5&parentID=null')
      const donor = (list?.data || []).find(
        (item: any) => item?.model?.providerID && item?.model?.id,
      )
      if (donor) {
        const model: Record<string, unknown> = {
          providerID: donor.model.providerID,
          id: donor.model.id,
        }
        if (donor.model.variant) model.variant = donor.model.variant
        await apiJson(
          'POST',
          `/api/session/${encodeURIComponent(raw.id)}/model`,
          { model },
          20_000,
        ).catch(() => null)
        if (!raw.model) raw.model = donor.model
      }
    } catch {
      // Model inheritance is best effort.
    }
    return { session: normalizeSession(raw, false) }
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
          const checks = serviceFileCandidates().map((file) => ({
            file,
            exists: existsSync(file),
          }))
          const target = await resolveServer()
          if (target) {
            const info = await requestJson(target, 'GET', '/api/info').catch(() => null)
            respond({
              ok: true,
              data: {
                connected: true,
                mode: 'http',
                url: target.url,
                version: String(info?.version || ''),
                hostname: String(info?.hostname || ''),
                streaming: Boolean(streamAbort),
                last_event: lastEventAt,
                checks,
              },
            })
            return
          }
          try {
            const info = await cliApi('GET', '/api/info')
            respond({
              ok: true,
              data: {
                connected: true,
                mode: 'cli',
                url: String(info?.urls?.[0] || ''),
                version: String(info?.version || ''),
                hostname: String(info?.hostname || ''),
                streaming: false,
                last_event: lastEventAt,
                checks,
              },
            })
          } catch (error) {
            respond({
              ok: true,
              data: {
                connected: false,
                mode: 'none',
                error: errorText(error),
                checks,
              },
            })
          }
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
        case 'session.create':
          respond({ ok: true, data: await actionSessionCreate(payload?.payload || {}) })
          return
        case 'session.delete':
          respond({ ok: true, data: await actionSessionDelete(payload?.payload || {}) })
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
      for (const sessionId of Array.from(polls.keys())) stopPolling(sessionId)
      try {
        streamAbort?.abort()
      } catch {
        // Ignore abort failures.
      }
      streamAbort = null
    },
    handleRequest,
    async listSessions(limit = 100) {
      const data = await actionSessionsList({ limit })
      return data.sessions || []
    },
    async createSession(directory: string, title?: string) {
      const data = await actionSessionCreate({ directory, title })
      return data.session
    },
    async deleteSession(sessionId: string) {
      await actionSessionDelete({ session_id: sessionId })
    },
    history(sessionId: string, limit = 100) {
      return actionSessionHistory({ session_id: sessionId, limit })
    },
    prompt(sessionId: string, text: string) {
      return actionSessionPrompt({ session_id: sessionId, text })
    },
    interrupt(sessionId: string) {
      return actionSessionInterrupt({ session_id: sessionId })
    },
    isBusy(sessionId: string) {
      return busySessions.has(sessionId) || Boolean(polls.get(sessionId))
    },
    async status() {
      const target = await resolveServer().catch(() => null)
      return {
        available: Boolean(target),
        mode: target ? 'http' : 'cli',
        url: target?.url || '',
        streaming: Boolean(streamAbort),
        busy_sessions: Array.from(busySessions),
        last_event: lastEventAt,
      }
    },
  }
}
