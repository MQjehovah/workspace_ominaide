import Panel from './Panel.vue'
import Page from './Page.vue'

export default {
  panel: Panel,
  page: Page,
  async activate(context: any) {
    context.registerCommand('getPanelData', async () => {
      let items: any[] = []
      try {
        const r = await context.api.get('/rss/entries?unread=true&page_size=5')
        items = r?.items || []
      } catch {}
      return {
        title: '资讯',
        subtitle: items.length > 0 ? `${items.length} 条未读` : '暂无未读',
        items: items.slice(0, 5).map((e: any) => ({
          title: e.title,
          subtitle: e.feed_title || '',
        })),
      }
    })
    context.registerCommand('getPageData', async () => ({}))
    context.registerCommand('open', async () => { context.openPage('rss') })
  },
  deactivate() {},
}
