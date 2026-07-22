import Panel from './Panel.vue'
import Page from './Page.vue'

export default {
  panel: Panel,
  page: Page,
  async activate(context: any) {
    context.registerCommand('getPanelData', async () => ({}))
    context.registerCommand('getPageData', async () => ({}))
    context.registerCommand('open', async () => { context.openPage('ai-chat') })

    context.registerSearchProvider({
      keyword: '>',
      name: 'AI 对话',
      priority: 10,
      onSearch: async (query: string) => {
        const text = query.startsWith('>') ? query.slice(1).trim() : query
        return [{
          title: text ? `问 AI: ${text}` : '打开 AI 对话',
          subtitle: text ? '回车发送' : '与 AI 助手对话',
          icon: 'chat',
          action: 'ai-chat:open',
          actionArgs: text ? { message: text } : {},
          pluginId: 'ai-chat',
        }]
      },
    })
  },
  deactivate() {},
}
