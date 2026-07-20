import { join } from 'path'
import { app, Notification, clipboard, shell } from 'electron'
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
    ? { openExternal: (url: string) => shell.openExternal(url) }
    : null

  const api = {
    get: async (path: string) => {
      const axios = (await import('axios')).default
      const res = await axios.get(`${store.serverUrl}/api${path}`, {
        headers: { Authorization: 'Bearer ' + store.token }
      })
      return res.data
    },
    post: async (path: string, body?: any) => {
      const axios = (await import('axios')).default
      const res = await axios.post(`${store.serverUrl}/api${path}`, body, {
        headers: { Authorization: 'Bearer ' + store.token }
      })
      return res.data
    },
    put: async (path: string, body?: any) => {
      const axios = (await import('axios')).default
      const res = await axios.put(`${store.serverUrl}/api${path}`, body, {
        headers: { Authorization: 'Bearer ' + store.token }
      })
      return res.data
    },
    delete: async (path: string) => {
      const axios = (await import('axios')).default
      const res = await axios.delete(`${store.serverUrl}/api${path}`, {
        headers: { Authorization: 'Bearer ' + store.token }
      })
      return res.data
    },
  }

  const context: PluginContext = {
    plugin: pluginInfo,
    api,
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
