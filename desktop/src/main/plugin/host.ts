import { join } from 'path'
import { app, clipboard, BrowserWindow, Notification, shell, dialog, desktopCapturer, screen } from 'electron'
import { existsSync, mkdirSync } from 'fs'
import { Low } from 'lowdb'
import { JSONFile } from 'lowdb/node'
import axios from 'axios'
import { getConfig, setConfig } from '../config'
import * as screenshot from '../screenshot'
import { showEditor } from '../pinWindow'
import type { PluginInfo, PluginPanel, SearchProvider } from '../../shared/types'
import { loadPlugins } from './loader'
import { PluginProcessManager } from './child-process'

const processManager = new PluginProcessManager()
const plugins = new Map<string, PluginInfo>()
const panels: PluginPanel[] = []

export function getProcessManager(): PluginProcessManager {
  return processManager
}

export async function initPlugins() {
  const loaded = loadPlugins()

  for (const [id, info] of loaded) {
    try {
      const modulePath = join(info.path, info.manifest.main || 'dist/index.js')
      if (!existsSync(modulePath)) {
        console.warn(`[plugin] ${id}: main entry not found at ${modulePath}, skipping`)
        continue
      }

      const proc = await processManager.startPlugin(info)
      registerBridgeHandlers(proc)

      const ready = await proc.waitForReady(8000)
      if (!ready) {
        console.warn(`[plugin] ${id}: not ready, will still add panel`)
        proc.on('stderr', (msg: string) => console.error(`[plugin:${id}]`, msg))
      }

      plugins.set(id, info)
      const hasPage = existsSync(join(info.path, 'frontend', 'index.html'))
      panels.push({ id: `${id}-panel`, pluginId: id, height: 120, hasPage })
      console.log(`[plugin] started in child process: ${info.manifest.id} (${info.manifest.version})`)
    } catch (e) {
      console.error(`[plugin] failed to start ${id}:`, e)
    }
  }

  startClipboardMonitoring()
}

export async function reloadNewPlugins(): Promise<string[]> {
  const loaded = loadPlugins()
  const started: string[] = []

  for (const [id, info] of loaded) {
    if (plugins.has(id)) continue

    try {
      const modulePath = join(info.path, info.manifest.main || 'dist/index.js')
      if (!existsSync(modulePath)) {
        console.warn(`[plugin] ${id}: main entry not found at ${modulePath}, skipping`)
        continue
      }

      const proc = await processManager.startPlugin(info)
      registerBridgeHandlers(proc)

      const ready = await proc.waitForReady(8000)
      if (!ready) {
        console.warn(`[plugin] ${id}: not ready, will still add panel`)
        proc.on('stderr', (msg: string) => console.error(`[plugin:${id}]`, msg))
      }

      plugins.set(id, info)
      const hasPage = existsSync(join(info.path, 'frontend', 'index.html'))
      panels.push({ id: `${id}-panel`, pluginId: id, height: 120, hasPage })
      console.log(`[plugin] hot-loaded: ${info.manifest.id} (${info.manifest.version})`)
      started.push(id)
    } catch (e) {
      console.error(`[plugin] failed to hot-load ${id}:`, e)
    }
  }

  if (started.length > 0) {
    BrowserWindow.getAllWindows().forEach(win => {
      if (!win.isDestroyed()) win.webContents.send('plugins:updated')
    })
  }

  return started
}

let lastClipboardText = ''
function startClipboardMonitoring() {
  setInterval(async () => {
    try {
      const text = clipboard.readText()
      if (text && text !== lastClipboardText) {
        lastClipboardText = text

        BrowserWindow.getAllWindows().forEach(win => {
          if (!win.isDestroyed()) win.webContents.send('clipboard:updated')
        })

        const proc = processManager.getProcess('clipboard-history')
        if (proc) {
          proc.executeCommand('onClipboardChange', text).catch(() => {})
        }
      }
    } catch {}
  }, 500)
}

function registerBridgeHandlers(proc: import('./child-process').PluginChildProcess): void {
  const store = { db: null as Low<any> | null }

  proc.registerBridgeHandler('api:get', async ([path]) => {
    const cfg = await getConfig()
    const res = await axios.get(`${cfg.serverUrl || 'http://localhost:8000'}/api${path}`, {
      headers: { Authorization: 'Bearer ' + (cfg.token || '') }
    })
    return res.data
  })

  proc.registerBridgeHandler('api:post', async ([path, body]) => {
    const cfg = await getConfig()
    const res = await axios.post(`${cfg.serverUrl || 'http://localhost:8000'}/api${path}`, body, {
      headers: { Authorization: 'Bearer ' + (cfg.token || ''), 'Content-Type': 'application/json' }
    })
    return res.data
  })

  proc.registerBridgeHandler('api:put', async ([path, body]) => {
    const cfg = await getConfig()
    const res = await axios.put(`${cfg.serverUrl || 'http://localhost:8000'}/api${path}`, body, {
      headers: { Authorization: 'Bearer ' + (cfg.token || ''), 'Content-Type': 'application/json' }
    })
    return res.data
  })

  proc.registerBridgeHandler('api:delete', async ([path]) => {
    const cfg = await getConfig()
    const res = await axios.delete(`${cfg.serverUrl || 'http://localhost:8000'}/api${path}`, {
      headers: { Authorization: 'Bearer ' + (cfg.token || '') }
    })
    return res.data
  })

  proc.registerBridgeHandler('shell:openPath', async ([path]) => shell.openPath(path))
  proc.registerBridgeHandler('shell:openExternal', async ([url]) => shell.openExternal(url))

  proc.registerBridgeHandler('storage:get', async ([key]) => {
    const file = join(app.getPath('userData'), 'plugin-data', `${proc.pluginId}.json`)
    mkdirSync(join(app.getPath('userData'), 'plugin-data'), { recursive: true })
    const adapter = new JSONFile(file)
    const db = new Low(adapter, {})
    await db.read()
    return (db.data as any)?.[key]
  })

  proc.registerBridgeHandler('storage:set', async ([key, value]) => {
    const file = join(app.getPath('userData'), 'plugin-data', `${proc.pluginId}.json`)
    mkdirSync(join(app.getPath('userData'), 'plugin-data'), { recursive: true })
    const adapter = new JSONFile(file)
    const db = new Low(adapter, {})
    await db.read()
    ;(db.data as any)[key] = value
    await db.write()
  })

  proc.registerBridgeHandler('config:get', async ([key]) => {
    const cfg = await getConfig()
    return (cfg as any)?.[key]
  })

  proc.registerBridgeHandler('notification:show', async ([title, body]) => {
    new Notification({ title, body }).show()
  })

  proc.registerBridgeHandler('screenshot:start', async () => { screenshot.startScreenshot() })
  proc.registerBridgeHandler('screenshot:capture-fullscreen', async () => screenshot.captureFullscreen())
  proc.registerBridgeHandler('screenshot:show-editor', async ([dataUrl]) => showEditor(dataUrl))
  proc.registerBridgeHandler('screenshot:get-history', async () => screenshot.getHistory())
  proc.registerBridgeHandler('screenshot:clear-history', async () => screenshot.clearHistory())
  proc.registerBridgeHandler('screenshot:delete-history', async ([id]) => screenshot.deleteFromHistory(id))

  proc.registerBridgeHandler('remote:get-sources', async () => {
    const sources = await desktopCapturer.getSources({
      types: ['screen'], fetchWindowIcons: false, thumbnailSize: { width: 1, height: 1 }
    })
    return sources.map(s => ({ id: s.id, name: s.name, display_id: (s as any).display_id }))
  })

  proc.registerBridgeHandler('remote:screen-size', async () => {
    const d = screen.getPrimaryDisplay()
    const sf = d.scaleFactor || 1
    return { width: Math.round(d.bounds.width * sf), height: Math.round(d.bounds.height * sf) }
  })

  proc.registerBridgeHandler('remote:get-all-displays', async () =>
    screen.getAllDisplays().map(d => ({
      id: d.id, name: `${d.bounds.width}x${d.bounds.height}`,
      bounds: { x: d.bounds.x, y: d.bounds.y, width: d.bounds.width, height: d.bounds.height },
      scaleFactor: d.scaleFactor || 1,
    }))
  )

  proc.registerBridgeHandler('remote:open-connection', async ([roomId]) => {
    console.log('[remote] open-connection window for room:', roomId)
    const preloadPath = join(__dirname, '../preload/index.js')
    const display = screen.getPrimaryDisplay().workArea
    const win = new BrowserWindow({
      width: 280, height: 120, show: false, frame: false, resizable: false,
      alwaysOnTop: true, skipTaskbar: true,
      x: display.width - 290, y: display.height - 130,
      webPreferences: { preload: preloadPath, contextIsolation: true, nodeIntegration: false },
    })
    const url = `plugin-app://remote/index.html?mode=webrtc-accept&room=${roomId}`
    win.loadURL(url)
    win.once('ready-to-show', () => win.show())
    win.on('closed', () => win.destroy())
  })

  proc.registerBridgeHandler('openPage', async ([pluginId, query]) => {
    const preloadPath = join(__dirname, '../preload/index.js')
    const win = new BrowserWindow({
      width: 900, height: 700,
      webPreferences: { preload: preloadPath, contextIsolation: true },
    })
    const extra = query ? '?' + query : ''
    const url = process.env.VITE_DEV_SERVER_URL
      ? `${process.env.VITE_DEV_SERVER_URL}?view=plugin-page&pluginId=${pluginId}${extra}`
      : `file://${join(__dirname, '../../../dist/index.html').replace(/\\/g, '/')}?view=plugin-page&pluginId=${pluginId}${extra}`
    win.loadURL(url)
  })

  // Electron proxy handlers (child process require('electron') bridge)
  const winMap = new Map<string, BrowserWindow>()

  proc.registerBridgeHandler('BrowserWindow:create', async ([opts]) => {
    // Create window but don't return it to child (child has stub)
    const preloadPath = join(__dirname, '../preload/index.js')
    const win = new BrowserWindow({
      ...opts,
      webPreferences: { ...opts.webPreferences, preload: preloadPath, contextIsolation: true },
    })
    return null // child doesn't use return value
  })
  proc.registerBridgeHandler('BrowserWindow:loadURL', async ([url]) => {})
  proc.registerBridgeHandler('BrowserWindow:show', async () => {})
  proc.registerBridgeHandler('BrowserWindow:focus', async () => {})
  proc.registerBridgeHandler('BrowserWindow:hide', async () => {})
  proc.registerBridgeHandler('BrowserWindow:close', async () => {})
  proc.registerBridgeHandler('BrowserWindow:setAlwaysOnTop', async () => {})
  proc.registerBridgeHandler('BrowserWindow:setSkipTaskbar', async () => {})
  proc.registerBridgeHandler('globalShortcut:register', async ([accelerator]) => {
    const { globalShortcut } = require('electron')
    globalShortcut.register(accelerator, () => {
      proc.executeCommand('toggleAssistant').catch(() => {})
    })
  })
  proc.registerBridgeHandler('globalShortcut:unregister', async ([accelerator]) => {
    const { globalShortcut } = require('electron')
    globalShortcut.unregister(accelerator)
  })
  proc.registerBridgeHandler('globalShortcut:unregisterAll', async () => {
    const { globalShortcut } = require('electron')
    globalShortcut.unregisterAll()
  })
  proc.registerBridgeHandler('clipboard:writeText', async ([text]) => {
    clipboard.writeText(text)
  })
  proc.registerBridgeHandler('shell:showItemInFolder', async ([path]) => {
    shell.showItemInFolder(path)
  })
}

export function removePlugin(id: string): boolean {
  const proc = processManager.getProcess(id)
  if (proc) {
    proc.stop()
    processManager.stopPlugin(id)
  }
  // remove from panels array
  const idx = panels.findIndex(p => p.pluginId === id)
  if (idx >= 0) panels.splice(idx, 1)
  return plugins.delete(id)
}

export function getPlugins(): PluginInfo[] {
  return Array.from(plugins.values())
}

export function getPanels(): PluginPanel[] {
  return panels
}

export function getSearchProviders(): Array<SearchProvider & { pluginId: string }> {
  const providers: Array<SearchProvider & { pluginId: string }> = []
  for (const [id] of plugins) {
    const proc = processManager.getProcess(id)
    if (proc && proc.searchProviders) {
      for (const p of proc.searchProviders as any[]) {
        providers.push({ ...p, pluginId: id })
      }
    }
  }
  return providers
}

export async function executeCommand(pluginId: string, command: string, args?: unknown): Promise<unknown> {
  const proc = processManager.getProcess(pluginId)
  if (!proc) throw new Error(`Plugin ${pluginId} not running`)
  const result = await proc.executeCommand(command, args)

  if (pluginId === 'clipboard-history' && command === 'copy') {
    BrowserWindow.getAllWindows().forEach(win => {
      if (!win.isDestroyed()) win.webContents.send('clipboard:updated')
    })
  }

  const playerReadonlyCommands = ['getPanelData', 'getPageData', 'cloudGetStreamUrl', 'cloudListPlaylists', 'cloudListSongs', 'cloudListAudioFiles']
  if (pluginId === 'player' && !playerReadonlyCommands.includes(command)) {
    BrowserWindow.getAllWindows().forEach(win => {
      if (!win.isDestroyed()) win.webContents.send('player:updated')
    })
  }

  const todoReadonlyCommands = ['getPanelData', 'getPageData']
  if (pluginId === 'todo' && !todoReadonlyCommands.includes(command)) {
    BrowserWindow.getAllWindows().forEach(win => {
      if (!win.isDestroyed()) win.webContents.send('todo:updated')
    })
  }

  return result
}

export function getPluginPage(pluginId: string): any {
  return null
}
