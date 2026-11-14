import type { PluginModule, PluginContext } from '../../../src/shared/types'

interface HistoryItem {
  content: string
  time: number
  pinned?: boolean
  hits?: number
}

const MAX_ITEMS = 200
const MAX_AGE_DAYS = 30
const STORAGE_KEY = 'history'

let history: HistoryItem[] = []
let pluginCtx: PluginContext | null = null
let persistTimer: any = null

function sortHistory() {
  history.sort((a, b) => {
    const pin = Number(!!b.pinned) - Number(!!a.pinned)
    return pin !== 0 ? pin : b.time - a.time
  })
}

function prune() {
  const cutoff = Date.now() - MAX_AGE_DAYS * 86400000
  history = history.filter(item => item.pinned || item.time >= cutoff)
  // Keep pinned items plus the newest MAX_ITEMS unpinned entries.
  let unpinned = 0
  history = history.filter(item => {
    if (item.pinned) return true
    unpinned += 1
    return unpinned <= MAX_ITEMS
  })
  sortHistory()
}

function persistSoon() {
  if (persistTimer) clearTimeout(persistTimer)
  persistTimer = setTimeout(() => {
    persistTimer = null
    const write = pluginCtx?.storage?.set(STORAGE_KEY, { items: history, savedAt: Date.now() })
    if (write) write.catch(() => {})
  }, 250)
}

async function loadHistory() {
  try {
    const raw: any = await pluginCtx?.storage?.get(STORAGE_KEY)
    const items = Array.isArray(raw) ? raw : raw?.items
    if (Array.isArray(items)) {
      history = items
        .filter((item: any) => item && typeof item.content === 'string' && item.content.trim())
        .map((item: any) => ({
          content: String(item.content),
          time: Number(item.time) || Date.now(),
          pinned: !!item.pinned,
          hits: Number(item.hits) || 1,
        }))
    }
  } catch {
    history = []
  }
  prune()
}

function notifyPanelUpdated() {
  const signal = pluginCtx?.signal('panel:updated')
  if (signal) signal.catch(() => {})
}

function formatTime(timestamp: number) {
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now.getTime() - timestamp
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:${date.getMinutes().toString().padStart(2, '0')}`
}

export default {
  panel: undefined,
  page: undefined,

  async activate(context: PluginContext) {
    pluginCtx = context
    await loadHistory()

    context.registerCommand('getPanelData', async () => {
      const pinned = history.filter(item => item.pinned)
      const recent = history.filter(item => !item.pinned)
      const preview = [...pinned, ...recent].slice(0, 5)
      return {
        title: '剪贴板历史',
        subtitle: `${history.length} 条${pinned.length ? ` · ${pinned.length} 条已固定` : ''}`,
        items: preview.map(item => ({
          title: item.content.length > 40 ? item.content.slice(0, 40) + '…' : item.content,
          subtitle: formatTime(item.time) + (item.pinned ? ' · 已固定' : ''),
          action: 'copy',
          actionArgs: { content: item.content },
          icon: item.pinned ? '📌' : undefined,
        })),
        buttons: [{ label: '打开历史', command: 'open' }],
      }
    })

    context.registerCommand('getPageData', async () => ({
      history,
      stats: {
        total: history.length,
        pinned: history.filter(item => item.pinned).length,
        maxItems: MAX_ITEMS,
        maxAgeDays: MAX_AGE_DAYS,
      },
    }))

    context.registerCommand('open', async () => {
      context.openPage('clipboard-history')
    })

    context.registerCommand('copy', async (args: any) => {
      const content = String(args?.content || '')
      if (!content || !context.clipboard) return { success: false }
      try {
        await context.clipboard.writeText(content)
        const existing = history.find(item => item.content === content)
        if (existing) {
          existing.time = Date.now()
          existing.hits = (existing.hits || 1) + 1
          sortHistory()
          persistSoon()
        }
        context.notification?.show?.('已复制', content.slice(0, 50))
        notifyPanelUpdated()
        return { success: true }
      } catch {
        return { success: false }
      }
    })

    context.registerCommand('pin', async (args: any) => {
      const content = String(args?.content || '')
      const item = history.find(entry => entry.content === content)
      if (!item) return { success: false }
      item.pinned = args?.pinned !== undefined ? !!args.pinned : !item.pinned
      sortHistory()
      persistSoon()
      notifyPanelUpdated()
      return { success: true, pinned: !!item.pinned }
    })

    context.registerCommand('delete', async (args: any) => {
      const content = String(args?.content || '')
      const before = history.length
      history = history.filter(item => item.content !== content)
      if (history.length === before) return { success: false }
      persistSoon()
      notifyPanelUpdated()
      return { success: true }
    })

    context.registerCommand('clear', async () => {
      // Keep pinned entries: "clear" should not silently discard things the
      // user explicitly saved.
      const kept = history.filter(item => item.pinned)
      const removed = history.length - kept.length
      history = kept
      sortHistory()
      persistSoon()
      notifyPanelUpdated()
      context.notification?.show?.('已清空', `移除了 ${removed} 条未固定记录`)
      return { success: true, removed, kept: kept.length }
    })

    context.registerCommand('clearAll', async () => {
      const removed = history.length
      history = []
      persistSoon()
      notifyPanelUpdated()
      context.notification?.show?.('已清空', `移除了 ${removed} 条记录`)
      return { success: true, removed }
    })

    context.registerCommand('onClipboardChange', async (raw: unknown) => {
      const content = String(raw || '')
      if (!content || content.length > 10000) return
      const existing = history.find(item => item.content === content)
      if (existing) {
        existing.time = Date.now()
        existing.hits = (existing.hits || 1) + 1
      } else {
        history.unshift({ content, time: Date.now(), pinned: false, hits: 1 })
      }
      prune()
      persistSoon()
    })
  },

  deactivate() {
    if (persistTimer) clearTimeout(persistTimer)
    const write = pluginCtx?.storage?.set(STORAGE_KEY, { items: history, savedAt: Date.now() })
    if (write) write.catch(() => {})
  },
} as PluginModule
