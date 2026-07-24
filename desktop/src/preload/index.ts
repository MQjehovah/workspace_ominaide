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
    uninstall: (pluginId: string) =>
      ipcRenderer.invoke('plugin:uninstall', pluginId),
    listMarketplace: () =>
      ipcRenderer.invoke('plugin:list-marketplace'),
    installFromMarket: (pluginId: string) =>
      ipcRenderer.invoke('plugin:install-from-market', pluginId),
    getPanelData: (pluginId: string) =>
      ipcRenderer.invoke('plugin:get-panel-data', pluginId),
    reload: () =>
      ipcRenderer.invoke('plugin:reload'),
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
    openPluginWindow: (pluginId: string, query?: string) => ipcRenderer.invoke('window:open-plugin-window', pluginId, query || ''),
    openSearch: () => ipcRenderer.invoke('window:open-search'),
    openPluginManager: () => ipcRenderer.invoke('window:open-plugin-manager'),
    hide: () => ipcRenderer.invoke('window:hide'),
    quit: () => ipcRenderer.invoke('window:quit'),
    move: (dx: number, dy: number) => ipcRenderer.invoke('window:move-relative', dx, dy),
    resize: (w: number, h: number) => ipcRenderer.invoke('window:resize', w, h),
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
    // Audio control commands (from Page.vue or any renderer)
    play: (detail?: any) => ipcRenderer.invoke('player:play', { action: 'play', ...(detail || {}) }),
    pause: () => ipcRenderer.invoke('player:play', { action: 'pause' }),
    seek: (time: number) => ipcRenderer.invoke('player:play', { action: 'seek', time }),
    setVolume: (volume: number) => ipcRenderer.invoke('player:play', { action: 'set-volume', volume }),
    setSource: (src: string, autoplay?: boolean) => ipcRenderer.invoke('player:play', { action: 'set-source', src, autoplay }),
    // Listen for control commands from main process (for main window audio)
    onControl: (callback: (detail: any) => void) => {
      ipcRenderer.on('player:control', (_, detail) => callback(detail))
    },
    // Send audio events back to main process (from main window)
    sendEvent: (event: string, data: any) => ipcRenderer.invoke('player:event', event, data),
    // Listen for audio events (for Page.vue and other windows)
    onAudioEvent: (event: string, callback: (data: any) => void) => {
      ipcRenderer.on('player:audio-event', (_, evt: string, data: any) => {
        if (evt === event) callback(data)
      })
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
  log: {
    write: (pluginId: string, level: string, message: string) =>
      ipcRenderer.invoke('log:write', pluginId, level, message),
  },
  remote: {
    getDesktopSources: () => ipcRenderer.invoke('remote:get-sources'),
    getScreenSize: () => ipcRenderer.invoke('remote:screen-size'),
    getAllDisplays: () => ipcRenderer.invoke('remote:get-all-displays'),
    injectInput: (event: any) => ipcRenderer.invoke('remote:inject', event),
    onControlRequest: (cb: (info: any) => void) => {
      ipcRenderer.on('remote:control-request', (_e, info) => cb(info))
    },
    // App.vue 常驻 WS — 接收来自 child process 的信号
    onConnect: (cb: (data: any) => void) => {
      console.log('[preload] register onConnect listener')
      ipcRenderer.on('remote:ws-connect', (_, data) => { console.log('[preload] remote:ws-connect received'); cb(data) })
    },
    // App.vue 直接连接 WS（启动时自动重连）
    connectDirectly: (data: any) => {
      console.log('[preload] connectDirectly')
      // 通过 IPC 发送到主进程，主进程广播给 App.vue
      ipcRenderer.invoke('remote:ws-connect', data)
    },
    onSend: (cb: (data: any) => void) => {
      console.log('[preload] register onSend listener')
      ipcRenderer.on('remote:ws-send', (_, data) => { console.log('[preload] remote:ws-send received, type=' + (data?.type)); cb(data) })
    },
    onDisconnect: (cb: () => void) => {
      console.log('[preload] register onDisconnect listener')
      ipcRenderer.on('remote:ws-disconnect', () => { console.log('[preload] remote:ws-disconnect received'); cb() })
    },
    // App.vue → 广播给所有窗口
    publishSignal: (msg: any) => {
      console.log('[preload] publishSignal:', msg?.type)
      return ipcRenderer.invoke('remote:ws-message', msg)
    },
    publishStatus: (status: string) => {
      console.log('[preload] publishStatus:', status)
      return ipcRenderer.invoke('remote:ws-status', status)
    },
    // 其他窗口监听 WS 信号
    onSignal: (cb: (msg: any) => void) => {
      ipcRenderer.on('remote:ws-signal', (_, msg) => { console.log('[preload] onSignal:', msg?.type); cb(msg) })
    },
    onStatus: (cb: (status: string) => void) => {
      ipcRenderer.on('remote:ws-status', (_, status) => { console.log('[preload] onStatus:', status); cb(status) })
    },
  },
})
