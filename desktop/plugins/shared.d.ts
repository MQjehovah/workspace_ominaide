export interface PluginContext {
  api: {
    get: (path: string) => Promise<any>
    post: (path: string, body?: any) => Promise<any>
    put: (path: string, body?: any) => Promise<any>
    delete: (path: string) => Promise<any>
  }
  mcp: {
    call: (tool: string, args: any) => Promise<any>
  }
  notification: {
    show: (title: string, message?: string) => void
  }
  pluginId: string
}

export interface PluginModule {
  activate: (context: PluginContext) => Promise<void>
  deactivate: () => void
  panel?: any  // Vue component for sidebar panel
  page?: any   // Vue component for full page
}
