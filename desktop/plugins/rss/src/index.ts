import Panel from './Panel.vue'
import Page from './Page.vue'

export default {
  panel: Panel,
  page: Page,
  async activate(context: any) {
    context.registerCommand('getPanelData', async () => ({
      title: 'RSS 订阅',
      summary: '0',
      items: [{ title: '暂无未读', icon: '📡' }],
      actions: [{ label: '打开', command: 'open' }],
    }))
    context.registerCommand('getPageData', async () => ({}))
    context.registerCommand('open', async () => { context.openPage('rss') })
  },
  deactivate() {},
}
