import { BrowserWindow, screen, clipboard, nativeImage, dialog } from 'electron'
import { join } from 'path'
import { loadView } from './utils'
import { writeFileSync } from 'fs'

let editorWindow: BrowserWindow | null = null
const pinWindows: Map<string, BrowserWindow> = new Map()

export async function showEditor(dataUrl: string): Promise<void> {
  if (editorWindow) {
    editorWindow.show()
    editorWindow.focus()
    editorWindow.webContents.send('screenshot-editor:set-image', dataUrl)
    return
  }

  const primaryDisplay = screen.getPrimaryDisplay()
  const { width: screenW, height: screenH } = primaryDisplay.workAreaSize

  // ★ 根据截图实际尺寸设置窗口大小
  const img = nativeImage.createFromDataURL(dataUrl)
  const imgSize = img.getSize()
  const toolbarH = 52 + 40 // 工具栏 + 状态栏
  const padding = 40
  const windowWidth = Math.min(900, screenW - 80)
  const windowHeight = Math.min(700, screenH - 80)

  editorWindow = new BrowserWindow({
    width: windowWidth,
    height: windowHeight,
    x: Math.floor((screenW - windowWidth) / 2),
    y: Math.floor((screenH - windowHeight) / 2),
    frame: false,
    transparent: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: true,
    show: false,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  })

  loadView(editorWindow, 'screenshot-editor')

  editorWindow.webContents.once('did-finish-load', () => {
    editorWindow?.show()
    editorWindow?.focus()
    setTimeout(() => {
      editorWindow?.webContents.send('screenshot-editor:set-image', dataUrl)
    }, 100)
  })

  editorWindow.on('closed', () => {
    editorWindow = null
  })
}

function buildPinSkeletonHtml(): string {
  return '<!DOCTYPE html><html><head><style>' +
    '*{margin:0;padding:0;box-sizing:border-box}' +
    'html,body{width:100%;height:100%;overflow:hidden;background:#fff}' +
    '#pin{position:relative;width:100%;height:100%;overflow:hidden;-webkit-app-region:drag}' +
    '#pin-img{width:100%;height:100%;display:block;pointer-events:none;user-select:none;-webkit-user-select:none;image-rendering:-webkit-optimize-contrast}' +
    '#close-btn{position:absolute;top:4px;right:4px;width:22px;height:22px;border-radius:50%;border:none;' +
    'background:rgba(0,0,0,.5);cursor:pointer;z-index:1000;padding:0;display:flex;align-items:center;justify-content:center;' +
    '-webkit-app-region:no-drag;transition:background .15s,opacity .15s;opacity:.5}' +
    '#close-btn:hover{background:rgba(255,0,0,.8);opacity:1}' +
    '#pin:hover #close-btn{opacity:.8}' +
    '</style></head><body>' +
    '<div id="pin"><img id="pin-img">' +
    '<button id="close-btn"><svg width="10" height="10" viewBox="0 0 10 10"><path d="M1.5 1.5L8.5 8.5M8.5 1.5L1.5 8.5" stroke="#fff" stroke-width="1.5" stroke-linecap="round" fill="none"/></svg></button>' +
    '</div></body></html>'
}

function buildPinInjectScript(safeUrl: string): string {
  return '(function(){' +
    'var i=document.getElementById("pin-img"),c=document.getElementById("close-btn");' +
    'i.src=' + safeUrl + ';' +
    'c.addEventListener("click",function(e){e.stopPropagation();window.mqbox.screenshot.pinClose()})' +
    '})()'
}

export async function pinImage(dataUrl: string): Promise<void> {
  const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  const image = nativeImage.createFromDataURL(dataUrl)
  const size = image.getSize()
  const primaryDisplay = screen.getPrimaryDisplay()
  const { width: screenWidth, height: screenHeight } = primaryDisplay.workAreaSize

  let w = size.width
  let h = size.height
  if (w > screenWidth * 0.9) {
    const ratio = screenWidth * 0.9 / w
    w = Math.floor(w * ratio)
    h = Math.floor(h * ratio)
  }
  if (h > screenHeight * 0.9) {
    const ratio = screenHeight * 0.9 / h
    h = Math.floor(h * ratio)
    w = Math.floor(w * ratio)
  }

  const initialX = Math.floor((screenWidth - w) / 2) + primaryDisplay.bounds.x
  const initialY = Math.floor((screenHeight - h) / 2) + primaryDisplay.bounds.y

  const win = new BrowserWindow({
    width: w,
    height: h,
    x: initialX,
    y: initialY,
    show: false,
    frame: false,
    transparent: false,
    backgroundColor: '#ffffff',
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    hasShadow: false,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  })

  ;(win as any)._expectedW = w
  ;(win as any)._expectedH = h

  if (process.platform === 'win32') {
    const WM_MOUSEWHEEL = 0x020A
    win.hookWindowMessage(WM_MOUSEWHEEL, (wParam: Buffer, lParam: Buffer) => {
      if (win.isDestroyed()) return
      const zDelta = wParam.readInt16LE(2)
      const screenX = lParam.readInt16LE(0)
      const screenY = lParam.readInt16LE(2)
      const factor = zDelta > 0 ? 1.15 : 1 / 1.15
      const [curW, curH] = win.getSize()
      const nw = Math.max(50, Math.round(curW * factor))
      const nh = Math.max(50, Math.round(curH * factor))
      const [winX, winY] = win.getPosition()
      const mx = screenX - winX
      const my = screenY - winY
      const ratioX = mx / curW
      const ratioY = my / curH
      const newX = Math.round(winX + mx - ratioX * nw)
      const newY = Math.round(winY + my - ratioY * nh)
      ;(win as any)._expectedW = nw
      ;(win as any)._expectedH = nh
      win.setBounds({ x: newX, y: newY, width: nw, height: nh })
    })
  }

  win.loadURL('data:text/html,' + encodeURIComponent(buildPinSkeletonHtml()))

  win.webContents.once('did-finish-load', async () => {
    try {
      const safeUrl = JSON.stringify(dataUrl)
      await win.webContents.executeJavaScript(buildPinInjectScript(safeUrl))
      if (!win.isDestroyed()) { win.show(); win.focus() }
    } catch {
      if (!win.isDestroyed()) { win.show(); win.focus() }
    }
  })

  win.on('closed', () => {
    pinWindows.delete(id)
  })

  pinWindows.set(id, win)
}

export async function saveImage(dataUrl: string): Promise<void> {
  const result = await dialog.showSaveDialog({
    title: '保存截图',
    defaultPath: `screenshot_${Date.now()}.png`,
    filters: [{ name: 'PNG 图片', extensions: ['png'] }],
  })
  if (result.filePath) {
    const base64 = dataUrl.split(',')[1]
    writeFileSync(result.filePath, Buffer.from(base64, 'base64'))
  }
}

export async function copyImage(dataUrl: string): Promise<void> {
  clipboard.writeImage(nativeImage.createFromDataURL(dataUrl))
}

export function closeEditor(): void {
  if (editorWindow) {
    editorWindow.close()
    editorWindow = null
  }
}

export function closeAllPins(): void {
  for (const win of pinWindows.values()) win.close()
  pinWindows.clear()
}
