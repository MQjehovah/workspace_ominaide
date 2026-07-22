import type { PluginModule, PluginContext } from '../../../src/shared/types'

export default {
  async activate(context: PluginContext) {
    context.registerCommand('getPanelData', async () => {
      try {
        const data = await context.api.get('/plugins/notes/tree') || []
        const notesArr = Array.isArray(data) ? data : []
        return {
          title: '笔记',
          subtitle: `${notesArr.length} 篇笔记`,
          items: notesArr.slice(0, 5).map((n: any) => ({
            title: n.title || n.name || '无标题',
            subtitle: n.updated_at ? new Date(n.updated_at).toLocaleDateString() : '',
            action: 'open',
            actionArgs: { id: n.id },
          })),
          buttons: [{ label: '新建', command: 'create' }],
        }
      } catch { return { title: '笔记', subtitle: '0 篇笔记', buttons: [{ label: '新建', command: 'create' }] } }
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
