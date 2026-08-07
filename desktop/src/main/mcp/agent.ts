import { listTools, callTool } from './mcp-manager'
import { getEnabledInstructions } from './skills'

export interface AgentRequest {
  sessionId: string
  message: string
  history: { role: string; content: string }[]
  images?: string[]
  llm: { baseUrl: string; apiKey: string; model: string; temperature?: number; maxTokens?: number }
  maxTurns?: number
  maxContextChars?: number
}

export interface AgentRunOptions {
  maxTurns?: number
  temperature?: number
  maxTokens?: number
  maxContextChars?: number
}

export type AgentPayload =
  | { sessionId: string; type: 'token'; content: string }
  | { sessionId: string; type: 'reasoning'; content: string }
  | { sessionId: string; type: 'tool_call'; name: string; arguments: any }
  | { sessionId: string; type: 'tool_result'; name: string; content: string; error: boolean }
  | { sessionId: string; type: 'tools_ready'; count: number; names: string[] }
  | { sessionId: string; type: 'usage'; chars: number; tools: number }
  | { sessionId: string; type: 'done' }
  | { sessionId: string; type: 'error'; content: string }

const MAX_TURNS = 20
const MAX_RESULT_CHARS = 12000
const MAX_CONTEXT_CHARS = 120000

function normalizeBase(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, '')
}

function truncate(s: string, max = MAX_RESULT_CHARS): string {
  if (!s || s.length <= max) return s
  const head = s.slice(0, Math.floor(max * 0.8))
  const tail = s.slice(s.length - Math.floor(max * 0.2))
  return `${head}\n\n…[内容过长已截断,共 ${s.length} 字符]…\n\n${tail}`
}

function countChars(msg: any): number {
  if (typeof msg?.content === 'string') return msg.content.length
  if (Array.isArray(msg?.content)) return JSON.stringify(msg.content).length
  if (msg?.reasoning_content) return (msg.reasoning_content || '').length
  return 200
}

function trimContext(messages: any[], maxChars: number): any[] {
  if (maxChars <= 0) return messages
  let total = 0
  for (const m of messages) total += countChars(m)
  if (total <= maxChars) return messages
  const system = messages[0]?.role === 'system' ? messages.shift() : null
  const dropped: any[] = []
  while (messages.length > 2 && total > maxChars) {
    const m = messages.shift()
    if (m) {
      total -= countChars(m)
      dropped.push(m)
    }
  }
  if (dropped.length && system) {
    messages.unshift({ role: 'system', content: `${system.content}\n\n(为节省上下文,对话开头 ${dropped.length} 条历史已省略,按最新消息继续。)` })
  } else if (system) {
    messages.unshift(system)
  }
  return messages
}

function buildUserContent(message: string, images: string[]): string | any[] {
  if (!images || !images.length) return message
  const parts: any[] = [{ type: 'text', text: message }]
  for (const img of images.slice(0, 6)) {
    if (typeof img === 'string' && img.startsWith('data:')) {
      parts.push({ type: 'image_url', image_url: { url: img } })
    }
  }
  return parts.length > 1 ? parts : message
}

function serializeToolResult(content: string, error: boolean): string {
  return error ? `[错误] ${content}` : content
}

export async function runAgentSession(req: AgentRequest, emit: (p: AgentPayload) => void, signal: AbortSignal, opts: AgentRunOptions = {}): Promise<void> {
  const started = Date.now()
  let totalChars = 0
  let totalTools = 0
  const base = normalizeBase(req.llm.baseUrl || 'https://api.openai.com/v1')
  const url = `${base}/chat/completions`
  const maxTurns = opts.maxTurns ?? req.maxTurns ?? MAX_TURNS
  const temperature = opts.temperature ?? req.llm.temperature ?? 0.7
  const maxTokens = opts.maxTokens ?? req.llm.maxTokens
  const maxContextChars = opts.maxContextChars ?? req.maxContextChars ?? MAX_CONTEXT_CHARS

  let system = '你是一个能调用工具的 AI 助手。当需要获取信息或执行操作时,选择合适的工具;工具结果返回后,基于结果组织最终回答。用中文回复。\n\n工具使用原则:\n- 用户要求创建/生成文件时,应调用对应的创建工具\n- 用户要求读取或修改 Word/PowerPoint 文档时,应使用 Office 文档工具\n- 用户要求执行命令或查看本机文件时,应使用本地工具\n- 用户询问最新信息、新闻、时事或你知识库之外的实时数据时,应使用 web_search 联网搜索,必要时用 read_webpage 读取结果页面\n- 如果工具执行失败,尝试其他方式或明确告知用户'
  const skills = getEnabledInstructions(60000)
  if (skills) system += '\n\n你可以使用以下技能,按技能说明执行:\n\n' + skills

  const messages: any[] = [{ role: 'system', content: system }]
  for (const h of req.history || []) {
    if (h.role === 'user' || h.role === 'assistant') messages.push({ role: h.role, content: h.content })
  }
  messages.push({ role: 'user', content: buildUserContent(req.message, req.images || []) })
  trimContext(messages, maxContextChars)

  let tools: any[]
  try {
    tools = await listTools()
    tools = tools.map(t => ({
      type: 'function',
      function: { name: t.name, description: t.description, parameters: t.inputSchema },
    }))
    emit({ sessionId: req.sessionId, type: 'tools_ready', count: tools.length, names: tools.map(t => t.function.name).slice(0, 50) })
  } catch (e: any) {
    emit({ sessionId: req.sessionId, type: 'error', content: `加载工具失败: ${e?.message || e}` })
    return
  }

  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (req.llm.apiKey) headers['Authorization'] = 'Bearer ' + req.llm.apiKey

  try {
    for (let turn = 0; turn < maxTurns; turn++) {
      const accumulatedContent: string[] = []
      const accumulatedReasoning: string[] = []
      const toolCalls = new Map<number, { id: string; name: string; arguments: string }>()

      const body: any = {
        model: req.llm.model,
        messages,
        temperature,
        stream: true,
      }
      if (maxTokens) body.max_tokens = maxTokens
      if (tools.length) body.tools = tools

      const resp = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
        signal,
      })
      if (!resp.ok) {
        const errText = await resp.text().catch(() => '')
        emit({ sessionId: req.sessionId, type: 'error', content: `LLM 请求失败 (${resp.status}): ${errText.slice(0, 300)}` })
        return
      }
      if (!resp.body) {
        emit({ sessionId: req.sessionId, type: 'error', content: 'LLM 无响应流' })
        return
      }

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      let finish: string | null = null

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() || ''
        for (const raw of lines) {
          const line = raw.trim()
          if (!line.startsWith('data: ')) continue
          const payload = line.slice(6)
          if (payload === '[DONE]') { finish = finish || 'stop'; break }
          try {
            const chunk = JSON.parse(payload)
            const delta = chunk.choices?.[0]?.delta
            if (!delta) continue
            const reasoning = delta.reasoning_content ?? delta.reasoning
            if (reasoning) {
              accumulatedReasoning.push(reasoning)
              emit({ sessionId: req.sessionId, type: 'reasoning', content: reasoning })
            }
            if (delta.content) {
              accumulatedContent.push(delta.content)
              emit({ sessionId: req.sessionId, type: 'token', content: delta.content })
            }
            if (delta.tool_calls) {
              for (const tc of delta.tool_calls) {
                const idx = tc.index ?? 0
                let acc = toolCalls.get(idx)
                if (!acc) { acc = { id: '', name: '', arguments: '' }; toolCalls.set(idx, acc) }
                if (tc.id) acc.id += tc.id
                if (tc.function?.name) acc.name += tc.function.name
                if (tc.function?.arguments) acc.arguments += tc.function.arguments
              }
            }
            if (delta.function_call) {
              const fc = delta.function_call
              const idx = 0
              let acc = toolCalls.get(idx)
              if (!acc) { acc = { id: '', name: '', arguments: '' }; toolCalls.set(idx, acc) }
              if (fc.name) acc.name += fc.name
              if (fc.arguments) acc.arguments += typeof fc.arguments === 'string' ? fc.arguments : JSON.stringify(fc.arguments)
            }
            const fr = chunk.choices?.[0]?.finish_reason
            if (fr) finish = fr
          } catch { /* ignore partial */ }
        }
        if (finish === 'stop' || finish === 'tool_calls' || finish === 'function_call') break
      }

      const content = accumulatedContent.join('')
      const reasoning = accumulatedReasoning.join('')
      totalChars += content.length + reasoning.length

      // Some providers (Gemini via OpenAI-compat) report finish_reason "function_call"
      const wantTools = finish === 'tool_calls' || finish === 'function_call'

      if (!wantTools && toolCalls.size === 0) {
        emit({ sessionId: req.sessionId, type: 'usage', chars: totalChars, tools: totalTools })
        emit({ sessionId: req.sessionId, type: 'done' })
        return
      }

      // execute tool calls
      const assistantMsg: any = { role: 'assistant', content: content || null }
      if (reasoning) assistantMsg.reasoning_content = reasoning
      const openaiTcs = [...toolCalls.entries()].map(([idx, tc]) => {
        let args: any = {}
        try { args = tc.arguments ? JSON.parse(tc.arguments) : {} } catch { /* keep {} */ }
        return { id: tc.id || `call_${idx}`, type: 'function', function: { name: tc.name, arguments: JSON.stringify(args) } }
      })
      assistantMsg.tool_calls = openaiTcs
      messages.push(assistantMsg)

      const sorted = [...toolCalls.entries()].sort((a, b) => a[0] - b[0])
      for (const [idx, tc] of sorted) {
        let args: any = {}
        try { args = tc.arguments ? JSON.parse(tc.arguments) : {} } catch { /* keep {} */ }
        const name = tc.name
        totalTools++
        emit({ sessionId: req.sessionId, type: 'tool_call', name, arguments: args })
        const result = await callTool(name, args)
        const safeContent = truncate(result.content || '')
        emit({ sessionId: req.sessionId, type: 'tool_result', name, content: safeContent, error: result.error })
        messages.push({ role: 'tool', tool_call_id: tc.id || `call_${idx}`, content: serializeToolResult(safeContent, result.error) })
        trimContext(messages, maxContextChars)
      }
    }

    emit({ sessionId: req.sessionId, type: 'token', content: '\n\n[已达到最大工具轮次]' })
    emit({ sessionId: req.sessionId, type: 'usage', chars: totalChars, tools: totalTools })
    emit({ sessionId: req.sessionId, type: 'done' })
  } catch (e: any) {
    if (e?.name === 'AbortError') {
      emit({ sessionId: req.sessionId, type: 'error', content: '已停止生成' })
    } else {
      emit({ sessionId: req.sessionId, type: 'error', content: `Agent 出错: ${e?.message || e}` })
    }
    emit({ sessionId: req.sessionId, type: 'done' })
  }
}
