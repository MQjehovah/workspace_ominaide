import type { PluginModule, PluginContext } from '../../../src/shared/types'

async function searchFiles(api: PluginContext['api'], query: string): Promise<any[]> {
  try {
    const data = await api.get(`/files?page_size=30&search=${encodeURIComponent(query)}`)
    const files = data?.files || []
    return files.filter((f: any) => !f.is_folder).map((f: any) => ({
      title: f.original_name,
      subtitle: (f.folder_path || '/') + f.original_name,
      icon: 'file',
    }))
  } catch {
    return []
  }
}

export default {
  async activate(context: PluginContext) {
    context.registerCommand('getPanelData', async () => null)

    context.registerSearchProvider({
      keyword: '',
      name: '文件搜索',
      priority: 100,
      onSearch: async (query: string) => {
        if (!query) return []
        const files = await searchFiles(context.api, query)
        return files.map((f: any) => ({
          title: f.title,
          subtitle: f.subtitle,
          action: 'open',
          actionArgs: f,
          pluginId: 'everything',
        }))
      },
    })
  },
  deactivate() {},
} as PluginModule
