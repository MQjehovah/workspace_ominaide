import Panel from './Panel.vue'
import Page from './Page.vue'

const REFRESH_INTERVAL = 30 * 60 * 1000 // 30 minutes

let refreshTimer: any = null

function relTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const diff = Date.now() - d.getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  if (diff < 7 * 86400000) return `${Math.floor(diff / 86400000)} 天前`
  return `${d.getMonth() + 1}/${d.getDate()}`
}

export default {
  panel: Panel,
  page: Page,
  async activate(context: any) {
    context.registerCommand('getPanelData', async () => {
      let items: any[] = []
      try {
        const r = await context.api.get('/rss/entries?unread=true&page_size=6')
        items = r?.items || []
      } catch {}
      return {
        title: '资讯',
        subtitle: items.length > 0 ? `${items.length} 条新文章` : '暂无新文章',
        items: items.slice(0, 4).map((e: any) => ({
          title: e.title,
          subtitle: `${e.feed_title || '资讯'} · ${relTime(e.published || e.created_at)}`,
        })),
      }
    })
    context.registerCommand('getPageData', async () => ({}))
    context.registerCommand('open', async () => { context.openPage('rss') })

    // Pull new articles from every subscribed feed, so the backend records
    // `article.new` events for the periodic LLM scan to summarize.
    context.registerCommand('refresh', async () => {
      return refreshFeeds(context)
    })

    // 本地定时拉取
    refreshTimer = setInterval(() => {
      refreshFeeds(context).catch(() => {})
    }, REFRESH_INTERVAL)
  },
  deactivate() {
    if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
  },
}

async function refreshFeeds(context: any): Promise<{ newCount: number }> {
  let feeds: any[] = []
  try {
    feeds = (await context.api.get('/rss/feeds')) || []
  } catch { return { newCount: 0 } }
  let newCount = 0
  for (const feed of feeds) {
    try {
      const r = await context.api.post(`/rss/feeds/${feed.id}/fetch`)
      newCount += r?.new_entries || 0
    } catch { /* ignore */ }
  }
  if (newCount > 0) {
    try { await context.signal?.('panel:updated') } catch { /* ignore */ }
  }
  return { newCount }
}
