import Panel from './Panel.vue'
import Page from './Page.vue'
import { scanProjects, findWorkspaceDirs, openInFileManager, openInVSCode, type ProjectInfo } from './utils/projectManager'
import { launchTerminal, checkAiTools, type AiTool } from './utils/terminalLauncher'
import { loadConfig as loadFeishuConfig, saveConfig as saveFeishuConfig, sendFeishuMessage, getConfig as getFeishuConfig, type FeishuConfig } from './utils/feishuBot'

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
      context.openPage('devops')
    })

    context.registerCommand('getProjects', async () => projectsCache)
    context.registerCommand('getFeishuConfig', async () => getFeishuConfig())

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
      return sendFeishuMessage('🔔 DevOps 插件测试消息\n如果收到此消息，说明飞书机器人配置成功！')
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
            icon: 'FolderOpened', action: 'devops:open', pluginId: 'devops',
          })
          return results
        }

        const q = text.toLowerCase()
        for (const p of projectsCache) {
          if (p.name.toLowerCase().includes(q) || p.path.toLowerCase().includes(q)) {
            results.push({
              title: `📂 ${p.name}`,
              subtitle: `${p.path} · ${p.type}`,
              icon: 'FolderOpened', action: 'devops:openProject',
              actionArgs: { path: p.path },
              pluginId: 'devops',
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
