export interface PluginManifest {
  id: string
  name: string
  displayName: string
  description?: string
  version: string
  icon?: string
  keywords?: string[]
  permissions?: string[]
  builtin?: boolean
  main?: string
}

export interface PluginInfo {
  id: string
  manifest: PluginManifest
  path: string
  enabled: boolean
}

export interface SearchProvider {
  keyword: string
  name: string
  priority?: number
  onSearch: (query: string) => Promise<SearchResult[]> | SearchResult[]
}

export interface SearchResult {
  type: string
  title: string
  subtitle?: string
  icon?: string
  action: string
  actionArgs?: unknown
  pluginId?: string
}

export interface PluginCommand {
  name: string
  handler: (args: unknown) => Promise<unknown> | unknown
}

export interface PluginPanel {
  id: string
  pluginId: string
  height?: number
}

export interface ScreenshotRecord {
  id: string
  dataUrl: string
  time: number
  type: string
  width: number
  height: number
}

export interface ScreenshotCapability {
  start: () => Promise<void>
  captureFullscreen: () => Promise<string | null>
  showEditor: (dataUrl: string) => Promise<void>
  getHistory: () => ScreenshotRecord[]
  clearHistory: () => void
  deleteHistory: (id: string) => void
}

export interface RemoteCapability {
  getDesktopSources: () => Promise<any[]>
  getScreenSize: () => { width: number; height: number }
  getAllDisplays: () => { id: number; name: string; bounds: { x: number; y: number; width: number; height: number }; scaleFactor: number }[]
}

export interface PluginContext {
  plugin: PluginInfo
  api: {
    get: (path: string) => Promise<any>
    post: (path: string, body?: any) => Promise<any>
    put: (path: string, body?: any) => Promise<any>
    delete: (path: string) => Promise<any>
  }
  clipboard: Electron.Clipboard | null
  shell: { openPath: (path: string) => Promise<string>; openExternal: (url: string) => Promise<void> } | null
  storage: {
    get: (key: string) => Promise<any>
    set: (key: string, value: any) => Promise<void>
  }
  notification: {
    show: (title: string, body?: string) => void
  }
  screenshot: ScreenshotCapability | null
  remote: RemoteCapability | null
  openPage: (pluginId: string, query?: string) => void
  registerCommand: (name: string, handler: (args: unknown) => Promise<unknown>) => void
  registerSearchProvider: (provider: SearchProvider) => void
}

export interface PluginModule {
  panel?: any
  page?: any
  activate: (context: PluginContext) => Promise<void>
  deactivate: () => void
}

declare global {
  interface Window {
    mqbox: {
      plugin: {
        list: () => Promise<PluginInfo[]>
        getPanels: () => Promise<PluginPanel[]>
        getPage: (pluginId: string) => Promise<any>
        execute: (pluginId: string, command: string, args?: unknown) => Promise<unknown>
      }
      search: {
        plugin: (keyword: string, query: string) => Promise<SearchResult[]>
        getProviders: () => Promise<SearchProvider[]>
      }
      config: {
        get: (key: string) => Promise<any>
        set: (key: string, value: any) => Promise<void>
      }
      window: {
        openMain: () => void
  files: { openDirectory: () => Promise<string | undefined>; listAudio: (dirPath: string) => Promise<{ name: string; path: string }[]> } | null
  openPage: (pluginId: string, query?: string) => void
        openSearch: () => void
        hide: () => void
      }
      screenshot: {
        onImage: (callback: (dataUrl: string) => void) => void
        getAllScreens: () => Promise<{ displays: any[]; images: string[] }>
        capture: (x: number, y: number, width: number, height: number) => Promise<string | null>
        captureFullscreen: () => Promise<string | null>
        start: () => void
        cancel: () => void
        showEditor: (dataUrl: string) => void
        pin: (dataUrl: string) => void
        pinClose: () => void
        save: (dataUrl: string) => void
        closeEditor: () => void
        closeAllPins: () => void
        getHistory: () => Promise<ScreenshotRecord[]>
        deleteHistory: (id: string) => Promise<void>
        clearHistory: () => Promise<void>
      }
      clipboard: {
        onUpdated: (callback: () => void) => void
        writeImage: (dataUrl: string) => void
      }
      api: {
        get: (path: string) => Promise<any>
        post: (path: string, body?: any) => Promise<any>
        put: (path: string, body?: any) => Promise<any>
        delete: (path: string) => Promise<any>
      },
      remote: {
        getDesktopSources: () => Promise<any[]>
        getScreenSize: () => Promise<{ width: number; height: number }>
        getAllDisplays: () => Promise<{ id: number; name: string; bounds: { x: number; y: number; width: number; height: number }; scaleFactor: number }[]>
        injectInput: (event: any) => Promise<any>
        onControlRequest: (cb: (info: any) => void) => void
      }
    }
  }
}
