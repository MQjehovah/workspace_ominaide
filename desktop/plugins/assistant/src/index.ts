import Panel from './Panel.vue'
import Page from './Page.vue'

export default {
  panel: Panel,
  page: Page,
  async activate(context: any) {
    const { BrowserWindow, globalShortcut } = require('electron') as any
    const { join } = require('path') as any
    let assistantWin: any = null

    async function showAssistant() {
      if (assistantWin && !assistantWin.isDestroyed()) {
        if (assistantWin.isVisible()) { assistantWin.hide(); return }
        assistantWin.show(); assistantWin.focus(); return
      }
      const preloadPath = join(__dirname, '../../dist-electron/preload/index.js')
      assistantWin = new BrowserWindow({
        width: 420,
        height: 620,
        frame: false,
        alwaysOnTop: true,
        skipTaskbar: true,
        resizable: true,
        webPreferences: { preload: preloadPath, contextIsolation: true },
      })
      const url = process.env.VITE_DEV_SERVER_URL
        ? `${process.env.VITE_DEV_SERVER_URL}?view=assistant`
        : `file://${join(__dirname, '../../../dist/index.html').replace(/\\/g, '/')}?view=assistant`
      assistantWin.loadURL(url)
      assistantWin.on('blur', () => {
        setTimeout(() => { if (assistantWin && !assistantWin.isDestroyed()) assistantWin.hide() }, 200)
      })
      assistantWin.on('closed', () => { assistantWin = null })
    }

    globalShortcut.register('CommandOrControl+Shift+A', () => { showAssistant() })

    context.registerCommand('getPanelData', async () => ({}))
    context.registerCommand('getPageData', async () => ({}))
    context.registerCommand('open', async () => { context.openPage('assistant') })
    context.registerCommand('toggleAssistant', async () => { showAssistant() })

    context.registerSearchProvider({
      keyword: '?',
      name: 'AI 助理',
      priority: 11,
      onSearch: async (query: string) => {
        const text = query.startsWith('?') ? query.slice(1).trim() : query
        return [{
          title: text ? `问助理: ${text}` : '打开 AI 助理',
          subtitle: text ? '回车发送' : 'Ctrl+Shift+A 呼出助理',
          icon: 'ChatDotSquare',
          action: 'assistant:open',
          actionArgs: text ? { message: text } : {},
          pluginId: 'assistant',
        }]
      },
    })
  },
  deactivate() {},
}
