import axios from 'axios'
import { join } from 'path'
import { app, Notification, clipboard, shell, BrowserWindow, dialog, ipcMain, desktopCapturer, screen } from 'electron'
import { readdirSync, statSync, mkdirSync } from 'fs'
import { Low } from 'lowdb'
import { JSONFile } from 'lowdb/node'
import { getConfig, setConfig } from '../config'
import * as screenshot from '../screenshot'
import { showEditor } from '../pinWindow'
import type { PluginInfo, PluginContext, ScreenshotCapability } from '../../shared/types'

export function createSandbox(pluginInfo: PluginInfo, commands: Map<string, Function>, searchProviders: any[]) {
  const perms = pluginInfo.manifest.permissions || []

  // Storage API
  let storage: any = null
  if (perms.includes('storage')) {
    const file = join(app.getPath('userData'), 'plugin-data', `${pluginInfo.id}.json`)
    mkdirSync(join(app.getPath('userData'), 'plugin-data'), { recursive: true })
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

  async function tryRefresh(): Promise<boolean> {
    try {
      const c = await getConfig()
      if (!c.refresh_token) return false
      const res = await axios.post(`${c.serverUrl || 'http://localhost:8000'}/api/auth/refresh`, 
        { refresh_token: c.refresh_token },
        { headers: { Authorization: 'Bearer ' + (c.token || '') } }
      )
      if (res.data?.access_token && res.data?.refresh_token) {
        await setConfig('token', res.data.access_token)
        await setConfig('refresh_token', res.data.refresh_token)
        return true
      }
    } catch {}
    return false
  }

  async function apiFetch(method: 'get' | 'post' | 'put' | 'delete', path: string, body?: any) {
    const c = await getConfig()
    const baseUrl = c.serverUrl || 'http://localhost:8000'
    const headers: any = { Authorization: 'Bearer ' + (c.token || '') }
    if (body && !(body instanceof FormData)) headers['Content-Type'] = 'application/json'
    try {
      const cfg: any = { method, url: `${baseUrl}/api${path}`, headers, data: body }
      const res = await axios(cfg)
      return res.data
    } catch (err: any) {
      if (err?.response?.status === 401) {
        const refreshed = await tryRefresh()
        if (refreshed) {
          const c2 = await getConfig()
          headers.Authorization = 'Bearer ' + (c2.token || '')
          const cfg: any = { method, url: `${baseUrl}/api${path}`, headers, data: body }
          const retry = await axios(cfg)
          return retry.data
        }
        await setConfig('token', '')
        BrowserWindow.getAllWindows().forEach(w => w.close())
      }
      throw err
    }
  }

  const api = {
    get: (path: string) => apiFetch('get', path),
    post: (path: string, body?: any) => apiFetch('post', path, body),
    put: (path: string, body?: any) => apiFetch('put', path, body),
    delete: (path: string) => apiFetch('delete', path),
  }

  // Screenshot API
  const screenshotApi: ScreenshotCapability = perms.includes('screenshot')
    ? {
        start: () => screenshot.startScreenshot(),
        captureFullscreen: () => screenshot.captureFullscreen(),
        showEditor: (dataUrl: string) => showEditor(dataUrl),
        getHistory: () => screenshot.getHistory(),
        clearHistory: () => screenshot.clearHistory(),
        deleteHistory: (id: string) => screenshot.deleteFromHistory(id),
      }
    : null

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
    screenshot: screenshotApi,
    remote: perms.includes('remote') ? {
      getDesktopSources: async () => {
        const sources = await desktopCapturer.getSources({ types: ['screen'], fetchWindowIcons: false, thumbnailSize: { width: 1, height: 1 } })
        return sources.map((s: any) => ({ id: s.id, name: s.name, display_id: s.display_id }))
      },
      getScreenSize: () => {
        const d = screen.getPrimaryDisplay()
        const sf = d.scaleFactor || 1
        return { width: Math.round(d.bounds.width * sf), height: Math.round(d.bounds.height * sf) }
      },
      getAllDisplays: () => screen.getAllDisplays().map((d: any) => ({
        id: d.id,
        name: `${d.bounds.width}x${d.bounds.height}`,
        bounds: { x: d.bounds.x, y: d.bounds.y, width: d.bounds.width, height: d.bounds.height },
        scaleFactor: d.scaleFactor || 1,
      })),
    } : null,
    files: perms.includes('files:read') ? {
      openDirectory: async () => {
        const result = await dialog.showOpenDialog({ properties: ['openDirectory'] })
        return result.canceled ? undefined : result.filePaths[0]
      },
      listAudio: async (dirPath: string) => {
        try {
          const entries = readdirSync(dirPath)
          const audioExts = ['.mp3', '.wav', '.flac', '.ogg', '.m4a', '.wma', '.aac']
          return entries
            .filter(f => {
              const ext = f.toLowerCase().slice(f.lastIndexOf('.'))
              return audioExts.includes(ext)
            })
            .map(f => ({ name: f, path: join(dirPath, f) }))
        } catch { return [] }
      },
    } : null,
    openPage: (pluginId: string, query: string = '') => {
      const preloadPath = join(__dirname, '../../preload/index.js')
      const win = new BrowserWindow({
        width: 900, height: 700,
        webPreferences: { preload: preloadPath, contextIsolation: true },
      })
      const extra = query ? '&' + query : ''
      const url = process.env.VITE_DEV_SERVER_URL
        ? `${process.env.VITE_DEV_SERVER_URL}?view=plugin-page&pluginId=${pluginId}${extra}`
        : `file://${join(__dirname, '../../../dist/index.html').replace(/\\/g, '/')}?view=plugin-page&pluginId=${pluginId}${extra}`
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
