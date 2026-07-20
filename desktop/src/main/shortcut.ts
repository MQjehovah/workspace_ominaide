import { globalShortcut } from 'electron'
import { executeCommand } from './plugin/host'
import { getConfig, setConfig } from './config'

export interface ShortcutBinding {
  accelerator: string
  pluginId: string
  command: string
  args?: unknown
  label?: string
}

export interface BuiltinShortcut {
  key: string
  label: string
  accelerator: string
  editable: boolean
  callback?: () => void
}

let builtinCallbacks: Record<string, () => void> = {}

export function setupShortcut(callbacks: Record<string, () => void>) {
  builtinCallbacks = callbacks
  const config = getConfig()

  // Register built-in shortcuts
  const builtins = config.shortcut || { toggle: 'Ctrl+Space', search: 'Ctrl+Shift+Space' }
  for (const [key, acc] of Object.entries(builtins)) {
    const cb = builtinCallbacks[key]
    if (cb && typeof acc === 'string') {
      try { globalShortcut.register(acc, cb) } catch {}
    }
  }

  // Register custom plugin shortcuts
  const custom: ShortcutBinding[] = config.customShortcuts || []
  for (const s of custom) {
    try {
      globalShortcut.register(s.accelerator, () => {
        executeCommand(s.pluginId, s.command, s.args)
      })
    } catch {}
  }
}

export function getCustomShortcuts(): ShortcutBinding[] {
  return getConfig().customShortcuts || []
}

export function addCustomShortcut(binding: ShortcutBinding): boolean {
  const config = getConfig()
  const custom: ShortcutBinding[] = config.customShortcuts || []

  // Remove old binding with same accelerator
  const idx = custom.findIndex(s => s.accelerator === binding.accelerator)
  if (idx >= 0) {
    try { globalShortcut.unregister(binding.accelerator) } catch {}
    custom.splice(idx, 1)
  }

  custom.push(binding)
  setConfig('customShortcuts', custom)

  try {
    globalShortcut.register(binding.accelerator, () => {
      executeCommand(binding.pluginId, binding.command, binding.args)
    })
  } catch { return false }
  return true
}

export function removeCustomShortcut(accelerator: string): boolean {
  const config = getConfig()
  const custom: ShortcutBinding[] = (config.customShortcuts || []).filter(s => s.accelerator !== accelerator)
  setConfig('customShortcuts', custom)
  try { globalShortcut.unregister(accelerator) } catch {}
  return true
}

export function getBuiltinShortcuts(): BuiltinShortcut[] {
  const config = getConfig()
  const s = config.shortcut || {}
  return [
    { key: 'toggle', label: '打开/隐藏面板', accelerator: s.toggle || 'Ctrl+Space', editable: true },
    { key: 'search', label: '全局搜索', accelerator: s.search || 'Ctrl+Shift+Space', editable: true },
  ]
}

export function updateBuiltinShortcut(key: string, accelerator: string): boolean {
  const config = getConfig()
  const shortcuts = config.shortcut || {}
  const oldAcc = shortcuts[key]

  // Unregister old
  if (oldAcc) { try { globalShortcut.unregister(oldAcc) } catch {} }

  // Register new
  shortcuts[key] = accelerator
  setConfig('shortcut', shortcuts)

  const cb = builtinCallbacks[key]
  if (cb) {
    try { globalShortcut.register(accelerator, cb) } catch {}
  }
  return true
}
