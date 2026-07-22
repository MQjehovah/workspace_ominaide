import { contextBridge, ipcRenderer } from 'electron'

const clipboardListeners: (() => void)[] = []
const playerListeners: (() => void)[] = []
const todoListeners: (() => void)[] = []
const pluginListeners: (() => void)[] = []

ipcRenderer.on('clipboard:updated', () => {
  clipboardListeners.forEach(fn => fn())
})

ipcRenderer.on('player:updated', () => {
  playerListeners.forEach(fn => fn())
})

ipcRenderer.on('todo:updated', () => {
  todoListeners.forEach(fn => fn())
})

ipcRenderer.on('plugins:updated', () => {
  pluginListeners.forEach(fn => fn())
})

contextBridge.exposeInMainWorld('mqbox', {
  plugin: {
    list: () => ipcRenderer.invoke('plugin:list'),
    listAll: () => ipcRenderer.invoke('plugin:list-all'),
    getPanels: () => ipcRenderer.invoke('plugin:get-panels'),
    getPage: (pluginId: string) => ipcRenderer.invoke('plugin:get-page', pluginId),
    execute: (pluginId: string, command: string, args?: unknown) =>
      ipcRenderer.invoke('plugin:execute', pluginId, command, args),
    setEnabled: (pluginId: string, enabled: boolean) =>
      ipcRenderer.invoke('plugin:set-enabled', pluginId, enabled),
    importPlugin: () =>
      ipcRenderer.invoke('plugin:import'),
    listMarketplace: () =>
      ipcRenderer.invoke('plugin:list-marketplace'),
    installFromMarket: (pluginId: string) =>
      ipcRenderer.invoke('plugin:install-from-market', pluginId),
    onUpdated: (callback: () => void) => {
      pluginListeners.push(callback)
    },
  },
  search: {
    plugin: (keyword: string, query: string) => ipcRenderer.invoke('search:plugin', keyword, query),
    getProviders: () => ipcRenderer.invoke('search:get-providers'),
  },
  config: {
    get: (key: string) => ipcRenderer.invoke('config:get', key),
    set: (key: string, value: any) => ipcRenderer.invoke('config:set', key, value),
  },
  shortcut: {
    list: () => ipcRenderer.invoke('shortcut:list'),
    add: (binding: any) => ipcRenderer.invoke('shortcut:add', binding),
    remove: (accelerator: string) => ipcRenderer.invoke('shortcut:remove', accelerator),
    getBuiltin: () => ipcRenderer.invoke('shortcut:get-builtin'),
    updateBuiltin: (key: string, accelerator: string) => ipcRenderer.invoke('shortcut:update-builtin', key, accelerator),
  },
  window: {
    openMain: () => ipcRenderer.invoke('window:open-main'),
    openPage: (pluginId: string, query?: string) => ipcRenderer.invoke('window:open-page', pluginId, query || ''),
    openSearch: () => ipcRenderer.invoke('window:open-search'),
    openPluginManager: () => ipcRenderer.invoke('window:open-plugin-manager'),
    hide: () => ipcRenderer.invoke('window:hide'),
    quit: () => ipcRenderer.invoke('window:quit'),
  },
  clipboard: {
    onUpdated: (callback: () => void) => {
      clipboardListeners.push(callback)
    },
    writeImage: (dataUrl: string) => ipcRenderer.invoke('clipboard:write-image', dataUrl),
  },
  player: {
    onUpdated: (callback: () => void) => {
      playerListeners.push(callback)
    },
  },
  todo: {
    onUpdated: (callback: () => void) => {
      todoListeners.push(callback)
    },
  },
  shell: {
    openExternal: (url: string) => ipcRenderer.invoke('shell:open-external', url),
    openUrl: (url: string, name: string) => ipcRenderer.invoke('file:open-url', url, name),
  },
  dialog: {
    selectFolder: () => ipcRenderer.invoke('dialog:select-folder'),
  },
  sync: {
    restart: () => ipcRenderer.invoke('sync:restart'),
  },
  screenshot: {
    onImage: (callback: (dataUrl: string) => void) => {
      ipcRenderer.on('screenshot-editor:set-image', (_, dataUrl: string) => callback(dataUrl))
    },
    getAllScreens: () => ipcRenderer.invoke('screenshot:get-all-screens'),
    capture: (x: number, y: number, width: number, height: number) =>
      ipcRenderer.invoke('screenshot:capture', x, y, width, height),
    captureFullscreen: () => ipcRenderer.invoke('screenshot:capture-fullscreen'),
    start: () => ipcRenderer.send('screenshot:start'),
    cancel: () => ipcRenderer.send('screenshot:cancel'),
    showEditor: (dataUrl: string) => ipcRenderer.send('screenshot:show-editor', dataUrl),
    pin: (dataUrl: string) => ipcRenderer.send('screenshot:pin', dataUrl),
    pinClose: () => ipcRenderer.send('screenshot:pin-close'),
    save: (dataUrl: string) => ipcRenderer.send('screenshot:save', dataUrl),
    closeEditor: () => ipcRenderer.send('screenshot:close-editor'),
    closeAllPins: () => ipcRenderer.send('screenshot:close-all-pins'),
    getHistory: () => ipcRenderer.invoke('screenshot:get-history'),
    deleteHistory: (id: string) => ipcRenderer.invoke('screenshot:delete-history', id),
    clearHistory: () => ipcRenderer.invoke('screenshot:clear-history'),
  },
  api: {
    get: (path: string) => ipcRenderer.invoke('api:get', path),
    post: (path: string, body?: any) => ipcRenderer.invoke('api:post', path, body),
    put: (path: string, body?: any) => ipcRenderer.invoke('api:put', path, body),
    delete: (path: string) => ipcRenderer.invoke('api:delete', path),
  },
  remote: {
    getDesktopSources: () => ipcRenderer.invoke('remote:get-sources'),
    getScreenSize: () => ipcRenderer.invoke('remote:screen-size'),
    injectInput: (event: any) => ipcRenderer.invoke('remote:inject', event),
    onControlRequest: (cb: (info: any) => void) => {
      ipcRenderer.on('remote:control-request', (_e, info) => cb(info))
    },
  },
})
