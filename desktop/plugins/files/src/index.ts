import type { PluginModule, PluginContext } from '../../../src/shared/types'

export default {
  async activate(context: PluginContext) {
    context.registerCommand('getPanelData', async () => {
      try {
        const data = await context.api.get('/files?page_size=5')
        return { recentFiles: data?.files?.filter((f: any) => !f.is_folder) || [], total: data?.total || 0 }
      } catch { return { recentFiles: [], total: 0 } }
    })

    context.registerCommand('getPageData', async () => {
      try {
        const data = await context.api.get('/files?page_size=100')
        return { files: data?.files || [], total: data?.total || 0 }
      } catch { return { files: [], total: 0 } }
    })
  },
  deactivate() {},
} as PluginModule
