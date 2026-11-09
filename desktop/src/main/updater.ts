import { app, BrowserWindow, ipcMain } from 'electron'
import { autoUpdater } from 'electron-updater'
import { getConfig } from './config'

let configured = false
let lastStatus: Record<string, any> = { status: 'idle' }

function broadcast(status: Record<string, any>) {
  lastStatus = status
  console.log('[updater]', JSON.stringify(status))
  for (const win of BrowserWindow.getAllWindows()) {
    win.webContents.send('update:status', status)
  }
}

async function configureFeed() {
  if (configured) return
  const cfg = await getConfig()
  const base = String(cfg.serverUrl || 'https://mqgeek.com/ominaide').replace(/\/+$/, '')
  autoUpdater.setFeedURL({ provider: 'generic', url: `${base}/api/desktop/releases` })
  autoUpdater.autoDownload = false
  autoUpdater.autoInstallOnAppQuit = true
  configured = true
}

export function registerUpdaterIpc() {
  autoUpdater.on('checking-for-update', () => broadcast({ status: 'checking' }))
  autoUpdater.on('update-available', (info) => broadcast({
    status: 'available',
    version: info.version,
    releaseDate: info.releaseDate,
  }))
  autoUpdater.on('update-not-available', (info) => broadcast({
    status: 'latest',
    version: info.version,
  }))
  autoUpdater.on('download-progress', (progress) => broadcast({
    status: 'downloading',
    percent: Math.round(progress.percent || 0),
    transferred: progress.transferred,
    total: progress.total,
  }))
  autoUpdater.on('update-downloaded', (info) => broadcast({
    status: 'downloaded',
    version: info.version,
  }))
  autoUpdater.on('error', (error) => broadcast({
    status: 'error',
    message: String(error?.message || error),
  }))

  ipcMain.handle('update:info', () => ({
    version: app.getVersion(),
    packaged: app.isPackaged,
    lastStatus,
  }))

  ipcMain.handle('update:check', async () => {
    if (!app.isPackaged) {
      broadcast({ status: 'dev', message: '开发模式下不检查更新' })
      return lastStatus
    }
    try {
      await configureFeed()
      await autoUpdater.checkForUpdates()
    } catch (error: any) {
      broadcast({ status: 'error', message: String(error?.message || error) })
    }
    return lastStatus
  })

  ipcMain.handle('update:download', async () => {
    if (!app.isPackaged) return lastStatus
    try {
      await configureFeed()
      await autoUpdater.downloadUpdate()
    } catch (error: any) {
      broadcast({ status: 'error', message: String(error?.message || error) })
    }
    return lastStatus
  })

  ipcMain.handle('update:install', () => {
    if (!app.isPackaged) return false
    setImmediate(() => autoUpdater.quitAndInstall(false, true))
    return true
  })

  if (app.isPackaged) {
    setTimeout(() => {
      configureFeed()
        .then(() => autoUpdater.checkForUpdates())
        .catch((error) => broadcast({ status: 'error', message: String(error?.message || error) }))
    }, 15_000)
  }
}
