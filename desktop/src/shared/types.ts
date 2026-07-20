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

export interface PluginContext {
  plugin: PluginInfo
  api: {
    get: (path: string) => Promise<any>
    post: (path: string, body?: any) => Promise<any>
    put: (path: string, body?: any) => Promise<any>
    delete: (path: string) => Promise<any>
  }
  storage: {
    get: (key: string) => Promise<any>
    set: (key: string, value: any) => Promise<void>
  }
  notification: {
    show: (title: string, body?: string) => void
  }
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
        openPage: (pluginId: string) => void
        openSearch: () => void
        hide: () => void
      }
      api: {
        get: (path: string) => Promise<any>
        post: (path: string, body?: any) => Promise<any>
        put: (path: string, body?: any) => Promise<any>
        delete: (path: string) => Promise<any>
      }
    }
  }
}
