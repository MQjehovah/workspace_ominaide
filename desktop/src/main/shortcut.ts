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

export async function setupShortcut(callbacks: Record<string, () => void>) {
  builtinCallbacks = callbacks
  const config = await getConfig()

  const builtins = config.shortcut || { toggle: 'Ctrl+Shift+Space', search: 'Ctrl+Space' }
  for (const [key, acc] of Object.entries(builtins)) {
    const cb = builtinCallbacks[key]
    if (cb && typeof acc === 'string') {
      try { globalShortcut.register(acc, cb) } catch {}
    }
  }

  const custom: ShortcutBinding[] = config.customShortcuts || []
  for (const s of custom) {
    try {
      globalShortcut.register(s.accelerator, () => {
        executeCommand(s.pluginId, s.command, s.args)
      })
    } catch {}
  }
}

export async function getCustomShortcuts(): Promise<ShortcutBinding[]> {
  const config = await getConfig()
  return config.customShortcuts || []
}

export async function addCustomShortcut(binding: ShortcutBinding): Promise<boolean> {
  const config = await getConfig()
  const custom: ShortcutBinding[] = config.customShortcuts || []

  const idx = custom.findIndex(s => s.accelerator === binding.accelerator)
  if (idx >= 0) {
    try { globalShortcut.unregister(binding.accelerator) } catch {}
    custom.splice(idx, 1)
  }

  custom.push(binding)
  await setConfig('customShortcuts', custom)

  try {
    globalShortcut.register(binding.accelerator, () => {
      executeCommand(binding.pluginId, binding.command, binding.args)
    })
  } catch { return false }
  return true
}

export async function removeCustomShortcut(accelerator: string): Promise<boolean> {
  const config = await getConfig()
  const custom: ShortcutBinding[] = (config.customShortcuts || []).filter(s => s.accelerator !== accelerator)
  await setConfig('customShortcuts', custom)
  try { globalShortcut.unregister(accelerator) } catch {}
  return true
}

export async function getBuiltinShortcuts(): Promise<BuiltinShortcut[]> {
  const config = await getConfig()
  const s = config.shortcut || {}
  return [
    { key: 'toggle', label: '打开/隐藏面板', accelerator: s.toggle || 'Ctrl+Shift+Space', editable: true },
    { key: 'search', label: '全局搜索', accelerator: s.search || 'Ctrl+Space', editable: true },
  ]
}

export async function updateBuiltinShortcut(key: string, accelerator: string): Promise<boolean> {
  const config = await getConfig()
  const shortcuts = config.shortcut || {}
  const oldAcc = shortcuts[key]

  if (oldAcc) { try { globalShortcut.unregister(oldAcc) } catch {} }

  shortcuts[key] = accelerator
  await setConfig('shortcut', shortcuts)

  const cb = builtinCallbacks[key]
  if (cb) {
    try { globalShortcut.register(accelerator, cb) } catch {}
  }
  return true
}
