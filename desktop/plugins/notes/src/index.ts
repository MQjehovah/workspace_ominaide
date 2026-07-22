import type { PluginModule, PluginContext } from '../../../src/shared/types'

export default {
  async activate(context: PluginContext) {
    context.registerCommand('getPanelData', async () => {
      try {
        const data = await context.api.get('/plugins/notes/tree') || []
        const count = Array.isArray(data) ? data.length : 0
        return {
          title: '笔记',
          summary: count,
          statusText: `${count} 篇笔记`,
          items: (Array.isArray(data) ? data : []).slice(0, 5).map((n: any) => ({
            title: n.title || n.name || '无标题',
            subtitle: n.updated_at ? new Date(n.updated_at).toLocaleDateString() : '',
            icon: '📝',
          })),
          actions: [{ label: '新建', command: 'create' }],
        }
      } catch { return { title: '笔记', summary: 0, items: [], actions: [{ label: '新建', command: 'create' }] } }
    })

    context.registerCommand('getPageData', async () => {
      try {
        const data = await context.api.get('/plugins/notes')
        return { notes: data || [] }
      } catch { return { notes: [] } }
    })
  },
  deactivate() {},
} as PluginModule
