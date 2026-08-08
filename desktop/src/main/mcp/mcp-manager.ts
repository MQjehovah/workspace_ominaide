import { app } from 'electron'
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'fs'
import { join } from 'path'
import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js'
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js'
import { listLocalTools, callLocalTool } from './local-tools'
import { createOfficeClient, closeOfficeClient, OFFICE_SERVER_ID, type OfficeClientHandle } from './office-mcp'
import { createBackendClient, closeBackendClient, BACKEND_SERVER_ID, type BackendClientHandle } from './backend-mcp'

export interface McpServerConfig {
  id: string
  name: string
  transport: 'stdio' | 'http' | 'internal'
  command?: string
  args?: string[]
  env?: Record<string, string>
  url?: string
  headers?: Record<string, string>
  enabled: boolean
}

interface ConnInfo {
  client: Client
  transport: any
  server: McpServerConfig
  error?: string
  failedAt?: number
}

const FILE = () => join(app.getPath('userData'), 'mcp-servers.json')
const TOOL_SEP = '__'
const FAIL_COOLDOWN = 30000

let servers: McpServerConfig[] = []
let conns = new Map<string, ConnInfo>()
let toolsCache: { name: string; description: string; inputSchema: any; serverId: string }[] | null = null
let officeHandle: OfficeClientHandle | null = null
let backendHandle: BackendClientHandle | null = null

function officeServerInfo(): McpServerConfig {
  return { id: OFFICE_SERVER_ID, name: 'Office 文档', transport: 'internal', enabled: true }
}

function backendServerInfo(): McpServerConfig {
  return { id: BACKEND_SERVER_ID, name: '后端服务', transport: 'internal', enabled: true }
}

async function ensureOffice(): Promise<OfficeClientHandle> {
  if (officeHandle) return officeHandle
  officeHandle = await createOfficeClient()
  return officeHandle
}

async function ensureBackend(): Promise<BackendClientHandle> {
  if (backendHandle) return backendHandle
  backendHandle = await createBackendClient()
  return backendHandle
}

function load() {
  try {
    const raw = readFileSync(FILE(), 'utf-8').replace(/^\uFEFF/, '')
    servers = (JSON.parse(raw).servers || []).filter((s: any) => s && s.id)
  } catch {
    servers = []
  }
}

function save() {
  try {
    mkdirSync(join(app.getPath('userData')), { recursive: true })
    writeFileSync(FILE(), JSON.stringify({ servers }, null, 2), 'utf-8')
  } catch (e) {
    console.error('[mcp] save failed:', e)
  }
}

function winStdio(command: string, args: string[]): { command: string; args: string[] } {
  if (process.platform === 'win32' && !/\.(exe|cmd|bat|ps1)$/i.test(command) && !/[/\\]/.test(command)) {
    return { command: 'cmd.exe', args: ['/c', command, ...args] }
  }
  return { command, args }
}

function makeTransport(s: McpServerConfig) {
  if (s.transport === 'http') {
    if (!s.url) throw new Error('HTTP MCP 服务器缺少 URL')
    return new StreamableHTTPClientTransport(new URL(s.url), {
      requestInit: {
        headers: s.headers && Object.keys(s.headers).length ? { ...s.headers } : undefined,
      },
    })
  }
  const cmd = s.command || 'npx'
  const args = s.args || []
  const fixed = winStdio(cmd, args)
  return new StdioClientTransport({
    command: fixed.command,
    args: fixed.args,
    env: s.env && Object.keys(s.env).length ? { ...process.env, ...s.env } : undefined,
    cwd: process.cwd(),
    stderr: 'pipe',
  } as any)
}

async function connectServer(s: McpServerConfig): Promise<ConnInfo> {
  const existing = conns.get(s.id)
  if (existing && !existing.error) return existing
  if (existing && existing.error && existing.failedAt && Date.now() - existing.failedAt < FAIL_COOLDOWN) {
    throw new Error(existing.error)
  }
  const client = new Client({ name: 'omniaide-assistant', version: '1.0.0' })
  const transport = makeTransport(s)
  const timer = new Promise<never>((_, rej) => setTimeout(() => rej(new Error('连接超时 (10s)')), 10000))
  try {
    await Promise.race([client.connect(transport), timer])
    const info: ConnInfo = { client, transport, server: s }
    conns.set(s.id, info)
    toolsCache = null
    return info
  } catch (e: any) {
    conns.set(s.id, { client, transport, server: s, error: e?.message || String(e), failedAt: Date.now() })
    throw e
  }
}

async function disconnect(id: string) {
  const info = conns.get(id)
  if (!info) return
  try { await info.client.close() } catch { /* ignore */ }
  conns.delete(id)
  toolsCache = null
}

export function getServers(): McpServerConfig[] {
  const out = servers.map(s => ({ ...s }))
  out.push(officeServerInfo())
  out.push(backendServerInfo())
  return out
}

export function addServer(cfg: Omit<McpServerConfig, 'enabled'> & { enabled?: boolean }): McpServerConfig {
  if (servers.some(s => s.id === cfg.id)) throw new Error(`服务器 "${cfg.id}" 已存在`)
  const server: McpServerConfig = { ...cfg, enabled: cfg.enabled !== false } as McpServerConfig
  servers.push(server)
  save()
  return { ...server }
}

export function updateServer(id: string, patch: Partial<McpServerConfig>): McpServerConfig {
  const idx = servers.findIndex(s => s.id === id)
  if (idx < 0) throw new Error('服务器不存在')
  servers[idx] = { ...servers[idx], ...patch, id }
  save()
  if (patch.command !== undefined || patch.args !== undefined || patch.url !== undefined) {
    disconnect(id).catch(() => {})
  }
  return { ...servers[idx] }
}

export async function removeServer(id: string) {
  await disconnect(id)
  servers = servers.filter(s => s.id !== id)
  save()
}

export const LOCAL_SERVER_ID = '__local__'

export async function listTools(): Promise<{ name: string; description: string; inputSchema: any; serverId: string }[]> {
  if (toolsCache) return toolsCache
  const out: { name: string; description: string; inputSchema: any; serverId: string }[] = []
  for (const t of listLocalTools()) {
    out.push({ ...t, serverId: LOCAL_SERVER_ID })
  }
  try {
    const office = await ensureOffice()
    const officeResult = await office.client.listTools()
    for (const t of officeResult.tools) {
      out.push({
        name: `${OFFICE_SERVER_ID}${TOOL_SEP}${t.name}`,
        description: `[Office] ${t.description || t.name}`,
        inputSchema: (t as any).inputSchema || { type: 'object', properties: {} },
        serverId: OFFICE_SERVER_ID,
      })
    }
  } catch (e: any) {
    console.error('[mcp] office server init failed:', e?.message || e)
  }
  try {
    const backend = await ensureBackend()
    for (const t of backend.tools) {
      out.push({
        name: `${BACKEND_SERVER_ID}${TOOL_SEP}${t.name}`,
        description: `[后端] ${t.description || t.name}`,
        inputSchema: t.inputSchema || { type: 'object', properties: {} },
        serverId: BACKEND_SERVER_ID,
      })
    }
  } catch (e: any) {
    console.error('[mcp] backend server init failed:', e?.message || e)
  }
  for (const s of servers) {
    if (!s.enabled) continue
    try {
      const info = await connectServer(s)
      const result = await info.client.listTools()
      for (const t of result.tools) {
        out.push({
          name: `${s.id}${TOOL_SEP}${t.name}`,
          description: `[${s.name}] ${t.description || t.name}`,
          inputSchema: (t as any).inputSchema || { type: 'object', properties: {} },
          serverId: s.id,
        })
      }
    } catch (e: any) {
      const info = conns.get(s.id)
      if (info) info.error = e?.message || String(e)
    }
  }
  toolsCache = out
  return out
}

export function getServerStatus(id: string): { connected: boolean; error?: string; tools: number } {
  if (id === OFFICE_SERVER_ID) {
    const toolCount = toolsCache
      ? toolsCache.filter(t => t.serverId === OFFICE_SERVER_ID).length
      : 0
    return { connected: !!officeHandle, tools: toolCount }
  }
  if (id === BACKEND_SERVER_ID) {
    const toolCount = toolsCache
      ? toolsCache.filter(t => t.serverId === BACKEND_SERVER_ID).length
      : 0
    return { connected: !!backendHandle, tools: toolCount }
  }
  const info = conns.get(id)
  if (!info) return { connected: false, tools: 0 }
  const toolCount = toolsCache
    ? toolsCache.filter(t => t.serverId === id).length
    : 0
  return { connected: !info.error, error: info.error, tools: toolCount }
}

export async function refresh() {
  for (const s of servers) {
    await disconnect(s.id).catch(() => {})
  }
  toolsCache = null
  await listTools()
}

export async function callTool(name: string, args: any): Promise<{ content: string; error: boolean }> {
  const sepIdx = name.indexOf(TOOL_SEP)
  if (sepIdx < 0) {
    // local built-in tool
    const localNames = listLocalTools().map(t => t.name)
    if (localNames.includes(name)) {
      const content = await callLocalTool(name, args)
      return { content, error: content.startsWith('本地工具') && content.includes('出错') }
    }
    return { content: `未知工具: ${name}`, error: true }
  }
  const serverId = name.slice(0, sepIdx)
  const toolName = name.slice(sepIdx + TOOL_SEP.length)
  if (serverId === LOCAL_SERVER_ID) {
    const content = await callLocalTool(toolName, args)
    return { content, error: content.startsWith('本地工具') && content.includes('出错') }
  }
  if (serverId === OFFICE_SERVER_ID) {
    try {
      const office = await ensureOffice()
      const res = await office.client.callTool({ name: toolName, arguments: args || {} })
      const blocks: any[] = (res as any).content || []
      let text = ''
      for (const c of blocks) {
        if (c && c.type === 'text' && c.text) text += (text ? '\n' : '') + c.text
        else if (c && c.type === 'resource' && c.resource?.text) text += (text ? '\n' : '') + c.resource.text
      }
      if (res.isError) return { content: text || '工具执行出错', error: true }
      return { content: text, error: false }
    } catch (e: any) {
      return { content: `Office 工具调用失败: ${e?.message || e}`, error: true }
    }
  }
  if (serverId === BACKEND_SERVER_ID) {
    try {
      const backend = await ensureBackend()
      const res = await backend.client.callTool({ name: toolName, arguments: args || {} })
      const blocks: any[] = (res as any).content || []
      let text = ''
      for (const c of blocks) {
        if (c && c.type === 'text' && c.text) text += (text ? '\n' : '') + c.text
        else if (c && c.type === 'resource' && c.resource?.text) text += (text ? '\n' : '') + c.resource.text
      }
      if (res.isError) return { content: text || '后端工具执行出错', error: true }
      return { content: text, error: false }
    } catch (e: any) {
      return { content: `后端工具调用失败: ${e?.message || e}`, error: true }
    }
  }
  const s = servers.find(x => x.id === serverId)
  if (!s) return { content: `服务器不存在: ${serverId}`, error: true }
  try {
    const info = await connectServer(s)
    const res = await info.client.callTool({ name: toolName, arguments: args || {} })
    const blocks: any[] = (res as any).content || []
    let text = ''
    for (const c of blocks) {
      if (c && c.type === 'text' && c.text) text += (text ? '\n' : '') + c.text
      else if (c && c.type === 'resource' && c.resource?.text) text += (text ? '\n' : '') + c.resource.text
    }
    if (res.isError) return { content: text || '工具执行出错', error: true }
    return { content: text, error: false }
  } catch (e: any) {
    return { content: `调用失败: ${e?.message || e}`, error: true }
  }
}

export async function disposeAll() {
  for (const id of [...conns.keys()]) {
    await disconnect(id).catch(() => {})
  }
  if (officeHandle) {
    await closeOfficeClient(officeHandle).catch(() => {})
    officeHandle = null
  }
  if (backendHandle) {
    await closeBackendClient(backendHandle).catch(() => {})
    backendHandle = null
  }
}

export function initMcpManager() {
  load()
}
