import Panel from './Panel.vue'
import Page from './Page.vue'

export default {
  panel: Panel,
  page: Page,
  async activate(context: any) {
    context.registerCommand('getPanelData', async () => ({
      title: '通知',
      subtitle: '暂无新通知',
    }))
    context.registerCommand('getPageData', async () => ({}))
    context.registerCommand('open', async () => { context.openPage('notifications') })
  },
  deactivate() {},
}
