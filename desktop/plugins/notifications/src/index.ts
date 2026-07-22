import Panel from './Panel.vue'
import Page from './Page.vue'

export default {
  panel: Panel,
  page: Page,
  async activate(context: any) {
    context.registerCommand('getPanelData', async () => ({
      title: '通知',
      summary: '0',
      items: [{ title: '暂无新通知', icon: '🔔' }],
      actions: [{ label: '查看', command: 'open' }],
    }))
    context.registerCommand('getPageData', async () => ({}))
    context.registerCommand('open', async () => { context.openPage('notifications') })
  },
  deactivate() {},
}
