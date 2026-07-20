import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('mqbox', {
  plugin: {
    list: () => ipcRenderer.invoke('plugin:list'),
    getPanels: () => ipcRenderer.invoke('plugin:get-panels'),
    getPage: (pluginId: string) => ipcRenderer.invoke('plugin:get-page', pluginId),
    execute: (pluginId: string, command: string, args?: unknown) =>
      ipcRenderer.invoke('plugin:execute', pluginId, command, args),
  },
  search: {
    plugin: (keyword: string, query: string) =>
      ipcRenderer.invoke('search:plugin', keyword, query),
    getProviders: () => ipcRenderer.invoke('search:get-providers'),
  },
  config: {
    get: (key: string) => ipcRenderer.invoke('config:get', key),
    set: (key: string, value: any) => ipcRenderer.invoke('config:set', key, value),
  },
  window: {
    openPage: (pluginId: string) => ipcRenderer.invoke('window:open-page', pluginId),
    openSearch: () => ipcRenderer.invoke('window:open-search'),
    hide: () => ipcRenderer.invoke('window:hide'),
  },
  api: {
    get: (path: string) => ipcRenderer.invoke('api:get', path),
    post: (path: string, body?: any) => ipcRenderer.invoke('api:post', path, body),
    put: (path: string, body?: any) => ipcRenderer.invoke('api:put', path, body),
    delete: (path: string) => ipcRenderer.invoke('api:delete', path),
  },
})
