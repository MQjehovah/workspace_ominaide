import { ipcMain, BrowserWindow } from 'electron'
import { getPlugins, getPanels, getSearchProviders, executeCommand, getPluginPage } from '../plugin/host'
import { setAuth } from '../plugin/sandbox'

export function registerIpcHandlers() {
  // Auth
  ipcMain.handle('auth:set', (_, serverUrl: string, token: string) => {
    setAuth(serverUrl, token)
  })

  // Plugin
  ipcMain.handle('plugin:list', () => getPlugins())
  ipcMain.handle('plugin:get-panels', () => getPanels())
  ipcMain.handle('plugin:get-page', (_, pluginId: string) => {
    const page = getPluginPage(pluginId)
    return page ? { pluginId, hasPage: true } : null
  })
  ipcMain.handle('plugin:execute', async (_, pluginId: string, command: string, args?: unknown) => {
    try { return await executeCommand(pluginId, command, args) }
    catch (e) { return { error: (e as Error).message } }
  })

  // Search
  ipcMain.handle('search:plugin', async (_, keyword: string, query: string) => {
    const providers = getSearchProviders()
    const results: any[] = []
    for (const p of providers) {
      if (keyword && p.keyword !== keyword) continue
      try {
        const res = await Promise.race([
          Promise.resolve(p.onSearch(query)),
          new Promise<[]>((_, reject) => setTimeout(() => reject([]), 2000)),
        ])
        results.push(...res)
      } catch {}
      if (results.length >= 20) break
    }
    return results.slice(0, 20)
  })
  ipcMain.handle('search:get-providers', () => getSearchProviders().map(p => ({ keyword: p.keyword, name: p.name, priority: p.priority })))

  // Window
  ipcMain.handle('window:hide', () => {
    const win = BrowserWindow.getFocusedWindow()
    win?.hide()
  })
}
