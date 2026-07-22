import Panel from './Panel.vue'
import Page from './Page.vue'

export default {
  panel: Panel,
  page: Page,
  async activate(context: any) {
    context.registerCommand('getPanelData', async () => ({
      title: '日程管理',
      subtitle: '暂无日程',
    }))
    context.registerCommand('getPageData', async () => ({}))
    context.registerCommand('open', async () => { context.openPage('schedule') })
  },
  deactivate() {},
}
