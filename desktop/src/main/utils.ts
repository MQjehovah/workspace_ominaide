import { BrowserWindow } from 'electron'
import { join } from 'path'

export function loadView(win: BrowserWindow, view: string) {
  const baseUrl = process.env.VITE_DEV_SERVER_URL
  if (baseUrl) {
    win.loadURL(`${baseUrl}?view=${view}`)
  } else {
    win.loadFile(join(__dirname, '../../dist/index.html'), { query: { view } })
  }
}
