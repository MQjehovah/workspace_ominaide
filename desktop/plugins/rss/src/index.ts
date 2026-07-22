import Panel from './Panel.vue'
import Page from './Page.vue'

export default {
  panel: Panel,
  page: Page,
  async activate(context: any) {
    context.registerCommand('getPanelData', async () => ({
      title: 'RSS 订阅',
      subtitle: '暂无未读',
    }))
    context.registerCommand('getPageData', async () => ({}))
    context.registerCommand('open', async () => { context.openPage('rss') })
  },
  deactivate() {},
}
