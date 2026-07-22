import Panel from './Panel.vue'
import Page from './Page.vue'

export default {
  panel: Panel,
  page: Page,
  async activate(context: any) {
    context.registerCommand('getPanelData', async () => ({
      title: '日程管理',
      summary: '0',
      items: [{ title: '暂无日程', icon: '📅' }],
      actions: [{ label: '打开', command: 'open' }],
    }))
    context.registerCommand('getPageData', async () => ({}))
    context.registerCommand('open', async () => { context.openPage('schedule') })
  },
  deactivate() {},
}
