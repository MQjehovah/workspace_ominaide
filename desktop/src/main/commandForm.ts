import { BrowserWindow, screen } from 'electron'
import { join } from 'path'
import type { CommandArgument } from '../shared/types'

let formWindow: BrowserWindow | null = null
let pendingResolve: ((value: Record<string, unknown> | null) => void) | null = null
let pendingTitle = ''

const WIDTH = 520

function finish(values: Record<string, unknown> | null): void {
  const resolve = pendingResolve
  pendingResolve = null
  if (formWindow && !formWindow.isDestroyed()) {
    try { formWindow.close() } catch {}
  }
  formWindow = null
  resolve?.(values)
}

function formHeight(fields: CommandArgument[]): number {
  return Math.max(220, Math.min(640, 176 + fields.length * 56))
}

function placeWindow(win: BrowserWindow, height: number): void {
  const cursor = screen.getCursorScreenPoint()
  const display = screen.getDisplayNearestPoint(cursor)
  const area = display.workArea
  const x = Math.round(area.x + (area.width - WIDTH) / 2)
  const y = Math.round(area.y + (area.height - height) / 2)
  win.setBounds({ x, y, width: WIDTH, height })
}

export function isCommandFormOpen(): boolean {
  return !!formWindow && !formWindow.isDestroyed()
}

export function collectCommandArguments(
  title: string,
  fields: CommandArgument[],
  initial?: Record<string, unknown>,
): Promise<Record<string, unknown> | null> {
  if (!Array.isArray(fields) || fields.length === 0) {
    return Promise.resolve({ ...(initial || {}) })
  }
  // Only one form at a time; a second request cancels the first.
  if (pendingResolve) finish(null)

  return new Promise((resolve) => {
    pendingResolve = resolve
    pendingTitle = title || '输入参数'
    const height = formHeight(fields)

    const win = new BrowserWindow({
      width: WIDTH,
      height,
      frame: false,
      resizable: false,
      minimizable: false,
      maximizable: false,
      fullscreenable: false,
      skipTaskbar: true,
      alwaysOnTop: true,
      show: false,
      backgroundColor: '#ffffff',
      webPreferences: {
        preload: join(__dirname, '../preload/index.js'),
        nodeIntegration: false,
        contextIsolation: true,
      },
    })
    formWindow = win
    placeWindow(win, height)
    win.setAlwaysOnTop(true, 'pop-up-menu')

    const baseUrl = process.env.VITE_DEV_SERVER_URL
    if (baseUrl) {
      win.loadURL(`${baseUrl}?view=command-form`)
    } else {
      win.loadFile(join(__dirname, '../../dist/index.html'), { query: { view: 'command-form' } })
    }

    const sendInit = () => {
      if (win.isDestroyed()) return
      win.webContents.send('command-form:init', {
        title: pendingTitle,
        arguments: fields,
        initial: initial || {},
      })
      win.show()
      win.focus()
    }

    win.webContents.once('did-finish-load', sendInit)
    if (!win.webContents.isLoading()) sendInit()

    win.on('closed', () => {
      if (formWindow === win) formWindow = null
      if (pendingResolve === resolve) {
        pendingResolve = null
        resolve(null)
      }
    })
  })
}

export function submitCommandForm(values: Record<string, unknown>): void {
  finish(values && typeof values === 'object' ? values : {})
}

export function cancelCommandForm(): void {
  finish(null)
}

export function resizeCommandForm(height: number): void {
  if (!formWindow || formWindow.isDestroyed()) return
  if (!Number.isFinite(height)) return
  const clamped = Math.max(180, Math.min(680, Math.round(height)))
  const bounds = formWindow.getBounds()
  formWindow.setBounds({ ...bounds, height: clamped })
}
