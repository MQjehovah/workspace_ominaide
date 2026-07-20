import { join } from 'path'
import { clipboard, BrowserWindow } from 'electron'
import type { PluginInfo, PluginPanel, PluginModule, SearchProvider } from '../../shared/types'
import { loadPlugins } from './loader'
import { createSandbox } from './sandbox'

const plugins = new Map<string, PluginInfo>()
const modules = new Map<string, PluginModule>()
const commands = new Map<string, Map<string, Function>>()
const searchProviders: SearchProvider[] = []
const panels: PluginPanel[] = []

function getPluginDir(plugin: PluginInfo): string {
  return plugin.path
}

export async function initPlugins() {
  const loaded = loadPlugins()
  
  for (const [id, info] of loaded) {
    try {
      const modulePath = join(getPluginDir(info), info.manifest.main || 'dist/index.js')
      const fileUrl = 'file:///' + modulePath.replace(/\\/g, '/')
      const mod = await import(/* @vite-ignore */ fileUrl)
      const plugin: PluginModule = mod.default || mod
      
      if (plugin?.activate) {
        const cmdMap = new Map<string, Function>()
        commands.set(id, cmdMap)
        
        const ctx = createSandbox(info, cmdMap, searchProviders)
        await plugin.activate(ctx)
        
        modules.set(id, plugin)
        plugins.set(id, info)
        
        panels.push({ id: `${id}-panel`, pluginId: id, height: 120 })
        console.log(`Plugin activated: ${info.manifest.id}`)
      }
    } catch (e) {
      console.error(`Failed to activate plugin ${id}:`, e)
    }
  }

  startClipboardWatcher()
}

let lastClipboard = ''

function startClipboardWatcher() {
  setInterval(() => {
    try {
      const text = clipboard.readText()
      if (text && text !== lastClipboard) {
        lastClipboard = text
        executeCommand('clipboard-history', 'onClipboardChange', text)
        BrowserWindow.getAllWindows().forEach(win => win.webContents.send('clipboard:updated'))
      }
    } catch {}
  }, 500)
}

export function getPlugins(): PluginInfo[] {
  return Array.from(plugins.values())
}

export function getPanels(): PluginPanel[] {
  return panels
}

export function getSearchProviders(): SearchProvider[] {
  return searchProviders
}

export async function executeCommand(pluginId: string, command: string, args?: unknown): Promise<unknown> {
  const cmdMap = commands.get(pluginId)
  if (!cmdMap) throw new Error(`Plugin ${pluginId} not found`)
  const handler = cmdMap.get(command)
  if (!handler) throw new Error(`Command ${command} not found in plugin ${pluginId}`)
  return handler(args)
}

export function getPluginPage(pluginId: string): any {
  const mod = modules.get(pluginId)
  return mod?.page || null
}
