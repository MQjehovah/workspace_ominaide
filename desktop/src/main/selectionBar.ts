import { BrowserWindow, clipboard, screen, shell, systemPreferences, Notification } from 'electron'
import { execFile } from 'child_process'
import { join } from 'path'
import { readClipboardTextSafe } from './clipboard'
import { executeCommand, getSelectionAction, getSelectionActions, getUniversalAction, getApplicableActions } from './plugin/host'
import type { SelectionRunResult } from '../shared/types'

let barWindow: BrowserWindow | null = null
let currentText = ''
let previousApp = ''
let currentInput: { type: 'text' | 'url'; url?: string } = { type: 'text' }

const BUILTIN_ACTIONS = [
  {
    id: 'copy-selection',
    title: '复制选中文本',
    description: '把选中的内容复制到剪贴板',
    icon: '📋',
    command: '__builtin_copy__',
    pluginId: '__builtin__',
    key: '__builtin__:copy-selection',
  },
]

const BAR_WIDTH = 400
const BAR_MIN_HEIGHT = 96

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function getFrontmostApp(): Promise<string> {
  return new Promise((resolve) => {
    execFile(
      'osascript',
      ['-e', 'tell application "System Events" to get name of first application process whose frontmost is true'],
      { timeout: 1500 },
      (err, stdout) => resolve(err ? '' : String(stdout).trim()),
    )
  })
}

function activateApp(name: string): Promise<void> {
  if (!name) return Promise.resolve()
  const escaped = name.replace(/"/g, '\\"')
  return runAppleScript(`tell application "${escaped}" to activate`)
}

function runAppleScript(script: string): Promise<void> {
  return new Promise((resolve, reject) => {
    execFile('osascript', ['-e', script], { timeout: 2000 }, (err) => {
      if (err) reject(err)
      else resolve()
    })
  })
}

async function copySelectedTextWithKeystroke(): Promise<void> {
  if (process.platform === 'darwin') {
    await runAppleScript('tell application "System Events" to keystroke "c" using command down')
    return
  }
  if (process.platform === 'win32') {
    await new Promise<void>((resolve, reject) => {
      execFile(
        'powershell',
        ['-NoProfile', '-Command', 'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait("^c")'],
        { timeout: 2000 },
        (err) => (err ? reject(err) : resolve()),
      )
    })
    return
  }
  await new Promise<void>((resolve, reject) => {
    execFile('xdotool', ['key', '--clearmodifiers', 'ctrl+c'], { timeout: 2000 }, (err) =>
      err ? reject(err) : resolve(),
    )
  })
}

/**
 * Read the text currently selected in the foreground application.
 *
 * There is no cross-platform API for this, so we copy the selection with a
 * synthetic Cmd/Ctrl+C, read the clipboard, then restore the previous contents.
 * macOS requires the Accessibility permission for the synthetic keystroke.
 */
export async function captureSelectedText(): Promise<string | null> {
  if (process.platform === 'darwin') {
    const trusted = systemPreferences.isTrustedAccessibilityClient(false)
    if (!trusted) {
      // Ask macOS to show the permission prompt, then stop: the user has to
      // grant access and trigger the shortcut again.
      systemPreferences.isTrustedAccessibilityClient(true)
      notify('需要辅助功能权限', '请在系统设置 → 隐私与安全性 → 辅助功能中勾选 OmniAide。')
      shell.openExternal('x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility')
      return null
    }
  }

  let previous = ''
  try {
    previous = await readClipboardTextSafe()
  } catch {}

  try {
    await copySelectedTextWithKeystroke()
  } catch (e) {
    return null
  }

  // Poll briefly: the source app writes the pasteboard asynchronously.
  let captured = ''
  for (let i = 0; i < 14; i++) {
    await sleep(50)
    try {
      const text = await readClipboardTextSafe()
      if (text && text !== previous) {
        captured = text
        break
      }
    } catch {}
  }

  // Restore what the user had before we hijacked the clipboard. Only text can
  // be restored reliably; images/rich content are cleared by the copy.
  try {
    if (previous) clipboard.writeText(previous)
    else if (captured) clipboard.clear()
  } catch {}

  if (!captured) return null
  const trimmed = captured.trim()
  return trimmed.length > 0 ? trimmed : null
}

function notify(title: string, body?: string): void {
  try {
    new Notification({ title, body }).show()
  } catch {}
}

function placeWindow(win: BrowserWindow, height: number): void {
  const cursor = screen.getCursorScreenPoint()
  const display = screen.getDisplayNearestPoint(cursor)
  const area = display.workArea
  const width = BAR_WIDTH
  const x = Math.min(Math.max(area.x + 8, cursor.x - Math.floor(width / 2)), area.x + area.width - width - 8)
  const y = Math.min(Math.max(area.y + 8, cursor.y + 18), area.y + area.height - height - 8)
  win.setBounds({ x, y, width, height })
}

export function isSelectionBarOpen(): boolean {
  return !!barWindow && !barWindow.isDestroyed()
}

export function closeSelectionBar(): void {
  if (barWindow && !barWindow.isDestroyed()) barWindow.close()
  barWindow = null
}

function ensureBarWindow(): BrowserWindow {
  if (barWindow && !barWindow.isDestroyed()) return barWindow

  const win = new BrowserWindow({
    width: BAR_WIDTH,
    height: BAR_MIN_HEIGHT,
    frame: false,
    transparent: true,
    resizable: false,
    movable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    show: false,
    hasShadow: true,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  })

  win.setAlwaysOnTop(true, 'pop-up-menu')
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })

  const baseUrl = process.env.VITE_DEV_SERVER_URL
  if (baseUrl) {
    win.loadURL(`${baseUrl}?view=selection-bar`)
  } else {
    win.loadFile(join(__dirname, '../../dist/index.html'), { query: { view: 'selection-bar' } })
  }

  win.on('blur', () => {
    // Give the renderer a moment so in-bar buttons do not close prematurely.
    setTimeout(() => {
      if (barWindow === win && !win.isDestroyed() && !win.isFocused()) closeSelectionBar()
    }, 120)
  })

  win.on('closed', () => {
    if (barWindow === win) barWindow = null
  })

  barWindow = win
  return win
}

export async function openSelectionBar(text?: string, options?: { silent?: boolean }): Promise<boolean> {
  if (isSelectionBarOpen()) {
    closeSelectionBar()
    return false
  }

  const selected = text !== undefined ? text : await captureSelectedText()
  if (!selected) {
    if (!options?.silent) {
      notify('没有读取到选中文本', '先选中一段文字，再按划词快捷键。首次使用需要辅助功能权限。')
    }
    return false
  }

  currentText = selected
  if (process.platform === 'darwin') previousApp = await getFrontmostApp()
  const isUrl = /^https?:\/\//i.test(selected)
  currentInput = { type: isUrl ? 'url' : 'text', url: isUrl ? selected : undefined }
  const universal = getApplicableActions({
    type: currentInput.type,
    text: selected,
    url: currentInput.url,
    app: { name: previousApp, title: '' },
    source: 'selection',
  }).map(action => ({
    id: action.id,
    title: action.title,
    description: action.description,
    icon: action.icon,
    pluginId: action.pluginId,
    key: action.key,
  }))
  const actions = [...BUILTIN_ACTIONS, ...getSelectionActions(), ...universal]
  const win = ensureBarWindow()
  placeWindow(win, BAR_MIN_HEIGHT)

  win.webContents.once('did-finish-load', () => {
    if (win.isDestroyed()) return
    win.webContents.send('selection:init', { text: selected, actions })
    win.show()
    win.focus()
  })

  if (!win.webContents.isLoading()) {
    win.webContents.send('selection:init', { text: selected, actions })
    win.show()
    win.focus()
  }

  return true
}

export function resizeSelectionBar(height: number): void {
  if (!barWindow || barWindow.isDestroyed()) return
  if (!Number.isFinite(height)) return
  const clamped = Math.max(BAR_MIN_HEIGHT, Math.min(560, Math.round(height)))
  const bounds = barWindow.getBounds()
  placeWindow(barWindow, clamped)
  if (bounds.width !== BAR_WIDTH) barWindow.setSize(BAR_WIDTH, clamped)
}

async function pasteIntoForeground(): Promise<void> {
  if (process.platform === 'darwin') {
    await runAppleScript('tell application "System Events" to keystroke "v" using command down')
    return
  }
  if (process.platform === 'win32') {
    await new Promise<void>((resolve, reject) => {
      execFile(
        'powershell',
        ['-NoProfile', '-Command', 'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait("^v")'],
        { timeout: 2000 },
        (err) => (err ? reject(err) : resolve()),
      )
    })
    return
  }
  await new Promise<void>((resolve, reject) => {
    execFile('xdotool', ['key', '--clearmodifiers', 'ctrl+v'], { timeout: 2000 }, (err) =>
      err ? reject(err) : resolve(),
    )
  })
}

export async function runSelectionAction(key: string): Promise<SelectionRunResult | { error: string }> {
  const builtin = BUILTIN_ACTIONS.find(a => a.key === key)
  if (builtin) {
    if (!currentText) return { error: '没有选中文本' }
    if (builtin.id === 'copy-selection') {
      clipboard.writeText(currentText)
      closeSelectionBar()
      return {}
    }
  }

  const universal = getUniversalAction(key)
  if (universal) {
    if (!currentText) return { error: '没有选中文本' }
    try {
      const result = (await executeCommand(universal.pluginId, universal.command, {
        ...(universal.args || {}),
        type: currentInput.type,
        text: currentText,
        url: currentInput.url,
        app: { name: previousApp, title: '' },
        source: 'selection',
      })) as SelectionRunResult | undefined
      return await applyActionResult(result)
    } catch (e: any) {
      return { error: e?.message || String(e) }
    }
  }

  const action = getSelectionAction(key)
  if (!action) return { error: '未找到该划词动作' }
  if (!currentText) return { error: '没有选中文本' }

  try {
    const result = (await executeCommand(action.pluginId, action.command, {
      ...(action.args || {}),
      text: currentText,
    })) as SelectionRunResult | undefined
    return await applyActionResult(result)
  } catch (e: any) {
    return { error: e?.message || String(e) }
  }
}

async function applyActionResult(result: SelectionRunResult | undefined): Promise<SelectionRunResult | { error: string }> {
  if (result && typeof result === 'object') {
    if (typeof result.replace === 'string') {
      let before = ''
      try { before = await readClipboardTextSafe() } catch {}
      clipboard.writeText(result.replace)
      closeSelectionBar()
      // The bar stole focus; put the user back into the app they came from
      // before sending the paste keystroke.
      await activateApp(previousApp)
      await sleep(180)
      try {
        await pasteIntoForeground()
      } catch {
        return { message: '已复制，可粘贴替换（需要辅助功能权限）' }
      }
      await sleep(400)
      try {
        if (before) clipboard.writeText(before)
        else clipboard.clear()
      } catch {}
      return {}
    }
    if (typeof result.copy === 'string') {
      clipboard.writeText(result.copy)
      closeSelectionBar()
      return {}
    }
    if (typeof result.message === 'string') {
      return { message: result.message }
    }
  }

  closeSelectionBar()
  return {}
}
