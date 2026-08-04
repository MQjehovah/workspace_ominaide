import { join } from 'path'
import { app, clipboard, BrowserWindow, Notification, shell, dialog, desktopCapturer, screen } from 'electron'
import { existsSync } from 'fs'
import { Low } from 'lowdb'
import axios from 'axios'
import { getConfig, setConfig } from '../config'
import * as screenshot from '../screenshot'
import { showEditor } from '../pinWindow'
import { writeLog } from '../logger'
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
          if (!win.isDestroyed()) win.webContents.send('panel:updated', 'clipboard-history')
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

  proc.registerBridgeHandler('log:write', async ([level, message]) => {
    writeLog(proc.pluginId, level, message)
  })

  proc.registerBridgeHandler('api:get', async ([path]) => {
    const cfg = await getConfig()
    const res = await axios.get(`${cfg.serverUrl || 'http://localhost:8000'}/api${path}`, {
      headers: { Authorization: 'Bearer ' + (cfg.token || '') },
      timeout: 15000,
    })
    return res.data
  })

  proc.registerBridgeHandler('api:post', async ([path, body]) => {
    const cfg = await getConfig()
    try {
      const res = await axios.post(`${cfg.serverUrl || 'http://localhost:8000'}/api${path}`, body, {
        headers: { Authorization: 'Bearer ' + (cfg.token || ''), 'Content-Type': 'application/json' },
        timeout: 15000,
      })
      return res.data
    } catch (e: any) {
      throw new Error(e.response?.data?.detail || e.response?.data || e.message)
    }
  })

  proc.registerBridgeHandler('api:put', async ([path, body]) => {
    const cfg = await getConfig()
    const res = await axios.put(`${cfg.serverUrl || 'http://localhost:8000'}/api${path}`, body, {
      headers: { Authorization: 'Bearer ' + (cfg.token || ''), 'Content-Type': 'application/json' },
      timeout: 15000,
    })
    return res.data
  })

  proc.registerBridgeHandler('api:delete', async ([path]) => {
    const cfg = await getConfig()
    const res = await axios.delete(`${cfg.serverUrl || 'http://localhost:8000'}/api${path}`, {
      headers: { Authorization: 'Bearer ' + (cfg.token || '') },
      timeout: 15000,
    })
    return res.data
  })

  proc.registerBridgeHandler('shell:openPath', async ([path]) => {
    writeLog(proc.pluginId, 'debug', `shell:openPath called: ${String(path)}`)
    const result = await shell.openPath(path)
    writeLog(proc.pluginId, 'debug', `shell:openPath result: ${String(result)}`)
    return result
  })
  proc.registerBridgeHandler('shell:openExternal', async ([url]) => shell.openExternal(url))
  proc.registerBridgeHandler('shell:exec', async ([command, args]) => {
    const { spawn } = require('child_process')
    writeLog(proc.pluginId, 'debug', `shell:exec called: ${String(command)} ${JSON.stringify(args || [])}`)
    try {
      const child = spawn(command, args || [], { detached: true, stdio: 'ignore', windowsHide: true })
      child.on('error', () => {})
      child.unref()
      return { ok: true }
    } catch (e: any) {
      writeLog(proc.pluginId, 'debug', `shell:exec error: ${e.message}`)
      return { ok: false, error: e.message }
    }
  })
  proc.registerBridgeHandler('dialog:showOpenDialog', async ([opts]) => dialog.showOpenDialog(opts))

  // BOM-tolerant JSON adapter: strip UTF-8 BOM on read, write without BOM.
  const jsonAdapter = (file: string) => ({
    async read(): Promise<any> {
      try {
        const raw = require('fs').readFileSync(file, 'utf-8').replace(/^\uFEFF/, '')
        return raw.trim() ? JSON.parse(raw) : {}
      } catch {
        return {}
      }
    },
    async write(data: any): Promise<void> {
      const { mkdirSync } = require('fs')
      const { dirname } = require('path')
      mkdirSync(dirname(file), { recursive: true })
      require('fs').writeFileSync(file, JSON.stringify(data, null, 2), 'utf-8')
    },
  })

  proc.registerBridgeHandler('storage:get', async ([key]) => {
    const file = join(app.getPath('userData'), 'plugin-data', `${proc.pluginId}.json`)
    const adapter = jsonAdapter(file)
    const db = new Low(adapter as any, {})
    await db.read()
    return (db.data as any)?.[key]
  })

  proc.registerBridgeHandler('storage:set', async ([key, value]) => {
    const file = join(app.getPath('userData'), 'plugin-data', `${proc.pluginId}.json`)
    const adapter = jsonAdapter(file)
    const db = new Low(adapter as any, {})
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

  proc.registerBridgeHandler('remote:open-connection', async ([hostDeviceId, viewerId]) => {
    console.log('[remote] open-connection window:', { hostDeviceId, viewerId })
    const preloadPath = join(__dirname, '../preload/index.js')
    const display = screen.getPrimaryDisplay().workArea
    const win = new BrowserWindow({
      width: 280, height: 40, show: false, frame: false, resizable: false,
      alwaysOnTop: true, skipTaskbar: true,
      x: display.width - 290, y: display.height - 50,
      webPreferences: { preload: preloadPath, contextIsolation: true, nodeIntegration: false },
    })
    const query = `mode=webrtc-accept${viewerId ? '&viewer=' + viewerId : ''}`
    const url = `plugin-app://remote/index.html?${query}`
    win.loadURL(url)
    win.once('ready-to-show', () => win.show())
    win.on('closed', () => win.destroy())
  })

  // Forward remote WS messages from plugin to App.vue (and disconnect)
  proc.registerBridgeHandler('remote:ws-connect', async ([data]) => {
    console.log('[host] remote:ws-connect signal received', data?.deviceId)
    BrowserWindow.getAllWindows().forEach(win => {
      if (!win.isDestroyed()) win.webContents.send('remote:ws-connect', data)
    })
  })
  proc.registerBridgeHandler('remote:ws-send', async ([data]) => {
    console.log('[host] remote:ws-send: type=' + (data?.type))
    BrowserWindow.getAllWindows().forEach(win => {
      if (!win.isDestroyed()) win.webContents.send('remote:ws-send', data)
    })
  })
  proc.registerBridgeHandler('remote:ws-disconnect', async () => {
    console.log('[host] remote:ws-disconnect')
    BrowserWindow.getAllWindows().forEach(win => {
      if (!win.isDestroyed()) win.webContents.send('remote:ws-disconnect')
    })
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
  proc.registerBridgeHandler('clipboard:readText', async () => {
    return clipboard.readText()
  })
  proc.registerBridgeHandler('shell:showItemInFolder', async ([path]) => {
    shell.showItemInFolder(path)
  })
  proc.registerBridgeHandler('panel:updated', async () => {
    BrowserWindow.getAllWindows().forEach(win => {
      if (!win.isDestroyed()) win.webContents.send('panel:updated', proc.pluginId)
    })
  })

  // PTY (pseudo-terminal) for interactive AI sessions
  const ptySessions = new Map<string, any>()
  let ptyCounter = 0

  proc.registerBridgeHandler('pty:create', async ([cmd, cmdArgs, cwd]) => {
    try {
      const { execSync } = require('child_process')
      const isWin = process.platform === 'win32'
      const pty = require('node-pty')
      const id = `pty_${proc.pluginId}_${++ptyCounter}`
      const rows = 30, cols = 120

      // On Windows, wrap in cmd.exe to resolve .cmd/.bat scripts correctly
      const spawnCmd = isWin ? 'cmd.exe' : cmd
      const spawnArgs = isWin ? ['/c', cmd, ...(cmdArgs || [])] : (cmdArgs || [])

      const term = pty.spawn(spawnCmd, spawnArgs, {
        name: 'xterm-color', cols, rows, cwd: cwd || process.cwd(),
        env: { ...process.env, TERM: 'xterm-256color' },
      })
      let output = ''
      term.onData((data: string) => { output += data })
      ptySessions.set(id, { term, read: () => { const o = output; output = ''; return o } })
      term.onExit(() => { output = ''; ptySessions.delete(id) })
      return { id, rows, cols }
    } catch (e: any) {
      return { error: e.message || String(e) }
    }
  })

  proc.registerBridgeHandler('pty:write', async ([id, data]) => {
    const s = ptySessions.get(id)
    if (!s) return { error: 'no session' }
    s.term.write(data)
    return { success: true }
  })

  proc.registerBridgeHandler('pty:read', async ([id]) => {
    const s = ptySessions.get(id)
    if (!s) return { output: '', done: true }
    return { output: s.read(), done: false }
  })

  proc.registerBridgeHandler('pty:kill', async ([id]) => {
    const s = ptySessions.get(id)
    if (s) { s.term.kill(); ptySessions.delete(id) }
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
      if (!win.isDestroyed()) win.webContents.send('panel:updated', 'clipboard-history')
    })
  }

  const playerReadonlyCommands = ['getPanelData', 'getPageData', 'cloudGetStreamUrl', 'cloudListPlaylists', 'cloudListSongs', 'cloudListAudioFiles']
  if (pluginId === 'player' && !playerReadonlyCommands.includes(command)) {
    BrowserWindow.getAllWindows().forEach(win => {
      if (!win.isDestroyed()) win.webContents.send('panel:updated', 'player')
    })
  }

  const todoReadonlyCommands = ['getPanelData', 'getPageData']
  if (pluginId === 'todo' && !todoReadonlyCommands.includes(command)) {
    BrowserWindow.getAllWindows().forEach(win => {
      if (!win.isDestroyed()) win.webContents.send('panel:updated', 'todo')
    })
  }

  return result
}

export function getPluginPage(pluginId: string): any {
  return null
}
