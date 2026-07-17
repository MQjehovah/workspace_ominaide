const { app, BrowserWindow, Tray, Menu, ipcMain, nativeImage, dialog } = require('electron')
const path = require('path')
const { SyncEngine } = require('./sync-engine')
const Store = require('electron-store')

const store = new Store()
let mainWindow = null
let tray = null
let syncEngine = null

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 500,
    height: 600,
    resizable: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    },
    icon: path.join(__dirname, '..', 'assets', 'icon.png')
  })
  mainWindow.loadFile(path.join(__dirname, '..', 'renderer', 'index.html'))
  mainWindow.on('close', (e) => {
    if (!app.isQuitting) {
      e.preventDefault()
      mainWindow.hide()
    }
  })
}

function createTray() {
  const icon = nativeImage.createEmpty()
  tray = new Tray(icon)
  tray.setToolTip('OmniAide Sync')
  updateTrayMenu('disconnected')
  tray.on('click', () => {
    if (mainWindow) mainWindow.show()
  })
}

function updateTrayMenu(status) {
  const icons = {
    connected: path.join(__dirname, '..', 'assets', 'tray-connected.png'),
    disconnected: path.join(__dirname, '..', 'assets', 'tray-disconnected.png'),
    syncing: path.join(__dirname, '..', 'assets', 'tray-syncing.png'),
    conflict: path.join(__dirname, '..', 'assets', 'tray-conflict.png')
  }
  
  const contextMenu = Menu.buildFromTemplate([
    { label: '打开 OmniAide', click: () => mainWindow.show() },
    { type: 'separator' },
    { label: `状态: ${status}`, enabled: false },
    { type: 'separator' },
    { label: '退出', click: () => { app.isQuitting = true; app.quit() } }
  ])
  tray.setContextMenu(contextMenu)
}

// IPC handlers
ipcMain.handle('get-config', () => {
  return store.get('config', { serverUrl: 'http://localhost:8000', token: '', workspaceId: null, localPath: '' })
})

ipcMain.handle('save-config', (event, config) => {
  store.set('config', config)
  return true
})

ipcMain.handle('select-folder', async () => {
  const result = await dialog.showOpenDialog({ properties: ['openDirectory'] })
  if (!result.canceled && result.filePaths.length > 0) {
    return result.filePaths[0]
  }
  return null
})

ipcMain.handle('start-sync', async (event, config) => {
  store.set('config', config)
  if (syncEngine) syncEngine.stop()
  syncEngine = new SyncEngine()
  syncEngine.onStatusChange = (status) => {
    updateTrayMenu(status)
    if (mainWindow) mainWindow.webContents.send('sync-status', status)
  }
  syncEngine.onEvent = (event) => {
    if (mainWindow) mainWindow.webContents.send('sync-event', event)
  }
  await syncEngine.start(config)
  return true
})

ipcMain.handle('stop-sync', () => {
  if (syncEngine) syncEngine.stop()
  syncEngine = null
  updateTrayMenu('disconnected')
  return true
})

ipcMain.handle('get-sync-status', () => {
  if (syncEngine) return syncEngine.getStatus()
  return { status: 'disconnected', pendingEvents: 0 }
})

app.whenReady().then(() => {
  createWindow()
  createTray()
})

app.on('window-all-closed', () => {})
app.on('activate', () => { mainWindow?.show() })
