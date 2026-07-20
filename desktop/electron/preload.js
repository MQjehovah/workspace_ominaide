const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  getConfig: () => ipcRenderer.invoke('get-config'),
  saveConfig: (config) => ipcRenderer.invoke('save-config', config),
  selectFolder: () => ipcRenderer.invoke('select-folder'),
  startSync: (config) => ipcRenderer.invoke('start-sync', config),
  stopSync: () => ipcRenderer.invoke('stop-sync'),
  getSyncStatus: () => ipcRenderer.invoke('get-sync-status'),
  onSyncStatus: (callback) => ipcRenderer.on('sync-status', (e, status) => callback(status)),
  onSyncEvent: (callback) => ipcRenderer.on('sync-event', (e, event) => callback(event)),
  onUnauthorized: (callback) => ipcRenderer.on('sync-unauthorized', () => callback()),
  openExternal: (url) => ipcRenderer.invoke('open-external', url)
})
