import type { PluginInfo, PluginContext, SearchProvider, ScreenshotCapability } from '../../shared/types'
import { encodeMessage, decodeMessage } from './rpc'

/**
 * Child process sandbox — provides PluginContext to plugins running in forked child processes.
 * All Electron-specific API calls are forwarded to the parent process via RPC over stdin/stdout.
 */
export function createChildContext(info: PluginInfo): PluginContext {
  const commands = new Map<string, Function>()
  const providers: SearchProvider[] = []
  let pendingResolve: ((value: unknown) => void) | null = null

  function sendToParent(msg: any): void {
    process.stdout!.write(encodeMessage(msg))
  }

  let respBuffer = ''

  function waitForResponse(id: string): Promise<unknown> {
    return new Promise((resolve) => {
      pendingResolve = resolve
      const cleanup = (chunk: Buffer) => {
        respBuffer += chunk.toString()
        const lines = respBuffer.split('\n')
        respBuffer = lines.pop() || ''
        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed) continue
          try {
            const msg = JSON.parse(trimmed)
            if ((msg as any).id === id) {
              pendingResolve = null
              respBuffer = ''
              process.stdin?.removeListener('data', cleanup)
              resolve((msg as any).data)
              return
            }
          } catch {}
        }
      }
      process.stdin?.on('data', cleanup)
    })
  }

  async function rpc(method: string, ...args: unknown[]): Promise<unknown> {
    const id = `${Date.now().toString(36)}-${Math.random().toString(36).substring(2, 8)}`
    sendToParent({ id, type: 'parent-rpc', method, args })
    return waitForResponse(id)
  }

  /**
   * Handle incoming commands from parent process.
   * Called by the child-entry loop.
   */
  function handleParentRequest(req: any): boolean {
    if (req.type === 'execute' && req.command) {
      if (req.command === '__search__') {
        const args = req.args || {}
        // Return provider list
        if (args.getProviders) {
          const meta = providers.map(p => ({
            keyword: p.keyword,
            name: p.name,
            priority: p.priority,
          }))
          sendToParent({ id: req.id, type: 'result', data: meta })
          return true
        }
        // Execute search
        const kw = args.keyword || ''
        const q = args.query || ''
        const matching = providers.filter((p: any) => !kw || p.keyword === kw)
        Promise.all(matching.map((p: any) => Promise.resolve(p.onSearch(q))))
          .then(results => sendToParent({ id: req.id, type: 'result', data: results.flat().slice(0, 20) }))
          .catch(err => sendToParent({ id: req.id, type: 'error', error: err.message }))
        return true
      }
      const handler = commands.get(req.command)
      if (handler) {
        Promise.resolve(handler(req.args))
          .then(result => sendToParent({ id: req.id, type: 'result', data: result }))
          .catch(err => sendToParent({ id: req.id, type: 'error', error: err.message }))
        return true
      }
      sendToParent({ id: req.id, type: 'error', error: `Unknown command: ${req.command}` })
      return true
    }
    if (req.type === 'search') {
      const matching = providers.filter(p => !req.keyword || p.keyword === req.keyword)
      Promise.all(matching.map(p => Promise.resolve(p.onSearch(req.query))))
        .then(results => sendToParent({ id: req.id, type: 'result', data: results.flat().slice(0, 20) }))
        .catch(err => sendToParent({ id: req.id, type: 'error', error: err.message }))
      return true
    }
    return false
  }

  const context: PluginContext = {
    plugin: info,
    api: {
      get: (path: string) => rpc('api:get', path),
      post: (path: string, body?: any) => rpc('api:post', path, body),
      put: (path: string, body?: any) => rpc('api:put', path, body),
      delete: (path: string) => rpc('api:delete', path),
    },
    clipboard: null,
    shell: {
      openPath: async (path: string) => rpc('shell:openPath', path) as Promise<string>,
      openExternal: async (url: string) => rpc('shell:openExternal', url) as Promise<void>,
    },
    storage: {
      get: async (key: string) => rpc('storage:get', key),
      set: async (key: string, value: any) => rpc('storage:set', key, value),
    },
    notification: {
      show: (title: string, body?: string) => { rpc('notification:show', title, body) },
    },
    screenshot: {
      start: () => rpc('screenshot:start'),
      captureFullscreen: () => rpc('screenshot:capture-fullscreen') as Promise<string | null>,
      showEditor: (dataUrl: string) => rpc('screenshot:show-editor', dataUrl),
      getHistory: () => rpc('screenshot:get-history'),
      clearHistory: () => rpc('screenshot:clear-history'),
      deleteHistory: (id: string) => rpc('screenshot:delete-history', id),
    },
    remote: {
      getDesktopSources: () => rpc('remote:get-sources'),
      getScreenSize: () => rpc('remote:screen-size') as Promise<{ width: number; height: number }>,
      getAllDisplays: () => rpc('remote:get-all-displays'),
    },
    openPage: (pluginId: string, query?: string) => { rpc('openPage', pluginId, query) },
    registerCommand: (name: string, handler: Function) => { commands.set(name, handler) },
    registerSearchProvider: (provider: SearchProvider) => {
      providers.push({ ...provider, pluginId: info.id })
    },
  }

  return Object.assign(context, { handleParentRequest, commands, providers })
}
