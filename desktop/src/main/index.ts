import { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, shell, protocol, net, session } from 'electron'
import { join, resolve } from 'path'
import { existsSync, readFileSync } from 'fs'
import { initPlugins, getProcessManager } from './plugin/host'
import { registerIpcHandlers } from './ipc'
import { setupShortcut } from './shortcut'
import { startSync, stopSync } from './sync/syncWorker'
import { getConfig } from './config'
import { openPluginWindow, closeAllPluginWindows } from './windows/plugin-window'

protocol.registerSchemesAsPrivileged([
  { scheme: 'local-file', privileges: { bypassCSP: true, stream: true, supportFetchAPI: true } },
  { scheme: 'plugin-app', privileges: { bypassCSP: true, stream: true, supportFetchAPI: true, standard: true, secure: true } },
])

let mainPanel: BrowserWindow | null = null
let loginWindow: BrowserWindow | null = null
let searchWindow: BrowserWindow | null = null
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
  const icon = nativeImage.createFromPath(join(__dirname, '../../assets/tray-icon.png'))
  tray = new Tray(icon)
  tray.setToolTip('OmniAide')
  const contextMenu = Menu.buildFromTemplate([
    { label: '打开 OmniAide', click: showMainPanel },
    { type: 'separator' },
    { label: '退出', click: () => { isQuitting = true; app.quit() } },
  ])
  tray.setContextMenu(contextMenu)
  tray.on('click', showMainPanel)
}

app.whenReady().then(async () => {
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
  await initPlugins()
  createTray()
  const cfg = await getConfig()
  await setupShortcut({ search: showSearchWindow, toggle: showMainPanel })
  if (cfg.token) {
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
  getProcessManager().stopAll()
  closeAllPluginWindows()
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

ipcMain.handle('window:move-relative', (_, dx: number, dy: number) => {
  const win = BrowserWindow.getFocusedWindow()
  if (win) { const [x, y] = win.getPosition(); win.setPosition(x + dx, y + dy) }
})

ipcMain.handle('window:resize', (_, w: number, h: number) => {
  const win = BrowserWindow.getFocusedWindow()
  if (win) win.setSize(w, h)
})

ipcMain.handle('shell:open', (_, url: string) => shell.openExternal(url))
