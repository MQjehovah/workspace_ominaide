import { z } from 'zod'
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js'
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js'
import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { getConfig } from '../config'

export const BACKEND_SERVER_ID = 'backend'

export interface BackendClientHandle {
  client: Client
  server: McpServer
  transports: [InMemoryTransport, InMemoryTransport]
  tools: { name: string; description: string; inputSchema: any }[]
}

async function fetchBackend(path: string, init?: RequestInit): Promise<Response> {
  const cfg = await getConfig()
  const base = String(cfg.serverUrl || 'http://localhost:8000').replace(/\/+$/, '')
  const token = cfg.token || ''
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string>) || {} }
  headers['Content-Type'] = 'application/json'
  if (token) headers['Authorization'] = 'Bearer ' + token
  return fetch(`${base}${path}`, { ...init, headers, signal: AbortSignal.timeout(30000) })
}

function toJsonSchema(inputSchema: any): Record<string, any> {
  if (!inputSchema || typeof inputSchema !== 'object') {
    return { type: 'object', properties: {} }
  }
  const props = inputSchema.properties || {}
  const zodShape: Record<string, any> = {}
  for (const [name, def] of Object.entries<any>(props)) {
    const t = def?.type
    if (t === 'string') zodShape[name] = z.string().optional().describe(def?.description || '')
    else if (t === 'integer' || t === 'number') zodShape[name] = z.number().optional().describe(def?.description || '')
    else if (t === 'boolean') zodShape[name] = z.boolean().optional().describe(def?.description || '')
    else zodShape[name] = z.any().optional().describe(def?.description || '')
  }
  return zodShape
}

async function createBackendMcpServer(): Promise<{ server: McpServer; tools: { name: string; description: string; inputSchema: any }[] }> {
  const server = new McpServer({ name: 'omniaide-backend', version: '1.0.0' })
  let tools: { name: string; description: string; inputSchema: any }[] = []
  try {
    const res = await fetchBackend('/api/mcp/tools')
    if (res.ok) {
      const j = await res.json()
      tools = (j.tools || []).filter((t: any) => t && t.name)
    } else {
      console.error('[backend-mcp] fetch tools failed:', res.status)
    }
  } catch (e: any) {
    console.error('[backend-mcp] fetch tools error:', e?.message || e)
  }

  for (const t of tools) {
    server.registerTool(
      t.name,
      {
        title: t.name,
        description: `[后端] ${t.description || t.name}`,
        inputSchema: toJsonSchema(t.inputSchema),
      },
      async (args: any) => {
        try {
          const res = await fetchBackend('/api/mcp/call', {
            method: 'POST',
            body: JSON.stringify({ name: t.name, arguments: args || {} }),
          })
          if (!res.ok) {
            const errText = await res.text().catch(() => '')
            return { content: [{ type: 'text', text: `后端调用失败 (${res.status}): ${errText.slice(0, 300)}` }], isError: true }
          }
          const j = await res.json()
          const blocks: any[] = j?.content || []
          const text = blocks.map((b: any) => b?.text || (b?.resource?.text ?? '') || '').filter(Boolean).join('\n')
          if (j?.isError) return { content: [{ type: 'text', text: text || '后端工具执行出错' }], isError: true }
          return { content: [{ type: 'text', text: text || JSON.stringify(j) }] }
        } catch (e: any) {
          return { content: [{ type: 'text', text: `后端调用异常: ${e?.message || e}` }], isError: true }
        }
      }
    )
  }
  return { server, tools }
}

export async function createBackendClient(): Promise<BackendClientHandle> {
  const { server, tools } = await createBackendMcpServer()
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair()
  const client = new Client({ name: 'omniaide-assistant', version: '1.0.0' })
  await Promise.all([
    client.connect(clientTransport),
    server.connect(serverTransport),
  ])
  return { client, server, transports: [clientTransport, serverTransport], tools }
}

export async function closeBackendClient(handle: BackendClientHandle): Promise<void> {
  try { await handle.client.close() } catch { /* ignore */ }
  try { await handle.server.close() } catch { /* ignore */ }
}
