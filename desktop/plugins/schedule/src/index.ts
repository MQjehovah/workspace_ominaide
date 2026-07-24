import Panel from './Panel.vue'
import Page from './Page.vue'

export default {
  panel: Panel,
  page: Page,
  async activate(context: any) {
    function toLocalISO(d: Date) { return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString() }

    context.registerCommand('getPanelData', async () => {
      const now = new Date()
      const s = new Date(now.getFullYear(), now.getMonth(), 1)
      const e = new Date(now.getFullYear(), now.getMonth() + 1, 1)
      let events: any[] = []
      try {
        const r = await context.api.get(`/schedule?start=${toLocalISO(s)}&end=${toLocalISO(e)}`)
        events = r || []
      } catch {}
      const todayEvents = events.filter((e: any) => {
        const d = new Date(e.start_time)
        return d.getUTCDate() === now.getDate() && d.getUTCMonth() === now.getMonth() && d.getUTCFullYear() === now.getFullYear()
      })
      return {
        title: '日程',
        subtitle: `今日 ${todayEvents.length} 项`,
        items: todayEvents.slice(0, 5).map((e: any) => ({
          title: e.title,
          subtitle: e.start_time ? new Date(e.start_time).toLocaleTimeString('zh-CN', { hour:'2-digit', minute:'2-digit' }) : '',
        })),
      }
    })
    context.registerCommand('getPageData', async () => ({}))
    context.registerCommand('open', async () => { context.openPage('schedule') })
  },
  deactivate() {},
}
