import { BrowserWindow } from 'electron'
import { join } from 'path'

const preloadPath = join(__dirname, '../preload/index.js')
const windows = new Map<string, BrowserWindow>()

export function openPluginWindow(pluginId: string): void {
  const existing = windows.get(pluginId)
  if (existing && !existing.isDestroyed()) {
    existing.focus()
    return
  }

  const win = new BrowserWindow({
    width: 1024,
    height: 740,
    minWidth: 680,
    minHeight: 500,
    show: false,
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  // Load plugin frontend from local disk via custom protocol
  // Falls back to backend URL if needed
  const url = `plugin-app://${pluginId}/index.html`
  win.loadURL(url)

  win.once('ready-to-show', () => win.show())
  win.on('closed', () => {
    windows.delete(pluginId)
  })

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
