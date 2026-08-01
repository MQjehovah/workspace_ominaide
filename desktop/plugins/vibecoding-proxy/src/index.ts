import Panel from './Panel.vue'
import Page from './Page.vue'
import { spawn } from 'child_process'
import { resolve } from 'path'
import { scanForProjects, suggestScanDirs, addProject, removeProject, getProjects, openInFileManager, openInVSCode, initStorage, type ProjectInfo } from './utils/projectManager'
import { startAcp, stopAcp, getAcpStatus, stopAllAcp } from './utils/acpClient'
import { loadConfig as loadFeishuConfig, saveConfig as saveFeishuConfig, startFeishuClient, stopFeishuClient, getFeishuStatus, setOnMessage, getFeishuClient, config as feishuConfig } from './utils/feishuBot'
import { checkAiTools } from './utils/terminalLauncher'

let toolsCache = { opencode: false, claude: false }
let storageBase = ''
let bindingProject = ''
let sessionStarted = false

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

    await loadFeishuConfig(context.storage)

    // Restore binding from storage
    try { bindingProject = await context.storage.get('binding_project') || '' } catch {}

    // Feishu → opencode run -c (non-blocking background process)
    setOnMessage(async (text: string, chatId: string, userId: string, msgId: string) => {
      const client = getFeishuClient()
    //  const warn = `测试 handler 被调用！text="${text}" msgId="${msgId}"`
    //  console.error(warn)
      if (!msgId || !client) { console.error('[hook] no msgId or client'); return }

      // 立即回复确认
      try { await client.replyMessage(msgId, `收到: ${text}`); console.error('[hook] 确认回复成功') }
      catch (e: any) { console.error('[hook] 确认回复失败:', e.message); return }

      if (!bindingProject) {
        try { await client.replyMessage(msgId, '⚠️ 未绑定项目') } catch {}
        return
      }

      const dir = resolve(bindingProject)
      const args = sessionStarted ? ['run', '-c', text] : ['run', text]
      sessionStarted = true
      console.error(`[hook] 启动 opencode: ${args.join(' ')} in ${dir}`)

      try {
        // Write a .ps1 script file (UTF-8 native) and run with PowerShell
        const { writeFileSync, mkdtempSync } = require('fs')
        const { join } = require('path')
        const tmpDir = mkdtempSync(join(require('os').tmpdir(), 'vibecoding-'))
        const psFile = join(tmpDir, 'run.ps1')
        writeFileSync(psFile, `opencode ${args.join(' ')}\n`, 'utf8')
        const child = spawn('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', psFile], { cwd: dir, stdio: ['pipe', 'pipe', 'pipe'] })
        let output = ''
        child.stdout?.on('data', (d: Buffer) => { output += d.toString() })
        child.stderr?.on('data', (d: Buffer) => { output += d.toString() })
        child.on('close', async (code) => {
          console.error(`[hook] opencode exit code=${code}`)
          const reply = output.trim() || `✅ exit=${code}`
          try { await client.replyMessage(msgId, reply) } catch (e2: any) { console.error('[hook] 回复失败:', e2.message) }
        })
        child.on('error', async (err) => {
          console.error('[hook] spawn error:', err.message)
          try { await client.replyMessage(msgId, '❌ opencode 启动失败') } catch {}
        })
      } catch (e: any) {
        console.error('[hook] exception:', e.message)
        try { await client.replyMessage(msgId, `❌ 错误: ${e.message}`) } catch {}
      }
    })

    context.registerCommand('getPanelData', async () => {
      const projects = getProjects()
      const acpStatus = getAcpStatus()
      return {
        title: 'VibeCoding Proxy',
        subtitle: `${projects.length} 个项目 · ACP ${acpStatus.length} 个运行中`,
        items: projects.slice(0, 5).map(p => {
          const acp = acpStatus.find(a => a.path === p.path)
          return {
            title: `${p.name}${acp ? ' 🟢' : ''}`,
            subtitle: `${p.path} · ${p.type}`,
            action: 'open',
            actionArgs: {},
          }
        }),
        buttons: [
          { label: '📂 管理器', command: 'open' },
          { label: '🔍 扫描项目', command: 'scanDir' },
        ],
      }
    })

    context.registerCommand('getPageData', async () => ({}))

    context.registerCommand('open', async () => context.openPage('vibecoding-proxy'))

    // Project CRUD
    context.registerCommand('getProjects', async () => getProjects())
    context.registerCommand('getAcpStatus', async () => getAcpStatus())

    context.registerCommand('scanDir', async () => {
      const dirs = suggestScanDirs()
      return scanForProjects(dirs)
    })

    context.registerCommand('scanCustomDir', async (args: any) => {
      if (!args?.dir) return getProjects()
      return scanForProjects([args.dir])
    })

    context.registerCommand('addProject', async (args: any) => {
      if (!args?.dir) return null
      return addProject(args.dir)
    })

    context.registerCommand('removeProject', async (args: any) => {
      if (!args?.path) return false
      stopAcp(args.path)
      return removeProject(args.path)
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

    // Feishu binding
    context.registerCommand('getFeishuConfig', async () => feishuConfig)

    context.registerCommand('saveFeishuConfig', async (cfg: any) => {
      try {
        await saveFeishuConfig(context.storage, cfg)
        return true
      } catch { return false }
    })

    context.registerCommand('startFeishu', async () => {
      try { await startFeishuClient(); return true } catch { return false }
    })

    context.registerCommand('stopFeishu', async () => {
      stopFeishuClient()
      return true
    })

    context.registerCommand('feishuStatus', async () => getFeishuStatus())

    context.registerCommand('bindProject', async (args: any) => {
      bindingProject = args?.path || ''
      try { await context.storage.set('binding_project', bindingProject) } catch {}
      return true
    })

    context.registerCommand('getBinding', async () => bindingProject)

    // Test via acp
    context.registerCommand('testFeishu', async () => {
      const client = getFeishuClient()
      if (client && client.lastMessageId) {
        try {
          await client.replyMessage(client.lastMessageId, '✅ VibeCoding Proxy ACP 模式测试成功！')
          return true
        } catch { return false }
      }
      return false
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
    stopFeishuClient()
  },
}
