import Panel from './Panel.vue'
import Page from './Page.vue'

export default {
  panel: Panel,
  page: Page,
  async activate(context: any) {
    const { BrowserWindow, globalShortcut } = require('electron') as any
    const { join } = require('path') as any
    let assistantWin: any = null
    let petWin: any = null

    async function showAssistant() {
      if (assistantWin && !assistantWin.isDestroyed()) {
        if (assistantWin.isVisible()) { assistantWin.hide(); return }
        assistantWin.show(); assistantWin.focus(); return
      }
      const preloadPath = join(__dirname, '../../../dist-electron/preload/index.js')
      assistantWin = new BrowserWindow({
        width: 420, height: 620, frame: false,
        alwaysOnTop: true, skipTaskbar: true, resizable: true,
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

    async function togglePet() {
      if (petWin && !petWin.isDestroyed()) {
        if (petWin.isVisible()) { petWin.hide(); return }
        petWin.show(); petWin.focus(); return
      }
      const preloadPath = join(__dirname, '../../../dist-electron/preload/index.js')
      petWin = new BrowserWindow({
        frame: false, transparent: true,
        alwaysOnTop: true, skipTaskbar: true,
        resizable: false,
        webPreferences: { preload: preloadPath, contextIsolation: true, nodeIntegration: false },
      })
      // Fullscreen transparent overlay
      try {
        const display: any = await context.signal('getPrimaryDisplay')
        if (display) petWin.setBounds({ x: display.x, y: display.y, width: display.width, height: display.height })
      } catch {
        petWin.maximize()
      }
      const url = process.env.VITE_DEV_SERVER_URL
        ? `${process.env.VITE_DEV_SERVER_URL}?view=pet`
        : `file://${join(__dirname, '../../../dist/index.html').replace(/\\/g, '/')}?view=pet`
      petWin.loadURL(url)
      // Start in passthrough mode; main process IPC (pet:hit-test) toggles dynamically
      setTimeout(() => {
        if (petWin && !petWin.isDestroyed()) {
          petWin.setIgnoreMouseEvents(true, { forward: true })
          // Windows: SetWindowLong used by setIgnoreMouseEvents can reset WS_EX_TOPMOST
          petWin.setAlwaysOnTop(true, 'pop-up-menu')
          petWin.moveTop()
          // Periodically re-assert topmost (Windows often drops it)
          const guard = setInterval(() => {
            if (petWin && !petWin.isDestroyed()) {
              petWin.setAlwaysOnTop(true, 'pop-up-menu')
            } else {
              clearInterval(guard)
            }
          }, 2000)
        }
      }, 500)
      petWin.on('closed', () => { petWin = null })
    }

    globalShortcut.register('CommandOrControl+Shift+A', () => { showAssistant() })
    globalShortcut.register('CommandOrControl+Shift+P', () => { togglePet() })

    context.registerCommand('getPanelData', async () => ({
      title: 'AI 助理',
      subtitle: '语音对话 · 自然语言操作',
      description: 'Ctrl+Shift+A 呼出助理 · Ctrl+Shift+P 切换桌宠',
      buttons: [{ label: '🐾 桌宠', command: 'togglePet' }],
    }))
    context.registerCommand('getPageData', async () => ({}))
    context.registerCommand('togglePet', async () => { togglePet() })
    context.registerCommand('open', async (args: any) => {
      if (args?.message) {
        try {
          const res = await context.api.post('/chat', {
            message: args.message,
            history: args.history || [],
          })
          const reply = res?.reply || res?.response || ''
          return reply ? { subtitle: reply } : undefined
        } catch (e) {
          return { subtitle: `[请求失败] ${(e as Error).message}` }
        }
      }
      context.openPage('assistant')
    })
    context.registerCommand('toggleAssistant', async () => { showAssistant() })

    context.registerSearchProvider({
      keyword: '>',
      name: 'AI 助理',
      priority: 11,
      onSearch: async (query: string) => {
        const text = query.startsWith('>') ? query.slice(1).trim() : query
        return [{
          title: text ? `问助理: ${text}` : '打开 AI 助理',
          subtitle: text ? '回车发送' : 'Ctrl+Shift+A 呼出助理 › 输入消息',
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
