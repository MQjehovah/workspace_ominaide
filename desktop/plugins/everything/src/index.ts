import * as http from 'http'
import type { PluginModule, PluginContext } from '../../../src/shared/types'

const EVERYTHING_PORT = 26983
const TIMEOUT = 3000

function searchEverything(query: string, maxResults = 20): Promise<any[]> {
  return new Promise((resolve) => {
    const url = `http://127.0.0.1:${EVERYTHING_PORT}/?search=${encodeURIComponent(query)}&json=1&path_column=1&count=${maxResults}`
    
    const req = http.get(url, { timeout: TIMEOUT }, (res) => {
      let data = ''
      res.on('data', (chunk: string) => { data += chunk })
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data)
          const results = parsed.results || []
          resolve(results.slice(0, maxResults).map((item: any) => {
            let fullPath = ''
            let name = ''
            if (Array.isArray(item)) {
              name = item[0] || ''
              const dir = item[1] || ''
              fullPath = dir && name ? `${dir}\\${name}` : name
            } else if (typeof item === 'object') {
              name = item.name || ''
              fullPath = item.path || name
            }
            return { name, path: fullPath, extension: name.includes('.') ? name.split('.').pop() || '' : '' }
          }))
        } catch { resolve([]) }
      })
    })
    req.on('error', () => resolve([]))
    req.on('timeout', () => { req.destroy(); resolve([]) })
  })
}

export default {
  async activate(context: PluginContext) {
    context.registerCommand('getPanelData', async () => null)

    context.registerSearchProvider({
      keyword: '',
      name: '本地搜索',
      priority: 100,
      onSearch: async (query: string) => {
        if (!query) return []
        const files = await searchEverything(query)
        return files.map((f: any) => ({
          title: f.name,
          subtitle: f.path,
          icon: 'file',
          action: 'open',
          actionArgs: { path: f.path },
          pluginId: 'everything',
        }))
      },
    })
  },
  deactivate() {},
} as PluginModule
