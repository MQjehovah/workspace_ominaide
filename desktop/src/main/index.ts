import { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, shell, protocol, net, session } from 'electron'
import { join, resolve } from 'path'
import { existsSync, readFileSync } from 'fs'
import { initPlugins, getProcessManager, setPluginEnabled } from './plugin/host'
import { registerIpcHandlers } from './ipc'
import { setupShortcut } from './shortcut'
import { startSync, stopSync } from './sync/syncWorker'
import { startSettingsSync, stopSettingsSync } from './sync/settingsSync'
import { getConfig } from './config'
import { openPluginWindow, closeAllPluginWindows } from './windows/plugin-window'
import { registerMcpIpc } from './mcp/ipc'
import { initMcpManager, disposeAll } from './mcp/mcp-manager'
import { registerUpdaterIpc } from './updater'
import { setHandoffHandler } from './backendChannel'

protocol.registerSchemesAsPrivileged([
  { scheme: 'local-file', privileges: { bypassCSP: true, stream: true, supportFetchAPI: true } },
  { scheme: 'plugin-app', privileges: { bypassCSP: true, stream: true, supportFetchAPI: true, standard: true, secure: true, media: true } },
])

let mainPanel: BrowserWindow | null = null
let loginWindow: BrowserWindow | null = null
let searchWindow: BrowserWindow | null = null
let quickCaptureWindow: BrowserWindow | null = null
let tray: Tray | null = null
let isQuitting = false

const preloadPath = join(__dirname, '../preload/index.js')

function createRenderer(view: string, opts: { width: number; height: number; frame?: boolean; transparent?: boolean; resizable?: boolean }) {
  const win = new BrowserWindow({
    width: opts.width,
    height: opts.height,
    resizable: opts.resizable ?? false,
    frame: opts.frame ?? false,
    transparent: opts.transparent ?? false,
    icon: join(__dirname, '../../assets/icon.png'),
    show: false,
    webPreferences: { preload: preloadPath, contextIsolation: true, nodeIntegration: false },
  })
  const url = process.env.VITE_DEV_SERVER_URL
    ? `${process.env.VITE_DEV_SERVER_URL}?view=${view}`
    : `file://${join(__dirname, '../../dist/index.html').replace(/\\/g, '/')}?view=${view}`
  win.loadURL(url)
  win.once('ready-to-show', () => win.show())
  return win
}

function showLogin() {
  if (loginWindow) { loginWindow.focus(); return }
  loginWindow = createRenderer('login', { width: 340, height: 260 })
  loginWindow.on('closed', () => { loginWindow = null })
}

function showMainPanel() {
  getConfig().then(cfg => {
    if (!cfg.token) {
      if (mainPanel) { mainPanel.hide() }
      showLogin()
      return
    }
    if (loginWindow) { loginWindow.close(); loginWindow = null }
    if (mainPanel) { mainPanel.show(); mainPanel.focus(); return }
    mainPanel = createRenderer('main', { width: 300, height: 600 })
    mainPanel.on('closed', () => { mainPanel = null })
    startSync()
  })
}

setHandoffHandler((msg) => {
  showMainPanel()
  const send = () => {
    try { mainPanel?.webContents.send('cognition:handoff', msg) } catch { /* ignore */ }
  }
  if (mainPanel && !mainPanel.webContents.isLoading()) send()
  else mainPanel?.webContents.once('did-finish-load', send)
})

function showQuickCapture() {
  getConfig().then(cfg => {
    if (!cfg.token) { showLogin(); return }
    if (quickCaptureWindow) {
      quickCaptureWindow.show()
      quickCaptureWindow.focus()
      return
    }
    quickCaptureWindow = createRenderer('quick-capture', {
      width: 560, height: 320, resizable: false,
    })
    quickCaptureWindow.setAlwaysOnTop(true, 'floating')
    quickCaptureWindow.setSkipTaskbar(true)
    quickCaptureWindow.center()
    quickCaptureWindow.on('closed', () => { quickCaptureWindow = null })
  })
}

function showSearchWindow() {
  getConfig().then(cfg => {
    if (!cfg.token) { showLogin(); return }
    if (searchWindow) { searchWindow.close(); searchWindow = null; return }
    searchWindow = createRenderer('search', { width: 640, height: 400, transparent: true })
  searchWindow.on('blur', () => { searchWindow?.close(); searchWindow = null })
  searchWindow.on('closed', () => { searchWindow = null })
  searchWindow.setAlwaysOnTop(true, 'floating')
  searchWindow.setSkipTaskbar(true)
  })
}

function createTray() {
  const isMac = process.platform === 'darwin'
  const iconPath = isMac
    ? join(__dirname, '../../assets/trayTemplate.png')
    : join(__dirname, '../../assets/tray-icon.png')
  const icon = nativeImage.createFromPath(iconPath)
  if (isMac) icon.setTemplateImage(true)
  tray = new Tray(icon)
  tray.setToolTip('OmniAide')
  const contextMenu = Menu.buildFromTemplate([
    { label: '打开 OmniAide', click: showMainPanel },
    { label: '快速记录', click: showQuickCapture },
    { type: 'separator' },
    { label: '退出', click: () => { isQuitting = true; app.quit() } },
  ])
  tray.setContextMenu(contextMenu)
  tray.on('click', showMainPanel)
}

app.whenReady().then(async () => {
  app.setName('OmniAide')
  if (process.platform === 'darwin' && app.dock) {
    app.dock.setIcon(join(__dirname, '../../assets/icon.png'))
  }
  session.defaultSession.setPermissionRequestHandler((_wc, _permission, callback) => callback(true))
  session.defaultSession.setPermissionCheckHandler(() => true)
  protocol.handle('local-file', (request) => {
    const filePath = decodeURIComponent(request.url.replace('local-file://', ''))
    return net.fetch(`file://${filePath}`)
  })

  // Plugin app protocol — serves plugin frontend files from local disk
  // URL format: plugin-app://{pluginId}/{path}
  // Example:    plugin-app://assistant/index.html
  protocol.handle('plugin-app', (request) => {
    const url = new URL(request.url)
    const pluginId = url.hostname
    const filePath = url.pathname.replace(/^\//, '') || 'index.html'
    const searchPaths = [
      join(__dirname, '../../../plugins', pluginId, 'frontend', filePath),
      join(__dirname, '../../plugins', pluginId, 'frontend', filePath),
      join(app.getPath('userData'), 'plugins', pluginId, 'frontend', filePath),
      join(process.resourcesPath, 'plugins', pluginId, 'frontend', filePath),
    ]
    for (const p of searchPaths) {
      if (existsSync(p)) {
        return net.fetch(`file://${resolve(p).replace(/\\/g, '/')}`)
      }
    }
    return new Response('Plugin frontend not found', { status: 404 })
  })
  registerIpcHandlers()
  registerMcpIpc()
  registerUpdaterIpc()
  initMcpManager()
  await initPlugins()
  createTray()
  const cfg = await getConfig()
  const shortcutCallbacks = {
    search: showSearchWindow,
    toggle: showMainPanel,
    quickCapture: showQuickCapture,
  }
  await setupShortcut(shortcutCallbacks)
  if (cfg.token) {
    startSettingsSync(async (changed) => {
      if (changed.shortcut || changed.customShortcuts) {
        await setupShortcut(shortcutCallbacks)
      }
      if (changed.disabledPlugins) {
        const before = new Set<string>(changed.disabledPlugins.from || [])
        const after = new Set<string>(changed.disabledPlugins.to || [])
        for (const id of before) {
          if (!after.has(id)) await setPluginEnabled(id, true)
        }
        for (const id of after) {
          if (!before.has(id)) await setPluginEnabled(id, false)
        }
      }
    })
  }
  if (cfg.token) {
    const { startBackendChannel } = await import('./backendChannel')
    startBackendChannel().catch(() => {})
    showMainPanel()
  } else {
    showLogin()
  }
})

ipcMain.handle('sync:restart', async () => { try { await startSync() } catch (e: any) { console.error('[sync] restart error:', e.message) }; return { success: true } })

ipcMain.handle('window:quit', () => { isQuitting = true; app.quit() })

app.on('window-all-closed', () => {})
app.on('before-quit', () => {
  isQuitting = true
  stopSettingsSync()
  getProcessManager().stopAll()
  closeAllPluginWindows()
  disposeAll().catch(() => {})
  try { (require('./backendChannel') as any)?.stopBackendChannel?.() } catch { /* ignore */ }
})

ipcMain.handle('window:open-main', () => showMainPanel())

ipcMain.handle('window:open-page', async (_, pluginId: string, query: string = '') => {
  const cfg = await getConfig()
  if (!cfg.token) return
  const win = new BrowserWindow({
    width: 900, height: 700,
    webPreferences: { preload: preloadPath, contextIsolation: true },
  })
  const extra = query ? '&' + query : ''
  const url = process.env.VITE_DEV_SERVER_URL
    ? `${process.env.VITE_DEV_SERVER_URL}?view=plugin-page&pluginId=${pluginId}${extra}`
    : `file://${join(__dirname, '../../dist/index.html').replace(/\\/g, '/')}?view=plugin-page&pluginId=${pluginId}${extra}`
  win.loadURL(url)
})

ipcMain.handle('window:open-plugin-window', async (_, pluginId: string, query: string = '') => {
  const cfg = await getConfig()
  if (!cfg.token) return
  openPluginWindow(pluginId, query)
})

ipcMain.handle('window:move-relative', (event, dx: number, dy: number) => {
  const win = BrowserWindow.fromWebContents(event.sender)
  if (win) { const [x, y] = win.getPosition(); const [w, h] = win.getSize(); win.setBounds({ x: x + dx, y: y + dy, width: w, height: h }) }
})

ipcMain.handle('window:get-bounds', (event) => {
  const win = BrowserWindow.fromWebContents(event.sender)
  if (win) return win.getBounds()
  return null
})

ipcMain.handle('window:set-bounds', (event, bounds: { x: number; y: number }) => {
  const win = BrowserWindow.fromWebContents(event.sender)
  if (win) { const [w, h] = win.getSize(); win.setBounds({ x: bounds.x, y: bounds.y, width: w, height: h }) }
})

ipcMain.handle('window:resize', (event, w: number, h: number) => {
  const win = BrowserWindow.fromWebContents(event.sender)
  if (win) { const [x, y] = win.getPosition(); win.setBounds({ x, y, width: w, height: h }) }
})

ipcMain.handle('shell:open', (_, url: string) => shell.openExternal(url))
