const { app, BrowserWindow, Tray, Menu, ipcMain, nativeImage, dialog, shell } = require('electron')
const path = require('path')
const { SyncEngine } = require('./sync-engine')
const Store = require('electron-store')

const store = new Store()
let mainWindow = null
let tray = null
let syncEngine = null

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 680,
    height: 540,
    minWidth: 580,
    minHeight: 400,
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

let trayIcon

function createTrayIcon(color) {
  const size = 16
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
    <circle cx="${size/2}" cy="${size/2}" r="${size/2-1}" fill="${color}" stroke="#fff" stroke-width="0.5"/>
  </svg>`
  const dataUrl = 'data:image/svg+xml;base64,' + Buffer.from(svg).toString('base64')
  return nativeImage.createFromDataURL(dataUrl)
}

const trayColors = {
  connected: '#34C759',
  disconnected: '#FF3B30',
  syncing: '#FF9F0A',
  conflict: '#FF3B30'
}

function createTray() {
  trayIcon = createTrayIcon('#FF3B30')
  tray = new Tray(trayIcon)
  tray.setToolTip('OmniAide')
  updateTrayMenu('disconnected')
  tray.on('click', () => {
    if (mainWindow) mainWindow.show()
  })
}

function updateTrayMenu(status) {
  const color = trayColors[status] || '#FF3B30'
  trayIcon = createTrayIcon(color)
  tray.setImage(trayIcon)
  
  const statusLabels = { connected: '已连接', disconnected: '未连接', syncing: '同步中', connecting: '连接中...' }
  const contextMenu = Menu.buildFromTemplate([
    { label: '打开 OmniAide', click: () => mainWindow.show() },
    { type: 'separator' },
    { label: `状态: ${statusLabels[status] || status}`, enabled: false },
    { type: 'separator' },
    { label: '退出', click: () => { app.isQuitting = true; app.quit() } }
  ])
  tray.setContextMenu(contextMenu)
}

// IPC handlers
ipcMain.handle('get-config', () => {
  return store.get('config', { serverUrl: 'http://localhost:8000', token: '', serverPath: '/', localPath: '' })
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
  syncEngine.onUnauthorized = () => {
    if (mainWindow) mainWindow.webContents.send('sync-unauthorized')
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

ipcMain.handle('open-external', async (event, url) => {
  await shell.openExternal(url)
})

app.whenReady().then(() => {
  createWindow()
  createTray()
})

app.on('window-all-closed', () => {})
app.on('activate', () => { mainWindow?.show() })
