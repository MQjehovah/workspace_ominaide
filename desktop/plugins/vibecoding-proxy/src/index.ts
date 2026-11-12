import Panel from './Panel.vue'
import Page from './Page.vue'
import { resolve } from 'path'
import { exec } from 'child_process'
import { existsSync, statSync } from 'fs'
import { scanForProjects, suggestScanDirs, addProject, removeProject, getProjects, openInFileManager, openInVSCode, initStorage, type ProjectInfo } from './utils/projectManager'
import { startAcp, stopAcp, getAcpStatus, stopAllAcp } from './utils/acpClient'
import { checkAiTools, spawnAiProcess, cancelActiveProcess, resetSession, type AiTool } from './utils/terminalLauncher'
import { createChannelManager, CHANNEL_TYPES, type IncomingMessage } from './utils/channelManager'
import { createVibeChannelClient, type VibeChannelClient } from './utils/channelClient'
import { OutputParser, type ParsedEvent } from './utils/outputParser'
import { runCodingAgent } from './utils/codingAgent'
import { createOpenCodeBridge, type OpenCodeBridge } from './utils/opencodeBridge'
import { createAgentSessionStore, type AgentSessionStore } from './utils/agentSessions'

type AgentTool = AiTool | 'omniaide'

interface CodingSession {
  taskId: string
  status: 'running' | 'done' | 'failed'
  output: string
  events: Array<{ event: string; data: Record<string, unknown>; ts: number }>
  startedAt: number
  endedAt: number | null
}

let toolsCache: Record<AiTool, boolean> = { opencode: false, claude: false, codex: false }
let activeAgent: { path: string; tool: AgentTool } | null = null
let channelManager: any = null
let reporter: VibeChannelClient | null = null
let opencodeBridge: OpenCodeBridge | null = null
let agentSessions: AgentSessionStore | null = null
let cliSessionRun: string | null = null
let taskQueue: Promise<void> = Promise.resolve()
let pluginCtx: any = null
let latestCodingTaskId = ''
const codingSessions = new Map<string, CodingSession>()
const codingCancel = new Set<string>()
const projectThreads = new Map<string, any[]>()
let developerProfile: any = null
let developerProfileAt = 0

async function getDeveloperProfile(): Promise<any> {
  if (developerProfileAt && Date.now() - developerProfileAt < 300000) return developerProfile
  try {
    const profile = await pluginCtx.api.get('/auth/profile')
    developerProfile = profile?.developer || null
    developerProfileAt = Date.now()
  } catch { }
  return developerProfile
}

function runGit(args: string, cwd?: string): Promise<string> {
  return new Promise((resolvePromise) => {
    exec(`git ${args}`, { cwd, windowsHide: true }, (err, stdout) => {
      resolvePromise(err ? '' : String(stdout).trim())
    })
  })
}

function newTaskId(): string {
  return `t-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function projectNameOf(dir: string): string {
  const parts = dir.split(/[\\/]/).filter(Boolean)
  return parts[parts.length - 1] || dir
}

function trackCodingEvent(taskId: string, event: string, data: Record<string, unknown>) {
  const session = codingSessions.get(taskId)
  if (session) {
    session.events.push({ event, data, ts: Date.now() })
    if (session.events.length > 500) session.events.splice(0, session.events.length - 500)
    if (event === 'output' && typeof data.chunk === 'string') {
      session.output = (session.output + data.chunk).slice(-60000)
    }
  }
  reporter?.emit(taskId, event as any, data)
}

function snapshotCodingSession(taskId: string) {
  const s = codingSessions.get(taskId)
  if (!s) return null
  return { ...s, events: s.events.slice(-200) }
}

function runVibeTask(opts: { taskId: string; tool: AgentTool; dir: string; input: string; source: string; reply?: (text: string) => Promise<void> }): void {
  taskQueue = taskQueue.then(() => executeVibeTask(opts)).catch((e: any) => {
    console.error('[vibe] task error:', e?.message || e)
  })
}

async function executeVibeTask(opts: { taskId: string; tool: AgentTool; dir: string; input: string; source: string; reply?: (text: string) => Promise<void> }): Promise<void> {
  const { taskId, tool, dir, input, source, reply } = opts
  if (tool === 'omniaide') {
    await executeOmniaideTask(opts)
    return
  }
  try {
    reporter?.emit(taskId, 'started', {
      tool, project: dir, project_name: projectNameOf(dir),
      input: input.slice(0, 500), source,
    })
    reporter?.emit(taskId, 'milestone', { stage: 'spawning' })

    const parser = new OutputParser()
    let buf = ''
    let lastFlush = 0
    const flush = (force = false) => {
      if (!buf) return
      const now = Date.now()
      if (!force && now - lastFlush < 400 && buf.length < 512) return
      reporter?.emit(taskId, 'output', { chunk: buf.slice(0, 8192) })
      buf = ''
      lastFlush = now
    }
    const emitParsed = (events: ParsedEvent[]) => {
      for (const ev of events) {
        if (ev.kind === 'tool') reporter?.emit(taskId, 'tool', { name: ev.name, detail: ev.detail })
        else reporter?.emit(taskId, 'file', { path: ev.path, action: ev.action })
      }
    }
    const onChunk = (chunk: string) => {
      buf += chunk
      flush()
      emitParsed(parser.feed(chunk))
    }

    const t0 = Date.now()
    const result = await spawnAiProcess(tool, dir, input, onChunk)
    flush(true)
    emitParsed(parser.flush())
    const duration = Date.now() - t0

    if (result?.error) {
      reporter?.emit(taskId, 'failed', { error: result.error, duration_ms: duration, code: result.code ?? -1 })
    } else {
      reporter?.emit(taskId, 'done', {
        code: result?.code ?? 0, duration_ms: duration,
        output: (result?.combined || '').slice(0, 20000),
      })
    }
    console.error(`[vibe] task ${taskId} done in ${duration}ms code=${result?.code} error=${result?.error}`)

    if (reply) {
      let text: string
      if (result?.error) {
        text = `❌ ${result.error}\n\n${(result.combined || '').slice(-1500)}`
      } else {
        text = (result?.combined || '').trim() || `✅ exit=${result?.code}（无输出）`
        if (text.length > 3800) text = text.slice(0, 3800) + '\n\n…(输出过长已截断)'
      }
      try { await reply(text) } catch (e: any) { console.error('[vibe] reply failed:', e?.message) }
    }
  } catch (e: any) {
    reporter?.emit(taskId, 'failed', { error: e?.message || String(e), duration_ms: 0 })
    if (reply) {
      try { await reply(`❌ 错误: ${e?.message}`) } catch {}
    }
  }
}

async function executeOmniaideTask(opts: { taskId: string; dir: string; input: string; source: string; reply?: (text: string) => Promise<void> }): Promise<void> {
  const { taskId, dir, input, source, reply } = opts
  latestCodingTaskId = taskId
  codingCancel.delete(taskId)
  codingSessions.set(taskId, {
    taskId, status: 'running', output: '', events: [], startedAt: Date.now(), endedAt: null,
  })
  const emit = (event: string, data: Record<string, unknown>) => trackCodingEvent(taskId, event, data)
  const developer = await getDeveloperProfile()
  try {
    const result = await runCodingAgent({
      taskId,
      dir,
      input,
      source,
      emit,
      developer,
      shouldStop: () => codingCancel.has(taskId),
      history: projectThreads.get(dir) || [],
      onMessages: (messages) => projectThreads.set(dir, messages),
      step: async (messages, tools) => {
        const res = await pluginCtx.api.post('/vibecoding/agent/step', { messages, tools })
        return res || {}
      },
    })
    codingCancel.delete(taskId)
    const session = codingSessions.get(taskId)
    if (session) {
      session.status = result.error ? 'failed' : 'done'
      session.endedAt = Date.now()
      if (result.output) session.output = result.output
    }
    if (reply) {
      const text = result.error
        ? `❌ ${result.error}`
        : (result.output || '✅ 完成').slice(0, 3800)
      try { await reply(text) } catch (e: any) { console.error('[vibe] reply failed:', e?.message) }
    }
  } catch (e: any) {
    const session = codingSessions.get(taskId)
    if (session) { session.status = 'failed'; session.endedAt = Date.now() }
    reporter?.emit(taskId, 'failed', { error: e?.message || String(e), duration_ms: 0 })
    if (reply) {
      try { await reply(`❌ 错误: ${e?.message}`) } catch {}
    }
  }
}

function handleDispatch(msg: any) {
  const tool = (msg?.tool as AgentTool) || 'omniaide'
  const project = String(msg?.project || '')
  const input = String(msg?.input || '')
  const taskId = String(msg?.task_id || newTaskId())
  if (!project || !input) {
    reporter?.emit(taskId, 'failed', { error: '派发缺少 project/input', duration_ms: 0 })
    return
  }
  if (tool !== 'omniaide' && !toolsCache[tool]) {
    reporter?.emit(taskId, 'failed', { error: `${tool} 未安装或不在 PATH（本机）`, duration_ms: 0 })
    return
  }
  const dir = resolve(project)
  if (!existsSync(dir) || !statSync(dir).isDirectory()) {
    reporter?.emit(taskId, 'failed', { error: `项目目录不存在: ${dir}`, duration_ms: 0 })
    return
  }
  runVibeTask({ taskId, tool, dir, input, source: String(msg?.source || 'mobile') })
}

function handleControl(msg: any) {
  if (msg?.action === 'cancel' && msg?.task_id) {
    const taskId = String(msg.task_id)
    const session = codingSessions.get(taskId)
    if (session && session.status === 'running') {
      codingCancel.add(taskId)
      reporter?.emit(taskId, 'milestone', { stage: 'cancelled' })
      return
    }
    const ok = cancelActiveProcess()
    if (ok) reporter?.emit(taskId, 'milestone', { stage: 'cancelled' })
  }
}

async function handleProjectsRequest(msg: any) {
  let tools: Record<string, boolean> = { ...toolsCache }
  try { toolsCache = await checkAiTools(); tools = { ...toolsCache } } catch {}
  reporter?.send({
    type: 'projects.response',
    request_id: msg?.request_id || '',
    projects: getProjects().map((p: ProjectInfo) => ({ name: p.name, path: p.path, type: p.type })),
    tools: { ...tools, omniaide: true },
  })
}

export default {
  panel: Panel,
  page: Page,

  async activate(context: any) {
    pluginCtx = context
    try {
      toolsCache = await checkAiTools()
    } catch {}

    // Persist project list in the user data dir (host provides OMNIAIDE_USER_DATA)
    initStorage()

    reporter = createVibeChannelClient(context)
    reporter.setServerMessageHandler((msg) => {
      if (msg?.type === 'task.dispatch') {
        handleDispatch(msg)
      } else if (msg?.type === 'task.control') {
        handleControl(msg)
      } else if (msg?.type === 'projects.request') {
        handleProjectsRequest(msg)
      } else if (msg?.type === 'oc.request') {
        opencodeBridge?.handleRequest(msg)
      }
    })
    reporter.start()

    // Bridge the local OpenCode 2 server (sessions/messages/streaming) to
    // remote clients such as the mobile app.
    opencodeBridge = createOpenCodeBridge(context, (msg) => reporter?.send(msg))
    opencodeBridge.start()
    agentSessions = createAgentSessionStore(context.storage)

    channelManager = createChannelManager(context.storage, async (msg: IncomingMessage) => {
      // Channel → agent run (session-aware), streamed to backend/mobile
      console.error(`[hook:${msg.channelId}] msg: "${msg.text.slice(0, 60)}"`)

      let bPath = ''
      let bTool: AgentTool = 'opencode'
      try {
        const saved = await context.storage.get('binding_project')
        if (typeof saved === 'object' && saved !== null) {
          bPath = saved.path || ''
          bTool = (saved.tool as AgentTool) || 'opencode'
        } else {
          bPath = String(saved || '')
        }
      } catch {}

      if (!bPath) {
        try { await channelManager.sendTest(msg.channelId) } catch {}
        return
      }
      if (bTool !== 'omniaide' && !toolsCache[bTool]) {
        try {
          const inst = channelManager.getChannel(msg.channelId)
          if (inst) await inst.reply(msg.replyId, `⚠️ ${bTool} 未安装或不在 PATH，请检查安装`)
        } catch {}
        return
      }

      const dir = resolve(bPath)
      console.error(`[hook] ${bTool} run in ${dir}: ${msg.text.slice(0, 80)}`)
      try {
        const inst = channelManager.getChannel(msg.channelId)
        if (inst) await inst.reply(msg.replyId, `✅ 收到，正在用 ${bTool} 处理：${msg.text.slice(0, 50)}`)
      } catch {}

      runVibeTask({
        taskId: newTaskId(),
        tool: bTool,
        dir,
        input: msg.text,
        source: msg.channelId,
        reply: async (text) => {
          const inst = channelManager.getChannel(msg.channelId)
          if (inst) await inst.reply(msg.replyId, text)
        },
      })
    })

    // Auto-start enabled channels
    await channelManager.startAll()

    context.registerCommand('getPanelData', async () => {
      const projects = getProjects()
      const acpStatus = getAcpStatus()
      return {
        title: 'VibeCoding Proxy',
        subtitle: `${projects.length} 个项目 · omniaide/${Object.entries(toolsCache).filter(([,v]) => v).map(([k]) => k).join('/')}`,
        recentProjects: projects.slice(0, 5).map(p => ({
          name: p.name, path: p.path, type: p.type, hasGit: true,
        })),
        tools: { ...toolsCache, omniaide: true },
        items: projects.slice(0, 5).map(p => {
          const acp = acpStatus.find(a => a.path === p.path)
          return {
            title: `${p.name}${acp ? ' 🟢' : ''}`,
            subtitle: `${p.path} · ${p.type}`,
            action: 'open',
            actionArgs: {},
          }
        }),
      }
    })

    // Unified coding sessions across agents (OpenCode has a native store,
    // Codex/Claude sessions are kept by the plugin).
    const normalizeOpenCodeMessages = (messages: any[]) =>
      (messages || [])
        .map((message: any) => {
          const parts = Array.isArray(message.parts) ? message.parts : []
          const text = parts
            .filter((part: any) => part.type === 'text')
            .map((part: any) => part.text)
            .join('\n\n')
          const tools = parts
            .filter((part: any) => part.type === 'tool')
            .map((part: any) => {
              const detail =
                part.input?.command ||
                part.input?.filePath ||
                part.input?.path ||
                ''
              return `${part.name || 'tool'}${detail ? ': ' + String(detail).split('\n')[0].slice(0, 120) : ''}`
            })
          return { role: message.role, text, tools, ts: message.time }
        })
        .filter((message: any) => message.text || (message.tools || []).length)

    context.registerCommand('listCodingAgents', async () => {
      let tools: any = { ...toolsCache }
      try {
        toolsCache = await checkAiTools()
        tools = { ...toolsCache }
      } catch {}
      return [
        { id: 'opencode', label: 'OpenCode 2', available: true, native: true, hint: '原生会话' },
        { id: 'codex', label: 'Codex', available: !!tools.codex, native: false, hint: 'CLI 会话' },
        { id: 'claude', label: 'Claude Code', available: !!tools.claude, native: false, hint: 'CLI 会话' },
      ]
    })

    context.registerCommand('listAgentSessions', async (args: any) => {
      const agent = String(args?.agent || 'opencode')
      if (agent === 'opencode') {
        if (!opencodeBridge) return []
        try {
          const rows = await opencodeBridge.listSessions(100)
          return rows.map((row: any) => ({
            id: row.id,
            agent: 'opencode',
            title: row.title || '未命名会话',
            project: row.directory || '',
            updated: row.updated || row.created || 0,
            running: !!row.busy,
            native: true,
          }))
        } catch {
          return []
        }
      }
      if (!agentSessions) return []
      const rows = await agentSessions.list(agent)
      return rows.map((row) => ({
        id: row.id,
        agent: row.agent,
        title: row.title,
        project: row.project,
        updated: row.updatedAt,
        running: row.running,
        native: false,
      }))
    })

    context.registerCommand('createAgentSession', async (args: any) => {
      const agent = String(args?.agent || 'opencode')
      const project = String(args?.project || '').trim()
      const title = String(args?.title || '').trim()
      if (!project) return { ok: false, error: '请先选择项目目录' }
      if (agent === 'opencode') {
        if (!opencodeBridge) return { ok: false, error: 'OpenCode 桥接未就绪' }
        try {
          const session = await opencodeBridge.createSession(project, title)
          return {
            ok: true,
            session: {
              id: session.id,
              agent: 'opencode',
              title: session.title,
              project: session.directory || project,
              updated: session.updated,
              running: false,
              native: true,
            },
          }
        } catch (error: any) {
          return { ok: false, error: String(error?.message || error) }
        }
      }
      if (!agentSessions) return { ok: false, error: '会话存储未就绪' }
      const session = await agentSessions.create(agent, project, title)
      return {
        ok: true,
        session: {
          id: session.id,
          agent: session.agent,
          title: session.title,
          project: session.project,
          updated: session.updatedAt,
          running: false,
          native: false,
        },
      }
    })

    context.registerCommand('deleteAgentSession', async (args: any) => {
      const agent = String(args?.agent || 'opencode')
      const sessionId = String(args?.sessionId || '')
      if (!sessionId) return { ok: false, error: '缺少 sessionId' }
      try {
        if (agent === 'opencode') {
          await opencodeBridge?.deleteSession(sessionId)
        } else {
          await agentSessions?.remove(sessionId)
        }
        return { ok: true }
      } catch (error: any) {
        return { ok: false, error: String(error?.message || error) }
      }
    })

    context.registerCommand('getAgentSession', async (args: any) => {
      const agent = String(args?.agent || 'opencode')
      const sessionId = String(args?.sessionId || '')
      if (!sessionId) return { ok: false, error: '缺少 sessionId' }
      if (agent === 'opencode') {
        if (!opencodeBridge) return { ok: false, error: 'OpenCode 桥接未就绪' }
        try {
          const history = await opencodeBridge.history(sessionId, 150)
          return {
            ok: true,
            session: {
              id: sessionId,
              agent: 'opencode',
              title: String(args?.title || ''),
              project: String(args?.project || ''),
              running: opencodeBridge.isBusy(sessionId),
              native: true,
            },
            messages: normalizeOpenCodeMessages(history?.messages || []),
            streaming: '',
          }
        } catch (error: any) {
          return { ok: false, error: String(error?.message || error) }
        }
      }
      const session = await agentSessions?.get(sessionId)
      if (!session) return { ok: false, error: '会话不存在' }
      return {
        ok: true,
        session: {
          id: session.id,
          agent: session.agent,
          title: session.title,
          project: session.project,
          running: session.running,
          native: false,
        },
        messages: session.messages,
        streaming: session.streaming,
      }
    })

    context.registerCommand('sendAgentMessage', async (args: any) => {
      const agent = String(args?.agent || 'opencode')
      const sessionId = String(args?.sessionId || '')
      const text = String(args?.text || '').trim()
      if (!sessionId) return { ok: false, error: '缺少 sessionId' }
      if (!text) return { ok: false, error: '内容不能为空' }
      if (agent === 'opencode') {
        if (!opencodeBridge) return { ok: false, error: 'OpenCode 桥接未就绪' }
        try {
          await opencodeBridge.prompt(sessionId, text)
          return { ok: true }
        } catch (error: any) {
          return { ok: false, error: String(error?.message || error) }
        }
      }
      if (!agentSessions) return { ok: false, error: '会话存储未就绪' }
      if (cliSessionRun) return { ok: false, error: '已有 CLI 会话正在执行，请先停止' }
      if (agent !== 'codex' && agent !== 'claude') {
        return { ok: false, error: `暂不支持 ${agent}` }
      }
      if (!toolsCache[agent]) {
        return { ok: false, error: `${agent} CLI 未安装或不在 PATH` }
      }
      const session = await agentSessions.get(sessionId)
      if (!session) return { ok: false, error: '会话不存在' }
      await agentSessions.appendMessage(sessionId, {
        role: 'user',
        text,
        ts: Date.now(),
      })
      await agentSessions.setRunning(sessionId, true)
      cliSessionRun = sessionId
      let buffer = ''
      void spawnAiProcess(agent, session.project, text, (chunk) => {
        buffer += chunk
        void agentSessions?.setStreaming(sessionId, buffer)
      })
        .then(async (result) => {
          await agentSessions?.finishRun(
            sessionId,
            result?.combined || buffer,
            result?.error,
          )
        })
        .catch(async (error: any) => {
          await agentSessions?.finishRun(
            sessionId,
            buffer,
            String(error?.message || error),
          )
        })
        .finally(() => {
          cliSessionRun = null
        })
      return { ok: true }
    })

    context.registerCommand('stopAgentMessage', async (args: any) => {
      const agent = String(args?.agent || 'opencode')
      const sessionId = String(args?.sessionId || '')
      try {
        if (agent === 'opencode') {
          await opencodeBridge?.interrupt(sessionId)
        } else {
          cancelActiveProcess()
          if (agentSessions) await agentSessions.setRunning(sessionId, false)
          cliSessionRun = null
        }
        return { ok: true }
      } catch (error: any) {
        return { ok: false, error: String(error?.message || error) }
      }
    })

    context.registerCommand('getPageData', async () => ({}))

    context.registerCommand('open', async () => context.openPage('vibecoding-proxy'))

    // Project CRUD
    context.registerCommand('getProjects', async () => getProjects())
    context.registerCommand('getAcpStatus', async () => getAcpStatus())

    context.registerCommand('scanDir', async () => {
      const dirs = suggestScanDirs()
      const res = scanForProjects(dirs)
      context.signal('panel:updated')
      return res
    })

    context.registerCommand('scanCustomDir', async (args: any) => {
      if (!args?.dir) return getProjects()
      const res = scanForProjects([args.dir])
      context.signal('panel:updated')
      return res
    })

    context.registerCommand('addProject', async (args: any) => {
      if (!args?.dir) return null
      const res = addProject(args.dir)
      context.signal('panel:updated')
      return res
    })

    context.registerCommand('removeProject', async (args: any) => {
      if (!args?.path) return false
      stopAcp(args.path)
      const res = removeProject(args.path)
      context.signal('panel:updated')
      return res
    })

    // ACP lifecycle
    context.registerCommand('startAcp', async (args: any) => {
      if (!args?.path) return { success: false }
      return startAcp(args.path)
    })

    context.registerCommand('stopAcp', async (args: any) => {
      if (!args?.path) return false
      return stopAcp(args.path)
    })

    context.registerCommand('stopAllAcp', async () => {
      stopAllAcp()
      return true
    })

    // Channel management
    context.registerCommand('getChannels', async () => channelManager.getChannels())
    context.registerCommand('getChannelTypes', async () => CHANNEL_TYPES)
    context.registerCommand('getChannelStatus', async () => channelManager.getStatus())
    context.registerCommand('saveChannel', async (cfg: any) => {
      try {
        await channelManager.saveChannel(cfg)
        return true
      } catch { return false }
    })
    context.registerCommand('removeChannel', async (args: any) => {
      if (!args?.id) return false
      return channelManager.removeChannel(args.id)
    })
    context.registerCommand('startChannels', async () => {
      try { await channelManager.startAll(); return true } catch { return false }
    })
    context.registerCommand('testChannel', async (args: any) => {
      if (!args?.id) return false
      return channelManager.sendTest(args.id)
    })

    context.registerCommand('getToolsCache', async () => ({ ...toolsCache, omniaide: true }))

    context.registerCommand('runCoding', async (args: any) => {
      const path = String(args?.path || '')
      const input = String(args?.input || '')
      if (!path || !input.trim()) return { ok: false, error: '缺少项目路径或指令' }
      const dir = resolve(path)
      if (!existsSync(dir) || !statSync(dir).isDirectory()) return { ok: false, error: `项目目录不存在: ${dir}` }
      const taskId = newTaskId()
      runVibeTask({ taskId, tool: 'omniaide', dir, input, source: 'panel' })
      return { ok: true, taskId }
    })

    context.registerCommand('cancelCoding', async (args: any) => {
      const taskId = String(args?.taskId || '')
      if (!taskId) return false
      handleControl({ action: 'cancel', task_id: taskId })
      return true
    })

    context.registerCommand('getCodingSession', async (args: any) => {
      const taskId = String(args?.taskId || latestCodingTaskId || '')
      return snapshotCodingSession(taskId)
    })

    context.registerCommand('resetCodingThread', async (args: any) => {
      const path = String(args?.path || '')
      if (!path) return false
      projectThreads.delete(resolve(path))
      return true
    })

    context.registerCommand('getDeveloperProfile', async () => getDeveloperProfile())

    context.registerCommand('refreshDeveloperProfile', async () => {
      developerProfile = null
      developerProfileAt = 0
      return getDeveloperProfile()
    })

    context.registerCommand('detectDeveloperIdentity', async (args: any) => {
      const cwd = args?.path ? resolve(String(args.path)) : undefined
      const name = await runGit('config --global user.name')
      const email = await runGit('config --global user.email')
      const remote = await runGit('remote get-url origin', cwd)
      let github = name
      const m = remote.match(/github\.com[:/]([^/]+)\//i)
      if (m) github = m[1]
      const developer = {
        github_username: github || name,
        github_email: email,
        default_org: '',
        workspace_roots: [],
        default_branch: 'main',
        auth: 'ssh',
        ssh_key_path: '~/.ssh/id_rsa',
        permissions: ['read', 'edit', 'commit', 'push'],
        commit_style: '',
        notes: '',
      }
      try {
        await pluginCtx.api.put('/auth/profile', { developer })
        developerProfile = developer
        developerProfileAt = Date.now()
      } catch { }
      return developer
    })

    context.registerCommand('getBackendStatus', async () =>
      (await reporter?.status()) || { enabled: false, connected: false, machineId: '', queued: 0 })

    context.registerCommand('getOpenCodeStatus', async () =>
      (await opencodeBridge?.status()) || { available: false })

    context.registerCommand('setOpenCodeServer', async (args: any) => {
      try {
        await context.storage.set('opencode_url', String(args?.url || '').trim())
        await context.storage.set('opencode_password', String(args?.password || ''))
        return true
      } catch {
        return false
      }
    })

    context.registerCommand('resetSession', async () => {
      resetSession()
      return true
    })

    context.registerCommand('bindProject', async (args: any) => {
      const path = args?.path || ''
      const tool = (args?.tool as AgentTool) || 'opencode'
      try {
        await context.storage.set('binding_project', { path, tool })
      } catch {}
      return true
    })

    // Start the selected agent tool in a project (and bind it for Feishu)
    context.registerCommand('startProjectAgent', async (args: any) => {
      const path = args?.path || ''
      const tool = (args?.tool as AgentTool) || 'opencode'
      if (!path) return { ok: false, error: '缺少项目路径' }
      if (tool !== 'omniaide' && !toolsCache[tool]) return { ok: false, error: `${tool} 未安装或不在 PATH` }

      // Bind this project + tool so Feishu messages route here
      try { await context.storage.set('binding_project', { path, tool }) } catch {}

      if (tool === 'omniaide') {
        activeAgent = { path, tool }
        return { ok: true, tool, path, ms: 0, code: 0, output: '自研 Agent 已就绪' }
      }

      // Probe the agent with a short init prompt to confirm it launches
      const t0 = Date.now()
      const result = await spawnAiProcess(tool, path, '请回复：就绪')
      const combined = (result?.combined || '').trim()
      const ok = !result?.error
      if (ok) activeAgent = { path, tool }
      return {
        ok,
        tool,
        path,
        ms: Date.now() - t0,
        code: result?.code,
        output: result?.error ? `${result.error}\n${combined.slice(-500)}` : combined.slice(-800) || '(无输出)',
      }
    })

    context.registerCommand('stopProjectAgent', async (args: any) => {
      const path = args?.path || ''
      // End any active agent session
      resetSession()
      if (activeAgent && (!path || activeAgent.path === path)) activeAgent = null
      return true
    })

    context.registerCommand('getActiveAgent', async () => activeAgent)

    context.registerCommand('getBinding', async () => {
      try {
        const saved = await context.storage.get('binding_project')
        if (typeof saved === 'object' && saved !== null) {
          return { path: saved.path || '', tool: (saved.tool as AgentTool) || 'opencode' }
        }
        return { path: String(saved || ''), tool: 'opencode' }
      } catch {
        return { path: '', tool: 'opencode' }
      }
    })

    context.registerCommand('spawnAiProcess', async (args: any) => {
      if (!args?.tool || !args?.path) return { error: '缺少 tool/path' }
      return spawnAiProcess(args.tool as AiTool, args.path, args.input || '')
    })

    // File operations
    context.registerCommand('openFolder', async (args: any) => {
      if (args?.path) openInFileManager(args.path)
    })

    context.registerCommand('openVSCode', async (args: any) => {
      if (args?.path) openInVSCode(args.path)
    })

    context.registerSearchProvider({
      keyword: '>',
      name: 'VibeCoding',
      priority: 9,
      onSearch: async (query: string) => {
        const projects = getProjects()
        const text = query.startsWith('>') ? query.slice(1).trim() : query
        const results: any[] = []
        if (!text) {
          results.push({ title: 'VibeCoding Proxy', subtitle: `${projects.length} 个项目`, icon: 'FolderOpened', action: 'vibecoding-proxy:open', pluginId: 'vibecoding-proxy' })
          return results
        }
        const q = text.toLowerCase()
        for (const p of projects) {
          if (p.name.toLowerCase().includes(q) || p.path.toLowerCase().includes(q)) {
            results.push({ title: `📂 ${p.name}`, subtitle: p.path, icon: 'FolderOpened', action: 'vibecoding-proxy:openProject', actionArgs: { path: p.path }, pluginId: 'vibecoding-proxy' })
            if (results.length >= 5) break
          }
        }
        return results
      },
    })
  },

  deactivate() {
    opencodeBridge?.stop()
    opencodeBridge = null
    stopAllAcp()
    if (channelManager) channelManager.stopAll()
    reporter?.stop()
    reporter = null
  },
}
