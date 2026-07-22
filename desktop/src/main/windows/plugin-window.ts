import { BrowserWindow } from 'electron'
import { join } from 'path'

const preloadPath = join(__dirname, '../preload/index.js')
const windows = new Map<string, BrowserWindow>()

export function openPluginWindow(pluginId: string, query: string = ''): void {
  const qs = query ? (query.startsWith('?') ? query : '?' + query) : ''
  const url = `plugin-app://${pluginId}/index.html${qs}`

  // Viewer mode → always create a new window
  if (query) {
    const win = new BrowserWindow({
      width: 1024, height: 740, minWidth: 680, minHeight: 500, show: false, autoHideMenuBar: true,
      webPreferences: { preload: preloadPath, contextIsolation: true, nodeIntegration: false },
    })
    win.loadURL(url)
    win.once('ready-to-show', () => win.show())
    win.on('closed', () => { /* viewer windows are ephemeral */ })
    return
  }

  // Main page → reuse existing window
  const existing = windows.get(pluginId)
  if (existing && !existing.isDestroyed()) {
    existing.focus()
    return
  }

  const win = new BrowserWindow({
    width: 1024, height: 740, minWidth: 680, minHeight: 500, show: false, autoHideMenuBar: true,
    webPreferences: { preload: preloadPath, contextIsolation: true, nodeIntegration: false },
  })

  win.loadURL(url)
  win.once('ready-to-show', () => win.show())
  win.on('closed', () => { windows.delete(pluginId) })

  windows.set(pluginId, win)
}

export function closePluginWindow(pluginId: string): void {
  const win = windows.get(pluginId)
  if (win && !win.isDestroyed()) {
    win.close()
  }
  windows.delete(pluginId)
}

export function closeAllPluginWindows(): void {
  for (const [id] of windows) {
    closePluginWindow(id)
  }
}
