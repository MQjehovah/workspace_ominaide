import { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, globalShortcut, shell } from 'electron'
import { join } from 'path'
import { initPlugins, getPlugins, executeCommand } from './plugin/host'
import { registerIpcHandlers } from './ipc'

let mainWindow: BrowserWindow | null = null
let searchWindow: BrowserWindow | null = null
let tray: Tray | null = null
let isQuitting = false

function createWindow(view: string = 'main') {
  const win = new BrowserWindow({
    width: view === 'search' ? 640 : 380,
    height: view === 'search' ? 400 : 600,
    resizable: false,
    frame: false,
    transparent: view === 'search',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  if (process.env.VITE_DEV_SERVER_URL) {
    win.loadURL(`${process.env.VITE_DEV_SERVER_URL}?view=${view}`)
  } else {
    win.loadFile(join(__dirname, '../../dist/index.html'), { query: { view } })
  }
  return win
}

function showMainWindow() {
  if (mainWindow) { mainWindow.show(); return }
  mainWindow = createWindow('main')
  mainWindow.on('closed', () => { mainWindow = null })
}

function showSearchWindow() {
  if (searchWindow) { searchWindow.show(); return }
  searchWindow = createWindow('search')
  searchWindow.on('blur', () => { searchWindow?.close(); searchWindow = null })
  searchWindow.on('closed', () => { searchWindow = null })
}

function createTray() {
  const icon = nativeImage.createEmpty()
  tray = new Tray(icon)
  tray.setToolTip('OmniAide')
  const contextMenu = Menu.buildFromTemplate([
    { label: '打开 OmniAide', click: showMainWindow },
    { type: 'separator' },
    { label: '退出', click: () => { isQuitting = true; app.quit() } },
  ])
  tray.setContextMenu(contextMenu)
  tray.on('click', showMainWindow)
}

app.whenReady().then(async () => {
  registerIpcHandlers()
  await initPlugins()
  createTray()
  showMainWindow()

  globalShortcut.register('Alt+Space', showSearchWindow)
})

app.on('window-all-closed', () => {})
app.on('before-quit', () => { isQuitting = true })

ipcMain.handle('window:open-page', (_, pluginId) => {
  const win = new BrowserWindow({
    width: 900, height: 700,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
    },
  })
  const url = process.env.VITE_DEV_SERVER_URL
    ? `${process.env.VITE_DEV_SERVER_URL}?view=plugin-page&pluginId=${pluginId}`
    : `file://${join(__dirname, '../../dist/index.html')}?view=plugin-page&pluginId=${pluginId}`
  win.loadURL(url)
})

ipcMain.handle('shell:open', (_, url: string) => shell.openExternal(url))
