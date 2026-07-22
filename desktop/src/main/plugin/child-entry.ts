/**
 * Child process entry point for plugins.
 * This file is forked by child-process.ts.
 * It loads the plugin module and communicates via stdin/stdout RPC.
 */

import { join } from 'path'
import { createChildContext } from './child-sandbox'
import { decodeMessage, encodeMessage } from './rpc'
import type { PluginModule } from '../../shared/types'

const pluginId = process.env.OMNIAIDE_PLUGIN_ID || ''
const pluginPath = process.env.OMNIAIDE_PLUGIN_PATH || ''

if (!pluginId || !pluginPath) {
  process.stderr.write('Missing OMNIAIDE_PLUGIN_ID or OMNIAIDE_PLUGIN_PATH\n')
  process.exit(1)
}

// Intercept require('electron') to proxy via RPC to parent process
function createElectronProxy() {
  function rpc(method: string, ...args: unknown[]): Promise<unknown> {
    const id = `${Date.now().toString(36)}-${Math.random().toString(36).substring(2, 8)}`
    const msg = { id, type: 'parent-rpc', method, args }
    process.stdout!.write(encodeMessage(msg))
    return new Promise((resolve, reject) => {
      const cleanup = (chunk: Buffer) => {
        const lines = chunk.toString().split('\n').filter(l => l.trim())
        for (const line of lines) {
          try {
            const res = JSON.parse(line)
            if ((res as any).id === id) {
              process.stdin?.removeListener('data', cleanup)
              if ((res as any).type === 'error') reject(new Error((res as any).error))
              else resolve((res as any).data)
              return
            }
          } catch {}
        }
      }
      process.stdin?.on('data', cleanup)
      setTimeout(() => { process.stdin?.removeListener('data', cleanup); reject(new Error('Timeout')) }, 30000)
    })
  }

  // Track windows created by this plugin
  const windows = new Set<any>()

  const electronStub = {
    BrowserWindow: class BrowserWindowStub {
      private _destroyed = false
      private _visible = false
      private _handlers: Record<string, Function[]> = {}
      constructor(opts: any) {
        windows.add(this)
        rpc('BrowserWindow:create', opts).catch(() => {})
      }
      loadURL(url: string) { rpc('BrowserWindow:loadURL', url).catch(() => {}); return this }
      on(event: string, handler: Function) {
        if (!this._handlers[event]) this._handlers[event] = []
        this._handlers[event].push(handler)
        return this
      }
      isDestroyed() { return this._destroyed }
      isVisible() { return this._visible }
      show() { this._visible = true; rpc('BrowserWindow:show').catch(() => {}) }
      focus() { rpc('BrowserWindow:focus').catch(() => {}) }
      hide() { this._visible = false; rpc('BrowserWindow:hide').catch(() => {}) }
      close() { this._destroyed = true; windows.delete(this); rpc('BrowserWindow:close').catch(() => {}) }
      setAlwaysOnTop(v: boolean) { rpc('BrowserWindow:setAlwaysOnTop', v).catch(() => {}) }
      setSkipTaskbar(v: boolean) { rpc('BrowserWindow:setSkipTaskbar', v).catch(() => {}) }
      onDidDispose() { return this }
    },
    globalShortcut: {
      register: (accelerator: string, callback: Function) => {
        rpc('globalShortcut:register', accelerator).catch(() => {})
      },
      unregister: (accelerator: string) => { rpc('globalShortcut:unregister', accelerator).catch(() => {}) },
      unregisterAll: () => { rpc('globalShortcut:unregisterAll').catch(() => {}) },
    },
    clipboard: {
      readText: () => '',
      writeText: (text: string) => { rpc('clipboard:writeText', text).catch(() => {}) },
      readImage: () => null,
      writeImage: (img: any) => { rpc('clipboard:writeImage').catch(() => {}) },
    },
    shell: {
      openPath: (path: string) => rpc('shell:openPath', path),
      openExternal: (url: string) => rpc('shell:openExternal', url),
      showItemInFolder: (path: string) => { rpc('shell:showItemInFolder', path).catch(() => {}) },
    },
    Notification: class NotificationStub {
      constructor(opts: any) { rpc('notification:show', opts.title, opts.body).catch(() => {}) }
      show() {}
    },
    ipcMain: {
      handle: () => {},
      on: () => {},
      handleOnce: () => {},
    },
    ipcRenderer: {
      invoke: () => Promise.resolve(),
      on: () => {},
      send: () => {},
    },
    screen: {
      getPrimaryDisplay: () => ({ scaleFactor: 1, bounds: { x: 0, y: 0, width: 1920, height: 1080 } }),
      getAllDisplays: () => [],
    },
    desktopCapturer: {
      getSources: () => Promise.resolve([]),
    },
    dialog: {
      showOpenDialog: () => Promise.resolve({ canceled: true, filePaths: [] }),
      showSaveDialog: () => Promise.resolve({ canceled: true, filePath: '' }),
    },
    app: {
      getPath: () => pluginPath,
      getVersion: () => '1.0.0',
      quit: () => process.exit(0),
      getAppPath: () => pluginPath,
      getName: () => 'OmniAide',
      isPackaged: true,
    },
    nativeImage: {
      createFromPath: () => ({ resize: () => null, toDataURL: () => '' }),
      createEmpty: () => null,
    },
    contextBridge: {
      exposeInMainWorld: () => {},
    },
    Menu: {
      buildFromTemplate: () => ({ popup: () => {} }),
      setApplicationMenu: () => {},
    },
    Tray: class TrayStub {
      constructor() {}
      setToolTip() {}
      setContextMenu() {}
      on() {}
    },
    nativeTheme: { shouldUseDarkColors: false, on: () => {} },
    powerMonitor: { on: () => {} },
    protocol: { registerSchemesAsPrivileged: () => {}, handle: () => {} },
    net: { fetch: () => Promise.resolve(new Response()) },
    session: { defaultSession: { setPermissionRequestHandler: () => {}, setPermissionCheckHandler: () => {} } },
  }

  return electronStub
}

// Intercept require('electron') before plugin loads
const Module = require('module')
const origRequire = Module.prototype.require
Module.prototype.require = function (id: string) {
  if (id === 'electron') return createElectronProxy()
  return origRequire.apply(this, arguments)
}

async function main() {
  const { readFileSync, existsSync } = require('fs')
  const manifestPath = join(pluginPath, 'manifest.json')
  const pkgPath = join(pluginPath, 'package.json')
  let manifest: any = {}

  if (existsSync(manifestPath)) {
    manifest = JSON.parse(readFileSync(manifestPath, 'utf-8'))
  } else if (existsSync(pkgPath)) {
    const pkg = JSON.parse(readFileSync(pkgPath, 'utf-8'))
    const ns = pkg.omniaide || pkg.mqbox || {}
    manifest = {
      id: ns.id || pkg.name,
      name: pkg.name,
      displayName: ns.displayName || pkg.displayName || pkg.name,
      description: pkg.description,
      version: pkg.version,
      icon: ns.icon,
      keywords: ns.keywords || [],
      permissions: ns.permissions || [],
      builtin: ns.builtin !== false,
      main: pkg.main || 'dist/index.js',
    }
  }

  const pluginInfo = {
    id: pluginId,
    manifest,
    path: pluginPath,
    enabled: true,
  }

  // Load plugin module
  const mainPath = join(pluginPath, manifest.main || 'dist/index.js')
  let pluginModule: PluginModule

  try {
    const mod = require(mainPath)
    pluginModule = mod.default || mod
  } catch (e: any) {
    process.stderr.write(`Failed to load plugin ${pluginId}: ${e.message}\n`)
    process.exit(1)
  }

  // Create child context
  const ctx = createChildContext(pluginInfo as any)

  // Activate
  try {
    if (pluginModule.activate) {
      await pluginModule.activate(ctx)
    }
  } catch (e: any) {
    process.stderr.write(`[plugin:${pluginId}] activate error: ${e.message}\n`)
  }

  // Signal readiness to parent
  process.stdout!.write(encodeMessage({ id: 'ready', type: 'result', data: { status: 'activated' } }))

  // Listen for commands from parent - handle partial JSON lines properly
  let buffer = ''
  process.stdin!.on('data', (chunk: Buffer) => {
    buffer += chunk.toString()
    const lines = buffer.split('\n')
    // Keep last potentially incomplete line in buffer
    buffer = lines.pop() || ''
    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed) continue
      try {
        const msg = JSON.parse(trimmed)
        if (!(ctx as any).handleParentRequest(msg)) {
          process.stdout!.write(encodeMessage({ id: msg.id || 'unknown', type: 'error', error: 'Unknown request' }))
        }
      } catch (e: any) {
        process.stderr.write(`[plugin:${pluginId}] invalid message: ${e.message}\n`)
      }
    }
  })

  // Handle cleanup
  process.on('SIGTERM', () => {
    try { pluginModule.deactivate?.() } catch {}
    process.exit(0)
  })
}

main().catch(err => {
  process.stderr.write(`[plugin:${pluginId}] fatal error: ${err.message}\n`)
  process.exit(1)
})
