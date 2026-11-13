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
  frontend?: string
  backend?: string
}

export interface PluginInfo {
  id: string
  manifest: PluginManifest
  path: string
  enabled: boolean
}

export interface PluginPanel {
  id: string
  pluginId: string
  height?: number
  hasPage?: boolean
}

export interface PanelItem {
  title: string
  subtitle?: string
  action?: string
  actionArgs?: unknown
  icon?: string   // emoji or icon name (used in grid layout)
  color?: string  // background color for grid cells
}

export interface PanelSwitch {
  label: string
  value: boolean
  command: string
  commandArgs?: unknown
}

export interface PanelButton {
  label: string
  command: string
}

export interface PanelFormField {
  key: string
  label?: string
  type?: 'text' | 'textarea' | 'number' | 'select' | 'switch'
  placeholder?: string
  value?: string | number | boolean
  options?: Array<{ label: string; value: string }>
  required?: boolean
}

export interface PanelForm {
  fields: PanelFormField[]
  submitLabel?: string
  command: string
  commandArgs?: Record<string, unknown>
}

export interface PanelProgress {
  label?: string
  value: number
  max?: number
  tone?: 'default' | 'success' | 'warning' | 'danger'
  hint?: string
}

export interface PanelChart {
  label?: string
  type?: 'bar' | 'line'
  labels: string[]
  values: number[]
  unit?: string
}

export interface PanelData {
  title: string
  subtitle?: string
  description?: string
  items?: PanelItem[]
  itemsLayout?: 'list' | 'grid'  // grid renders items as icon tiles (phone-style)
  switches?: PanelSwitch[]
  buttons?: PanelButton[]
  // Rich panel blocks — plugins can render interactive UI without shipping a page.
  forms?: PanelForm[]
  progress?: PanelProgress[]
  charts?: PanelChart[]
}

// ---- Platform extension points -------------------------------------------

export interface ContextMenuItem {
  id?: string
  label?: string
  type?: 'normal' | 'separator' | 'checkbox'
  checked?: boolean
  enabled?: boolean
  submenu?: ContextMenuItem[]
}

export interface TrayMenuItem {
  id: string
  label: string
  type?: 'normal' | 'separator'
  enabled?: boolean
  checked?: boolean
  command: string
  args?: unknown
}

export interface PaletteItem {
  id: string
  title: string
  subtitle?: string
  keywords?: string[]
  icon?: string
  command: string
  args?: unknown
}

export interface SelectionAction {
  id: string
  title: string
  description?: string
  icon?: string
  command: string
  args?: Record<string, unknown>
}

export interface SelectionRunResult {
  /** Replace the selected text in the source app (requires Accessibility). */
  replace?: string
  /** Copy this value to the clipboard. */
  copy?: string
  /** Keep the bar open and show this message. */
  message?: string
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

export interface RpcRequest {
  id: string
  type: 'execute' | 'getState' | 'setState'
  command?: string
  args?: unknown
  key?: string
  value?: unknown
}

export interface RpcResponse {
  id: string
  type: 'result' | 'error' | 'event'
  data?: unknown
  error?: string
  event?: string
  eventData?: unknown
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
  config: {
    get: (key: string) => Promise<any>
  }
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
  /** Show a native context menu and resolve with the clicked item id. */
  showContextMenu: (items: ContextMenuItem[]) => Promise<string | null>
  /** Contribute items to the tray menu. Calling again replaces this plugin's items. */
  setTrayItems: (items: TrayMenuItem[]) => void
  /** Contribute a command to the global search / command palette. */
  registerPaletteItem: (item: PaletteItem) => void
  /** Contribute an action to the system-wide text selection bar. */
  registerSelectionAction: (action: SelectionAction) => void
  signal: (method: string, ...args: any[]) => Promise<unknown>
  log: (level: string, message: string) => void
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
        listAll: () => Promise<PluginInfo[]>
        getPanels: () => Promise<PluginPanel[]>
        getPage: (pluginId: string) => Promise<any>
        execute: (pluginId: string, command: string, args?: unknown) => Promise<unknown>
        setEnabled: (pluginId: string, enabled: boolean) => Promise<void>
        importPlugin: () => Promise<any>
        uninstall: (pluginId: string) => Promise<any>
        listMarketplace: () => Promise<any[]>
        installFromMarket: (pluginId: string) => Promise<any>
        getPanelData: (pluginId: string) => Promise<PanelData>
        onUpdated: (callback: () => void) => void
      }
      search: {
        plugin: (keyword: string, query: string) => Promise<SearchResult[]>
        getProviders: () => Promise<SearchProvider[]>
      }
      palette: {
        list: () => Promise<Array<PaletteItem & { pluginId: string; key: string }>>
      }
      selection: {
        onInit: (callback: (data: { text: string; actions: Array<SelectionAction & { pluginId: string; key: string }> }) => void) => void
        run: (key: string) => Promise<SelectionRunResult | { error: string }>
        close: () => void
        capture: () => Promise<string | null>
      }
      config: {
        get: (key: string) => Promise<any>
        set: (key: string, value: any) => Promise<void>
      }
      dialog: {
        selectFolder: () => Promise<string | null>
      }
      window: {
        openMain: () => void
        files: { openDirectory: () => Promise<string | undefined>; listAudio: (dirPath: string) => Promise<{ name: string; path: string }[]> } | null
        openPage: (pluginId: string, query?: string) => void
        openSearch: () => void
        hide: () => void
        openPluginWindow: (pluginId: string) => void
      }
      screenshot: {
        onImage: (callback: (dataUrl: string) => void) => void
        getAllScreens: () => Promise<{ displays: any[]; images: string[] }>
        capture: (x: number, y: number, width: number, height: number) => Promise<string | null>
        captureNormalized: (
          displayId: number,
          nx: number,
          ny: number,
          nw: number,
          nh: number,
        ) => Promise<string | null>
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
      }
      log: {
        write: (pluginId: string, level: string, message: string) => void
      }
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
