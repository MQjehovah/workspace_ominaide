import axios from 'axios'
import { ipcMain, BrowserWindow } from 'electron'
import { join } from 'path'
import { app } from 'electron'
import { Low } from 'lowdb'
import { JSONFile } from 'lowdb/node'
import { getPlugins, getPanels, getSearchProviders, executeCommand, getPluginPage } from '../plugin/host'
import { setAuth } from '../plugin/sandbox'

const configFile = join(app.getPath('userData'), 'config.json')
const adapter = new JSONFile<Record<string, any>>(configFile)
const configDb = new Low(adapter, {})

export function registerIpcHandlers() {
  // Config
  ipcMain.handle('config:get', async (_, key: string) => {
    await configDb.read()
    return configDb.data?.[key]
  })
  ipcMain.handle('config:set', async (_, key: string, value: any) => {
    await configDb.read()
    configDb.data![key] = value
    await configDb.write()
  })

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

  // API proxy
  const getApiConfig = async () => {
    await configDb.read()
    return { serverUrl: configDb.data?.serverUrl || 'http://localhost:8000', token: configDb.data?.token || '' }
  }
  ipcMain.handle('api:get', async (_, path: string) => {
    const c = await getApiConfig()
    const res = await axios.get(`${c.serverUrl}/api${path}`, { headers: { Authorization: 'Bearer ' + c.token } })
    return res.data
  })
  ipcMain.handle('api:post', async (_, path: string, body?: any) => {
    const c = await getApiConfig()
    const res = await axios.post(`${c.serverUrl}/api${path}`, body, { headers: { Authorization: 'Bearer ' + c.token } })
    return res.data
  })
  ipcMain.handle('api:put', async (_, path: string, body?: any) => {
    const c = await getApiConfig()
    const res = await axios.put(`${c.serverUrl}/api${path}`, body, { headers: { Authorization: 'Bearer ' + c.token } })
    return res.data
  })
  ipcMain.handle('api:delete', async (_, path: string) => {
    const c = await getApiConfig()
    const res = await axios.delete(`${c.serverUrl}/api${path}`, { headers: { Authorization: 'Bearer ' + c.token } })
    return res.data
  })

  // Window
  ipcMain.handle('window:hide', () => {
    const win = BrowserWindow.getFocusedWindow()
    win?.hide()
  })
}
