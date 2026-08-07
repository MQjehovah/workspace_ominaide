import Panel from './Panel.vue'
import Page from './Page.vue'

export default {
  panel: Panel,
  page: Page,
  async activate(context: any) {
    const { globalShortcut } = require('electron') as any

    function openConsole() {
      context.openPage('assistant')
    }

    globalShortcut.register('CommandOrControl+Shift+A', () => { openConsole() })

    context.registerCommand('getPanelData', async () => ({
      title: 'AI 助理',
      subtitle: '语音对话 · 自然语言操作 · 工具调用',
      description: 'Ctrl+Shift+A 快速打开控制台 · 语音对话 · 自然语言操作',
    }))
    context.registerCommand('getPageData', async () => ({}))
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
    context.registerCommand('toggleAssistant', async () => { openConsole() })

    context.registerSearchProvider({
      keyword: '>',
      name: 'AI 助理',
      priority: 11,
      onSearch: async (query: string) => {
        const text = query.startsWith('>') ? query.slice(1).trim() : query
        return [{
          title: text ? `问助理: ${text}` : '打开 AI 控制台',
          subtitle: text ? '回车发送' : 'Ctrl+Shift+A 打开控制台',
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
