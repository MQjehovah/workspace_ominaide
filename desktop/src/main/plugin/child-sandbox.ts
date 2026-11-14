import type { PluginInfo, PluginContext, SearchProvider, ScreenshotCapability } from '../../shared/types'
import { encodeMessage, decodeMessage } from './rpc'

/**
 * Child process sandbox — provides PluginContext to plugins running in forked child processes.
 * All Electron-specific API calls are forwarded to the parent process via RPC over stdin/stdout.
 */
export function createChildContext(info: PluginInfo): PluginContext {
  const commands = new Map<string, Function>()
  const providers: SearchProvider[] = []
  const eventHandlers = new Map<string, Map<string, Function>>()
  const scheduleHandlers = new Map<string, Function>()
  let eventSeq = 0
  let pendingResolve: ((value: unknown) => void) | null = null

  process.stdin?.setMaxListeners(100)

  function sendToParent(msg: any): void {
    process.stdout!.write(encodeMessage(msg))
  }

  let respBuffer = ''

  function waitForResponse(id: string): Promise<unknown> {
    return new Promise((resolve, reject) => {
      pendingResolve = resolve
      let done = false
      const timeout = setTimeout(() => {
        if (done) return
        done = true
        process.stdin?.removeListener('data', cleanup)
        reject(new Error(`RPC timeout waiting for response ${id}`))
      }, 30000)

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
              if (done) return
              done = true
              clearTimeout(timeout)
              pendingResolve = null
              respBuffer = ''
              process.stdin?.removeListener('data', cleanup)
              if ((msg as any).type === 'error') {
                reject(new Error((msg as any).error || 'RPC error'))
              } else {
                resolve((msg as any).data)
              }
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
            fallback: !!p.fallback,
          }))
          sendToParent({ id: req.id, type: 'result', data: meta })
          return true
        }
        // Execute search (fallback providers only run when explicitly asked)
        const kw = args.keyword || ''
        const q = args.query || ''
        const matching = args.fallback
          ? providers.filter((p: any) => p.fallback)
          : providers.filter((p: any) => !p.fallback && (!kw || p.keyword === kw))
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
    if (req.type === 'event') {
      const data = req.data || {}
      const event = String(data.event || '')
      if (data.kind === 'schedule') {
        const handler = scheduleHandlers.get(String(data.id || ''))
        if (handler) {
          Promise.resolve(handler(data.payload))
            .catch((err: any) => { rpc('log:write', 'error', `schedule ${data.id} failed: ${err?.message || err}`).catch(() => {}) })
        }
        return true
      }
      const handlers = eventHandlers.get(event)
      if (handlers) {
        for (const handler of handlers.values()) {
          Promise.resolve(handler(data.payload))
            .catch((err: any) => { rpc('log:write', 'error', `event ${event} failed: ${err?.message || err}`).catch(() => {}) })
        }
      }
      return true
    }
    if (req.type === 'search') {
      const matching = providers.filter(p => !p.fallback && (!req.keyword || p.keyword === req.keyword))
      Promise.all(matching.map(p => Promise.resolve(p.onSearch(req.query))))
        .then(results => sendToParent({ id: req.id, type: 'result', data: results.flat().slice(0, 20) }))
        .catch(err => sendToParent({ id: req.id, type: 'error', error: err.message }))
      return true
    }
    return false
  }

  const perms = new Set<string>(info.manifest.permissions || [])
  const has = (name: string) => perms.has(name)

  const context: PluginContext = {
    plugin: info,
    config: {
      get: (key: string) => rpc('config:get', key),
    },
    api: {
      get: (path: string) => rpc('api:get', path),
      post: (path: string, body?: any) => rpc('api:post', path, body),
      put: (path: string, body?: any) => rpc('api:put', path, body),
      delete: (path: string) => rpc('api:delete', path),
    },
    // Exposed only when the manifest declares clipboard access. The host still
    // enforces read/write separately per call.
    clipboard: (has('clipboard') || has('clipboard:read') || has('clipboard:write'))
      ? ({
          readText: () => rpc('clipboard:readText'),
          writeText: (text: string) => { rpc('clipboard:writeText', text) },
          clear: () => { rpc('clipboard:writeText', '') },
        } as any)
      : null,
    // Manifest permissions are enforced here, not just displayed in the UI.
    shell: has('shell') ? {
      openPath: async (path: string) => rpc('shell:openPath', path) as Promise<string>,
      openExternal: async (url: string) => rpc('shell:openExternal', url) as Promise<void>,
    } : null,
    storage: has('storage') ? {
      get: async (key: string) => rpc('storage:get', key),
      set: async (key: string, value: any) => rpc('storage:set', key, value),
    } : {
      get: async () => null,
      set: async () => {},
    },
    notification: has('notification') ? {
      show: (input: any, body?: string) => {
        const payload = typeof input === 'string' ? { title: input, body } : input
        rpc('notification:show', payload).catch(() => {})
      },
    } : {
      show: () => {},
    },
    screenshot: has('screenshot') ? {
      start: () => rpc('screenshot:start'),
      captureFullscreen: () => rpc('screenshot:capture-fullscreen') as Promise<string | null>,
      showEditor: (dataUrl: string) => rpc('screenshot:show-editor', dataUrl),
      getHistory: () => rpc('screenshot:get-history'),
      clearHistory: () => rpc('screenshot:clear-history'),
      deleteHistory: (id: string) => rpc('screenshot:delete-history', id),
    } : null,
    remote: has('remote') ? {
      getDesktopSources: () => rpc('remote:get-sources'),
      getScreenSize: () => rpc('remote:screen-size') as Promise<{ width: number; height: number }>,
      getAllDisplays: () => rpc('remote:get-all-displays'),
    } : null,
    openPage: (pluginId: string, query?: string) => { rpc('openPage', pluginId, query) },
    registerCommand: (name: string, handler: Function) => { commands.set(name, handler) },
    showContextMenu: (items: any[]) => rpc('menu:show', items) as Promise<string | null>,
    setTrayItems: (items: any[]) => { rpc('tray:set', items).catch(() => {}) },
    registerPaletteItem: (item: any) => { rpc('palette:register', item).catch(() => {}) },
    registerSelectionAction: (action: any) => { rpc('selection:register', action).catch(() => {}) },
    registerAction: (action: any) => { rpc('action:register', action).catch(() => {}) },
    registerDeepLink: (spec: any) => { rpc('deeplink:register', spec).catch(() => {}) },
    getActiveWindow: () => rpc('system:active-window') as Promise<{ name: string; title: string } | null>,
    on: (event: string, handler: (payload: any) => void | Promise<void>, options?: any) => {
      const name = String(event || '')
      const id = `${name}:${++eventSeq}`
      if (!eventHandlers.has(name)) eventHandlers.set(name, new Map())
      eventHandlers.get(name)!.set(id, handler)
      rpc('event:subscribe', name, id, options || {}).catch((err: any) => {
        rpc('log:write', 'warn', `event subscribe failed (${name}): ${err?.message || err}`).catch(() => {})
      })
      return () => {
        eventHandlers.get(name)?.delete(id)
        if (eventHandlers.get(name)?.size === 0) eventHandlers.delete(name)
        rpc('event:unsubscribe', name, id).catch(() => {})
      }
    },
    emit: (event: string, payload?: unknown) => {
      rpc('event:emit', String(event || ''), payload).catch(() => {})
    },
    schedule: (spec: any, handler: (payload: any) => void | Promise<void>) => {
      if (!spec?.id) throw new Error('schedule spec requires an id')
      const id = String(spec.id)
      scheduleHandlers.set(id, handler)
      rpc('schedule:register', { ...spec, id }).catch((err: any) => {
        rpc('log:write', 'warn', `schedule register failed (${id}): ${err?.message || err}`).catch(() => {})
      })
      return () => {
        scheduleHandlers.delete(id)
        rpc('schedule:unregister', id).catch(() => {})
      }
    },
    unschedule: (id: string) => {
      scheduleHandlers.delete(String(id))
      rpc('schedule:unregister', String(id)).catch(() => {})
    },
    signal: (method: string, ...args: any[]) => rpc(method, ...args),
    registerSearchProvider: (provider: SearchProvider) => {
      providers.push({ ...provider, pluginId: info.id })
    },
    log: (level: string, message: string) => {
      rpc('log:write', level, message)
    },
  }

  return Object.assign(context, { handleParentRequest, commands, providers })
}
