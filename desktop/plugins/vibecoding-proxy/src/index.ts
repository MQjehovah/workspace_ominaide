import Panel from './Panel.vue'
import Page from './Page.vue'
import { scanProjects, findWorkspaceDirs, openInFileManager, openInVSCode, type ProjectInfo } from './utils/projectManager'
import { launchTerminal, checkAiTools, spawnAiProcess, startSession, sendInput, pollOutput, endSession, isSessionActive, setSignalFn, resetSession, type AiTool } from './utils/terminalLauncher'
import { loadConfig as loadFeishuConfig, saveConfig as saveFeishuConfig, sendFeishuMessage, getConfig as getFeishuConfig, startFeishuClient, stopFeishuClient, getFeishuStatus, setOnMessage, getFeishuClient, config as feishuConfig, type FeishuConfig } from './utils/feishuBot'

let projectsCache: ProjectInfo[] = []
let toolsCache = { opencode: false, claude: false }

export default {
  panel: Panel,
  page: Page,

  async activate(context: any) {
    try {
      const dirs = findWorkspaceDirs()
      projectsCache = scanProjects(dirs)
    } catch {}
    try {
      toolsCache = await checkAiTools()
    } catch {}

    await loadFeishuConfig(context.storage)

    setSignalFn(context.signal)

    // Feishu message → opencode relay
    setOnMessage(async (text: string, chatId: string, userId: string, msgId: string) => {
      try {
        const result = await spawnAiProcess('opencode', projectsCache[0]?.path || '', text)
        const reply = result?.combined?.trim() || result?.stdout?.trim() || '处理完成，但无输出'
        const client = getFeishuClient()
        if (client) {
          await client.replyMessage(msgId, reply)
        }
      } catch {}
    })

    context.registerCommand('getPanelData', async () => ({
      title: 'DevOps',
      subtitle: '项目管理 · 终端 · 飞书',
      description: `找到 ${projectsCache.length} 个项目 · opencode ${toolsCache.opencode ? '✓' : '✗'} · claude ${toolsCache.claude ? '✓' : '✗'}`,
      buttons: [
        { label: '📂 管理器', command: 'open' },
        { label: '🔍 扫描', command: 'scanProjects' },
      ],
      recentProjects: projectsCache.slice(0, 5),
      tools: toolsCache,
    }))

    context.registerCommand('getPageData', async () => ({}))

    context.registerCommand('open', async () => {
      context.openPage('vibecoding-proxy')
    })

    context.registerCommand('getProjects', async () => projectsCache)
    context.registerCommand('getFeishuConfig', async () => getFeishuConfig())

    context.registerCommand('scanDir', async (args: any) => {
      if (!args?.dir) return projectsCache
      try {
        projectsCache = scanProjects([args.dir])
        toolsCache = await checkAiTools()
      } catch {}
      return projectsCache
    })

    context.registerCommand('scanProjects', async () => {
      try {
        const dirs = findWorkspaceDirs()
        projectsCache = scanProjects(dirs)
        toolsCache = await checkAiTools()
      } catch {}
      return projectsCache
    })

    context.registerCommand('openProject', async (args: any) => {
      if (args?.path) launchTerminal(args.path, 'opencode')
    })

    context.registerCommand('launchTerminal', async (args: any) => {
      const { path, tool, prompt } = args || {}
      if (!path) return { error: 'no path' }
      launchTerminal(path, tool || 'opencode', prompt)
      return { success: true }
    })

    context.registerCommand('openFolder', async (args: any) => {
      if (args?.path) openInFileManager(args.path)
    })

    context.registerCommand('openVSCode', async (args: any) => {
      if (args?.path) openInVSCode(args.path)
    })

    context.registerCommand('resetSession', async () => { resetSession(); return { success: true } })

    // One-shot AI prompt with -c for conversation context
    context.registerCommand('spawnAiProcess', async (args: any) => {
      const { tool, path, input } = args || {}
      if (!path || !input) return { error: 'missing path or input' }
      const result = await spawnAiProcess(tool || 'opencode', path, input)
      return result || { stdout: '', stderr: '', error: 'process failed' }
    })

    // Interactive AI session (uses PTY via main process bridge)
    context.registerCommand('startSession', async (args: any) => {
      const { tool, path } = args || {}
      if (!path) return { error: 'no path' }
      return await startSession(tool || 'opencode', path)
    })

    context.registerCommand('sendInput', async (args: any) => {
      const { input } = args || {}
      if (!input) return { error: 'no input' }
      return await sendInput(input)
    })

    context.registerCommand('pollOutput', async () => {
      return await pollOutput()
    })

    context.registerCommand('endSession', async () => {
      await endSession()
      return { success: true }
    })

    context.registerCommand('sessionStatus', async () => ({
      active: await isSessionActive(),
    }))

    context.registerCommand('pickProject', async () => {
      // Use dialog via Electron RPC
      const result = await context.signal('dialog:showOpenDialog', {
        properties: ['openDirectory'],
        title: '选择项目目录',
      })
      return result?.filePaths?.[0] || ''
    })

    context.registerCommand('saveFeishuConfig', async (cfg: FeishuConfig) => {
      try {
        await saveFeishuConfig(context.storage, cfg)
        return true
      } catch { return false }
    })

    context.registerCommand('testFeishu', async () => {
      const client = getFeishuClient()
      if (client && client.lastMessageId) {
        try {
          await client.replyMessage(client.lastMessageId, '✅ VibeCoding Proxy 测试成功！\n收到这条消息说明飞书直连和 opencode 集成正常工作。')
          return true
        } catch { return false }
      }
      return false
    })

    context.registerCommand('startFeishu', async () => {
      try {
        await startFeishuClient()
        return true
      } catch { return false }
    })

    context.registerCommand('stopFeishu', async () => {
      stopFeishuClient()
      return true
    })

    context.registerCommand('feishuStatus', async () => {
      return getFeishuStatus()
    })

    context.registerSearchProvider({
      keyword: '>',
      name: 'DevOps',
      priority: 9,
      onSearch: async (query: string) => {
        const text = query.startsWith('>') ? query.slice(1).trim() : query
        const results: any[] = []

        if (!text) {
          results.push({
            title: 'DevOps 项目管理',
            subtitle: `${projectsCache.length} 个项目 · opencode ${toolsCache.opencode ? '✓' : '未安装'}`,
            icon: 'FolderOpened', action: 'vibecoding-proxy:open', pluginId: 'vibecoding-proxy',
          })
          return results
        }

        const q = text.toLowerCase()
        for (const p of projectsCache) {
          if (p.name.toLowerCase().includes(q) || p.path.toLowerCase().includes(q)) {
            results.push({
              title: `📂 ${p.name}`,
              subtitle: `${p.path} · ${p.type}`,
              icon: 'FolderOpened', action: 'vibecoding-proxy:openProject',
              actionArgs: { path: p.path },
              pluginId: 'vibecoding-proxy',
            })
            if (results.length >= 5) break
          }
        }
        return results
      },
    })
  },

  deactivate() {},
}
