import axios from 'axios'
import { join } from 'path'
import { app, Notification, clipboard, shell, BrowserWindow } from 'electron'
import { Low } from 'lowdb'
import { JSONFile } from 'lowdb/node'
import type { PluginInfo, PluginContext } from '../../shared/types'

export function createSandbox(pluginInfo: PluginInfo, commands: Map<string, Function>, searchProviders: any[]) {
  const perms = pluginInfo.manifest.permissions || []

  // Storage API
  let storage: any = null
  if (perms.includes('storage')) {
    const file = join(app.getPath('userData'), 'plugin-data', `${pluginInfo.id}.json`)
    const adapter = new JSONFile(file)
    storage = new Low(adapter, {})
  }

  // Notification API
  const notification = perms.includes('notification')
    ? { show: (title: string, body?: string) => new Notification({ title, body }).show() }
    : null

  // Shell API
  const shellApi = perms.includes('shell')
    ? { openPath: (path: string) => shell.openPath(path), openExternal: (url: string) => shell.openExternal(url) }
    : null

  const api = {
    get: async (path: string) => {
      const res = await axios.get(`${store.serverUrl}/api${path}`, {
        headers: { Authorization: 'Bearer ' + store.token }
      })
      return res.data
    },
    post: async (path: string, body?: any) => {
      const res = await axios.post(`${store.serverUrl}/api${path}`, body, {
        headers: { Authorization: 'Bearer ' + store.token }
      })
      return res.data
    },
    put: async (path: string, body?: any) => {
      const res = await axios.put(`${store.serverUrl}/api${path}`, body, {
        headers: { Authorization: 'Bearer ' + store.token }
      })
      return res.data
    },
    delete: async (path: string) => {
      const res = await axios.delete(`${store.serverUrl}/api${path}`, {
        headers: { Authorization: 'Bearer ' + store.token }
      })
      return res.data
    },
  }

  const context: PluginContext = {
    plugin: pluginInfo,
    api,
    clipboard: perms.includes('clipboard') ? clipboard : null,
    shell: shellApi,
    storage: {
      get: async (key: string) => {
        if (!storage) return null
        await storage.read()
        return (storage.data as any)[key]
      },
      set: async (key: string, value: any) => {
        if (!storage) return
        await storage.read()
        ;(storage.data as any)[key] = value
        await storage.write()
      },
    },
    notification: notification || { show: () => {} },
    openPage: (pluginId: string) => {
      const preloadPath = join(__dirname, '../../preload/index.js')
      const win = new BrowserWindow({
        width: 900, height: 700,
        webPreferences: { preload: preloadPath, contextIsolation: true },
      })
      const url = process.env.VITE_DEV_SERVER_URL
        ? `${process.env.VITE_DEV_SERVER_URL}?view=plugin-page&pluginId=${pluginId}`
        : `file://${join(__dirname, '../../../dist/index.html').replace(/\\/g, '/')}?view=plugin-page&pluginId=${pluginId}`
      win.loadURL(url)
    },
    registerCommand: (name: string, handler: (args: unknown) => Promise<unknown>) => {
      commands.set(name, handler)
    },
    registerSearchProvider: (provider: any) => {
      searchProviders.push(provider)
    },
  }

  return context
}

// Shared store across sandboxes
const store: { serverUrl: string; token: string } = { serverUrl: 'http://localhost:8000', token: '' }

export function setAuth(serverUrl: string, token: string) {
  store.serverUrl = serverUrl
  store.token = token
}
