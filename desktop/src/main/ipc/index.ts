import axios from 'axios'
import { ipcMain, BrowserWindow } from 'electron'
import { join } from 'path'
import { getPlugins, getPanels, getSearchProviders, executeCommand, getPluginPage } from '../plugin/host'
import { setAuth } from '../plugin/sandbox'
import { getConfig, setConfig } from '../config'
import { getCustomShortcuts, addCustomShortcut, removeCustomShortcut, getBuiltinShortcuts, updateBuiltinShortcut } from '../shortcut'

export function registerIpcHandlers() {
  // Config
  ipcMain.handle('config:get', async (_, key: string) => (await getConfig())?.[key])
  ipcMain.handle('config:set', async (_, key: string, value: any) => setConfig(key, value))

  // Auth
  ipcMain.handle('auth:set', (_, serverUrl: string, token: string) => setAuth(serverUrl, token))

  // Plugin management
  ipcMain.handle('plugin:list', () => getPlugins())
  ipcMain.handle('plugin:get-panels', () => getPanels())
  ipcMain.handle('plugin:get-page', (_, pluginId: string) => ({ pluginId, hasPage: !!getPluginPage(pluginId) }))
  ipcMain.handle('plugin:execute', async (_, pluginId: string, command: string, args?: unknown) => {
    try { return await executeCommand(pluginId, command, args) }
    catch (e) { return { error: (e as Error).message } }
  })

  // Shortcuts
  ipcMain.handle('shortcut:list', async () => getCustomShortcuts())
  ipcMain.handle('shortcut:add', async (_, binding: any) => addCustomShortcut(binding))
  ipcMain.handle('shortcut:remove', async (_, accelerator: string) => removeCustomShortcut(accelerator))
  ipcMain.handle('shortcut:get-builtin', async () => getBuiltinShortcuts())
  ipcMain.handle('shortcut:update-builtin', async (_, key: string, accelerator: string) => updateBuiltinShortcut(key, accelerator))

  // Search
  ipcMain.handle('search:plugin', async (_, keyword: string, query: string) => {
    const providers = getSearchProviders()
    const results: any[] = []
    for (const p of providers) {
      if (keyword && p.keyword !== keyword) continue
      if (!keyword && p.keyword !== '') continue
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
  ipcMain.handle('api:get', async (_, path: string) => {
    const c = await getConfig()
    const res = await axios.get(`${c.serverUrl || 'http://localhost:8000'}/api${path}`, { headers: { Authorization: 'Bearer ' + (c.token || '') } })
    return res.data
  })
  ipcMain.handle('api:post', async (_, path: string, body?: any) => {
    const c = await getConfig()
    const res = await axios.post(`${c.serverUrl || 'http://localhost:8000'}/api${path}`, body, { headers: { Authorization: 'Bearer ' + (c.token || '') } })
    return res.data
  })
  ipcMain.handle('api:put', async (_, path: string, body?: any) => {
    const c = await getConfig()
    const res = await axios.put(`${c.serverUrl || 'http://localhost:8000'}/api${path}`, body, { headers: { Authorization: 'Bearer ' + (c.token || '') } })
    return res.data
  })
  ipcMain.handle('api:delete', async (_, path: string) => {
    const c = await getConfig()
    const res = await axios.delete(`${c.serverUrl || 'http://localhost:8000'}/api${path}`, { headers: { Authorization: 'Bearer ' + (c.token || '') } })
    return res.data
  })

  // Window
  ipcMain.handle('window:open-search', () => {
    const searchWin = new BrowserWindow({
      width: 640, height: 400, resizable: false, frame: false, transparent: true,
      webPreferences: { preload: join(__dirname, '../preload/index.js'), contextIsolation: true },
    })
    searchWin.loadURL('file://' + join(__dirname, '../../dist/index.html').replace(/\\/g, '/') + '?view=search')
    searchWin.on('blur', () => searchWin.close())
  })
  ipcMain.handle('window:open-plugin-manager', () => {
    const win = new BrowserWindow({
      width: 560, height: 480, frame: false, resizable: false, show: false,
      webPreferences: { preload: join(__dirname, '../preload/index.js'), contextIsolation: true },
    })
    win.loadURL('file://' + join(__dirname, '../../dist/index.html').replace(/\\/g, '/') + '?view=plugin-manager')
    win.once('ready-to-show', () => win.show())
  })
  ipcMain.handle('window:hide', () => {
    BrowserWindow.getFocusedWindow()?.hide()
  })

  ipcMain.handle('shell:open-external', (_, url: string) => {
    const { shell } = require('electron')
    shell.openExternal(url)
  })
}
