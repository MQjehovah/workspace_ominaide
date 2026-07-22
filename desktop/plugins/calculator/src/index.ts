import Panel from './Panel.vue'
import Page from './Page.vue'

export default {
  panel: Panel,
  page: Page,

  activate(context: any) {
    context.registerCommand('getPanelData', async () => ({
      title: '计算器',
      summary: '0',
      items: [{ title: '点击打开计算器', icon: '🔢' }],
      actions: [{ label: '打开', command: 'open' }],
    }))
    context.registerCommand('getPageData', async () => ({}))

    context.registerCommand('open', async () => {
      context.openPage('calculator')
    })

    context.registerSearchProvider({
      keyword: 'calc',
      name: '计算器',
      priority: 10,
      onSearch: async (query: string) => {
        if (!query) {
          return [{
            title: '打开计算器',
            subtitle: '进行简单的数学计算',
            icon: 'calc',
            action: 'calculator:open',
            pluginId: 'calculator'
          }]
        }
        return []
      }
    })
  },

  deactivate() {}
}
