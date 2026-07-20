import type { PluginModule, PluginContext } from '../../../src/shared/types'

export default {
  async activate(context: PluginContext) {
    context.registerCommand('getPanelData', async () => {
      try {
        const data = await context.api.get('/plugins/notes/tree')
        return { notes: data || [], count: (data || []).length }
      } catch { return { notes: [], count: 0 } }
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
