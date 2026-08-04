import Panel from './Panel.vue'
import Page from './Page.vue'
import { resolve } from 'path'
import { scanForProjects, suggestScanDirs, addProject, removeProject, getProjects, openInFileManager, openInVSCode, initStorage, type ProjectInfo } from './utils/projectManager'
import { startAcp, stopAcp, getAcpStatus, stopAllAcp } from './utils/acpClient'
import { checkAiTools, spawnAiProcess, resetSession, type AiTool } from './utils/terminalLauncher'
import { createChannelManager, CHANNEL_TYPES, type IncomingMessage } from './utils/channelManager'

let toolsCache: Record<AiTool, boolean> = { opencode: false, claude: false, codex: false }
let storageBase = ''
let activeAgent: { path: string; tool: AiTool } | null = null
let channelManager: any = null

export default {
  panel: Panel,
  page: Page,

  async activate(context: any) {
    try {
      toolsCache = await checkAiTools()
    } catch {}

    // Use plugin storage dir for data persistence
    storageBase = context.plugin.path || process.cwd()
    initStorage(storageBase)

    channelManager = createChannelManager(context.storage, async (msg: IncomingMessage) => {
      // Channel → agent run (session-aware)
      console.error(`[hook:${msg.channelId}] msg: "${msg.text.slice(0, 60)}"`)

      let bPath = ''
      let bTool: AiTool = 'opencode'
      try {
        const saved = await context.storage.get('binding_project')
        if (typeof saved === 'object' && saved !== null) {
          bPath = saved.path || ''
          bTool = (saved.tool as AiTool) || 'opencode'
        } else {
          bPath = String(saved || '')
        }
      } catch {}

      if (!bPath) {
        try { await channelManager.sendTest(msg.channelId) } catch {}
        return
      }
      if (!toolsCache[bTool]) {
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

      try {
        const t0 = Date.now()
        const result = await spawnAiProcess(bTool, dir, msg.text)
        console.error(`[hook] agent done in ${Date.now()-t0}ms error=${result?.error} code=${result?.code} outLen=${(result?.combined||'').length}`)
        let reply = ''
        if (result?.error) {
          reply = `❌ ${result.error}\n\n${(result.combined || '').slice(-1500)}`
        } else {
          reply = (result?.combined || '').trim() || `✅ exit=${result?.code}（无输出）`
          if (reply.length > 3800) reply = reply.slice(0, 3800) + '\n\n…(输出过长已截断)'
        }
        try {
          const inst = channelManager.getChannel(msg.channelId)
          if (inst) await inst.reply(msg.replyId, reply)
        } catch (e2: any) { console.error('[hook] 回复失败:', e2.message) }
      } catch (e: any) {
        console.error('[hook] exception:', e.message)
        try {
          const inst = channelManager.getChannel(msg.channelId)
          if (inst) await inst.reply(msg.replyId, `❌ 错误: ${e.message}`)
        } catch {}
      }
    })

    // Auto-start enabled channels
    await channelManager.startAll()

    context.registerCommand('getPanelData', async () => {
      const projects = getProjects()
      const acpStatus = getAcpStatus()
      return {
        title: 'VibeCoding Proxy',
        subtitle: `${projects.length} 个项目 · ${Object.entries(toolsCache).filter(([,v]) => v).map(([k]) => k).join('/')}`,
        recentProjects: projects.slice(0, 5).map(p => ({
          name: p.name, path: p.path, type: p.type, hasGit: true,
        })),
        tools: toolsCache,
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

    context.registerCommand('getToolsCache', async () => toolsCache)

    context.registerCommand('resetSession', async () => {
      resetSession()
      return true
    })

    context.registerCommand('bindProject', async (args: any) => {
      const path = args?.path || ''
      const tool = (args?.tool as AiTool) || 'opencode'
      try {
        await context.storage.set('binding_project', { path, tool })
      } catch {}
      return true
    })

    // Start the selected agent tool in a project (and bind it for Feishu)
    context.registerCommand('startProjectAgent', async (args: any) => {
      const path = args?.path || ''
      const tool = (args?.tool as AiTool) || 'opencode'
      if (!path) return { ok: false, error: '缺少项目路径' }
      if (!toolsCache[tool]) return { ok: false, error: `${tool} 未安装或不在 PATH` }

      // Bind this project + tool so Feishu messages route here
      try { await context.storage.set('binding_project', { path, tool }) } catch {}

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
          return { path: saved.path || '', tool: (saved.tool as AiTool) || 'opencode' }
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
    stopAllAcp()
    if (channelManager) channelManager.stopAll()
  },
}
