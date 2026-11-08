import { channelSend, setChannelOpenHandler } from './backendChannel'
import { callProxyTool, listProxyTools } from './mcp/mcp-manager'
import { writeLog } from './logger'

let started = false
let sending: Promise<void> | null = null

export async function sendLocalMcpTools(): Promise<void> {
  if (sending) return sending
  sending = (async () => {
    try {
      const tools = await listProxyTools()
      channelSend('local-mcp', { type: 'tools', tools })
      writeLog('system', 'info', `local MCP tools advertised: ${tools.length}`)
    } catch (err: any) {
      writeLog('system', 'warn', `local MCP discover failed: ${err?.message || err}`)
    } finally {
      sending = null
    }
  })()
  return sending
}

export function initLocalMcpProxy(): void {
  if (started) return
  started = true
  setChannelOpenHandler(() => {
    sendLocalMcpTools().catch(() => {})
  })
  // The host may already be connected; queued sends are flushed on reconnect.
  sendLocalMcpTools().catch(() => {})
}

export async function handleLocalMcpMessage(msg: any): Promise<void> {
  if (msg?.type !== 'call') return
  const callId = String(msg?.call_id || '')
  if (!callId) return
  const serverId = String(msg?.server_id || '')
  const tool = String(msg?.tool || '')
  const args = msg?.args && typeof msg.args === 'object' ? msg.args : {}
  try {
    const result = await callProxyTool(serverId, tool, args)
    channelSend('local-mcp', {
      type: 'result',
      call_id: callId,
      ok: !result.error,
      content: result.content,
      is_error: result.error,
    })
  } catch (err: any) {
    channelSend('local-mcp', {
      type: 'result',
      call_id: callId,
      ok: false,
      error: err?.message || String(err),
    })
  }
}
