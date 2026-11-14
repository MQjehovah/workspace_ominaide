import { contextBridge, ipcRenderer } from 'electron'

const pluginListeners: (() => void)[] = []
const panelListeners = new Map<string, () => void>()

ipcRenderer.on('panel:updated', (_event, pluginId: string) => {
  const cb = panelListeners.get(pluginId)
  if (cb) cb()
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
    statuses: () => ipcRenderer.invoke('plugin:statuses'),
    restart: (pluginId: string) => ipcRenderer.invoke('plugin:restart', pluginId),
    logs: (pluginId: string, limit?: number) => ipcRenderer.invoke('plugin:logs', pluginId, limit),
    openLogFile: () => ipcRenderer.invoke('plugin:open-log-file'),
    permissions: () => ipcRenderer.invoke('plugin:permissions'),
    setPermission: (pluginId: string, permission: string, enabled: boolean) =>
      ipcRenderer.invoke('plugin:set-permission', pluginId, permission, enabled),
    reload: () =>
      ipcRenderer.invoke('plugin:reload'),
    onUpdated: (callback: () => void) => {
      pluginListeners.push(callback)
    },
    onPanelUpdated: (pluginId: string, callback: () => void) => {
      panelListeners.set(pluginId, callback)
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
    getBounds: () => ipcRenderer.invoke('window:get-bounds'),
    setBounds: (bounds: { x: number; y: number }) => ipcRenderer.invoke('window:set-bounds', bounds),
  },
  palette: {
    list: () => ipcRenderer.invoke('palette:list'),
    run: (key: string, values?: Record<string, unknown>) => ipcRenderer.invoke('palette:run', key, values),
    onUpdated: (callback: () => void) => {
      ipcRenderer.on('palette:updated', () => callback())
    },
  },
  commandForm: {
    onInit: (callback: (data: any) => void) => {
      ipcRenderer.on('command-form:init', (_, data) => callback(data))
    },
    submit: (values: Record<string, unknown>) => ipcRenderer.send('command-form:submit', values),
    cancel: () => ipcRenderer.send('command-form:cancel'),
    resize: (height: number) => ipcRenderer.send('command-form:resize', height),
  },
  actions: {
    list: (input: any) => ipcRenderer.invoke('actions:list', input),
    run: (key: string, input: any) => ipcRenderer.invoke('actions:run', key, input),
  },
  selection: {
    onInit: (callback: (data: any) => void) => {
      ipcRenderer.on('selection:init', (_, data) => callback(data))
    },
    run: (key: string) => ipcRenderer.invoke('selection:run', key),
    close: () => ipcRenderer.send('selection:close'),
    capture: () => ipcRenderer.invoke('selection:capture'),
    show: (text?: string) => ipcRenderer.invoke('selection:show', text),
    resize: (height: number) => ipcRenderer.send('selection:resize', height),
  },
  clipboard: {
    writeImage: (dataUrl: string) => ipcRenderer.invoke('clipboard:write-image', dataUrl),
    readText: () => ipcRenderer.invoke('clipboard:read-text'),
    writeText: (text: string) => ipcRenderer.invoke('clipboard:write-text', text),
  },
  player: {
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
  },
  shell: {
    openExternal: (url: string) => ipcRenderer.invoke('shell:open-external', url),
    openPath: (path: string) => ipcRenderer.invoke('shell:open-path', path),
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
    captureNormalized: (
      displayId: number,
      nx: number,
      ny: number,
      nw: number,
      nh: number,
    ) => ipcRenderer.invoke('screenshot:capture-normalized', displayId, nx, ny, nw, nh),
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
  mcp: {
    list: () => ipcRenderer.invoke('mcp:list'),
    add: (cfg: any) => ipcRenderer.invoke('mcp:add', cfg),
    update: (id: string, patch: any) => ipcRenderer.invoke('mcp:update', id, patch),
    remove: (id: string) => ipcRenderer.invoke('mcp:remove', id),
    refresh: () => ipcRenderer.invoke('mcp:refresh'),
    tools: () => ipcRenderer.invoke('mcp:tools'),
    testCall: (name: string, args: any) => ipcRenderer.invoke('mcp:test-call', name, args),
  },
  skills: {
    list: () => ipcRenderer.invoke('skills:list'),
    create: (data: any) => ipcRenderer.invoke('skills:create', data),
    update: (id: string, patch: any) => ipcRenderer.invoke('skills:update', id, patch),
    toggle: (id: string, enabled: boolean) => ipcRenderer.invoke('skills:toggle', id, enabled),
    remove: (id: string) => ipcRenderer.invoke('skills:delete', id),
    installFolder: () => ipcRenderer.invoke('skills:install-folder'),
    installUrl: (url: string) => ipcRenderer.invoke('skills:install-url', url),
  },
  cognition: {
    onHandoff: (callback: (msg: any) => void) => {
      const handler = (_: any, msg: any) => callback(msg)
      ipcRenderer.on('cognition:handoff', handler)
      return () => ipcRenderer.removeListener('cognition:handoff', handler)
    },
  },
  agent: {
    start: (req: any) => ipcRenderer.invoke('agent:start', req),
    abort: (sessionId: string) => ipcRenderer.invoke('agent:abort', sessionId),
    onEvent: (callback: (payload: any) => void) => {
      const handler = (_: any, payload: any) => callback(payload)
      ipcRenderer.on('agent:event', handler)
      return () => ipcRenderer.removeListener('agent:event', handler)
    },
  },
  update: {
    info: () => ipcRenderer.invoke('update:info'),
    check: () => ipcRenderer.invoke('update:check'),
    download: () => ipcRenderer.invoke('update:download'),
    install: () => ipcRenderer.invoke('update:install'),
    onStatus: (callback: (status: any) => void) => {
      const handler = (_: any, status: any) => callback(status)
      ipcRenderer.on('update:status', handler)
      return () => ipcRenderer.removeListener('update:status', handler)
    },
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
    saveFile: (name: string, data: ArrayBuffer) => ipcRenderer.invoke('remote:save-file', { name, data }),
    getLockState: () => ipcRenderer.invoke('remote:get-lock-state'),
    setPowerSave: (active: boolean) => ipcRenderer.invoke('remote:power-save', active),
    onScreenLocked: (cb: () => void) => { ipcRenderer.on('remote:screen-locked', () => cb()) },
    onScreenUnlocked: (cb: () => void) => { ipcRenderer.on('remote:screen-unlocked', () => cb()) },
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
      const handler = (_: any, msg: any) => { console.log('[preload] onSignal:', msg?.type); cb(msg) }
      ipcRenderer.on('remote:ws-signal', handler)
      return () => ipcRenderer.removeListener('remote:ws-signal', handler)
    },
    onStatus: (cb: (status: string) => void) => {
      ipcRenderer.on('remote:ws-status', (_, status) => { console.log('[preload] onStatus:', status); cb(status) })
    },
  },
})
