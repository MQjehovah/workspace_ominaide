import { BrowserWindow, desktopCapturer, screen, clipboard, nativeImage } from 'electron'
import { join } from 'path'

let screenshotWindows: BrowserWindow[] = []

export interface ScreenshotRecord {
  id: string
  dataUrl: string
  time: number
  type: 'region' | 'fullscreen'
  width: number
  height: number
}

const MAX_HISTORY = 50
let screenshotHistory: ScreenshotRecord[] = []

export function addToHistory(dataUrl: string, type: 'region' | 'fullscreen', width: number, height: number): ScreenshotRecord {
  const record: ScreenshotRecord = {
    id: Date.now().toString() + Math.random().toString(36).slice(2, 6),
    dataUrl,
    time: Date.now(),
    type,
    width,
    height,
  }
  screenshotHistory.unshift(record)
  if (screenshotHistory.length > MAX_HISTORY) {
    screenshotHistory = screenshotHistory.slice(0, MAX_HISTORY)
  }
  return record
}

export function getHistory(): ScreenshotRecord[] {
  return screenshotHistory
}

export function deleteFromHistory(id: string): void {
  screenshotHistory = screenshotHistory.filter(r => r.id !== id)
}

export function clearHistory(): void {
  screenshotHistory = []
}

let cachedScreenshot: { displays: DisplayInfo[]; images: string[] } | null = null

export function getCachedScreenshot() {
  return cachedScreenshot
}

export function clearCachedScreenshot(): void {
  cachedScreenshot = null
}

export interface DisplayInfo {
  id: number
  bounds: { x: number; y: number; width: number; height: number }
  scaleFactor: number
  isPrimary: boolean
  label: string
}

export async function getDisplays(): Promise<DisplayInfo[]> {
  const displays = screen.getAllDisplays()
  const primaryId = screen.getPrimaryDisplay().id
  return displays.map((d, index) => ({
    id: d.id,
    bounds: d.bounds,
    scaleFactor: d.scaleFactor,
    isPrimary: d.id === primaryId,
    label: d.id === primaryId ? '主屏幕' : `屏幕 ${index + 1}`,
  }))
}

interface PhysicalRect { x: number; y: number; width: number; height: number }

interface PhysicalLayout {
  rects: Map<number, PhysicalRect>
  totalWidth: number
  totalHeight: number
}

export function computePhysicalLayout(displays: { id: number; bounds: { x: number; y: number; width: number; height: number }; scaleFactor: number }[]): PhysicalLayout {
  const rects = new Map<number, PhysicalRect>()
  for (const d of displays) {
    rects.set(d.id, {
      x: 0, y: 0,
      width: Math.floor(d.bounds.width * d.scaleFactor),
      height: Math.floor(d.bounds.height * d.scaleFactor),
    })
  }
  const sortedByX = [...displays].sort((a, b) => a.bounds.x - b.bounds.x)
  for (const d of sortedByX) {
    let physX = 0
    for (const other of displays) {
      if (other.id === d.id) continue
      if (other.bounds.x + other.bounds.width <= d.bounds.x) {
        const r = rects.get(other.id)!
        physX = Math.max(physX, r.x + r.width)
      }
    }
    rects.get(d.id)!.x = physX
  }
  const sortedByY = [...displays].sort((a, b) => a.bounds.y - b.bounds.y)
  for (const d of sortedByY) {
    let physY = 0
    for (const other of displays) {
      if (other.id === d.id) continue
      if (other.bounds.y + other.bounds.height <= d.bounds.y) {
        const r = rects.get(other.id)!
        physY = Math.max(physY, r.y + r.height)
      }
    }
    rects.get(d.id)!.y = physY
  }
  let totalWidth = 0, totalHeight = 0
  rects.forEach(r => {
    totalWidth = Math.max(totalWidth, r.x + r.width)
    totalHeight = Math.max(totalHeight, r.y + r.height)
  })
  return { rects, totalWidth: Math.max(totalWidth, 1), totalHeight: Math.max(totalHeight, 1) }
}

function extractSourceNumber(name: string): number {
  const match = name.match(/(\d+)/)
  if (!match) return -1
  const num = parseInt(match[1], 10)
  return num > 0 && num < 100 ? num : -1
}

export function matchSourceToDisplay(
  display: DisplayInfo,
  sources: Electron.DesktopCapturerSource[],
  usedSourceIndices: Set<number>,
): Electron.DesktopCapturerSource | null {
  for (let si = 0; si < sources.length; si++) {
    if (usedSourceIndices.has(si)) continue
    const s = sources[si]
    if (s.display_id && String(display.id) === s.display_id) {
      usedSourceIndices.add(si)
      return s
    }
  }
  const expectedW = Math.floor(display.bounds.width * display.scaleFactor)
  const expectedH = Math.floor(display.bounds.height * display.scaleFactor)
  for (let si = 0; si < sources.length; si++) {
    if (usedSourceIndices.has(si)) continue
    const s = sources[si]
    const { width, height } = s.thumbnail.getSize()
    if (Math.abs(width - expectedW) <= 2 && Math.abs(height - expectedH) <= 2) {
      usedSourceIndices.add(si)
      return s
    }
  }
  const allDisplays = screen.getAllDisplays()
  const sortedDisplays = [...allDisplays].sort((a, b) => a.bounds.x - b.bounds.x || a.bounds.y - b.bounds.y)
  const targetIdx = sortedDisplays.findIndex(d => d.id === display.id)
  if (targetIdx >= 0) {
    const numberedSources: { source: Electron.DesktopCapturerSource; index: number; num: number }[] = []
    for (let si = 0; si < sources.length; si++) {
      if (usedSourceIndices.has(si)) continue
      const num = extractSourceNumber(sources[si].name)
      if (num > 0) numberedSources.push({ source: sources[si], index: si, num })
    }
    if (numberedSources.length > 0) {
      numberedSources.sort((a, b) => a.num - b.num)
      const matched = numberedSources.find(e => e.num === targetIdx + 1)
      if (matched) {
        usedSourceIndices.add(matched.index)
        return matched.source
      }
      if (targetIdx < numberedSources.length) {
        const fallback = numberedSources[targetIdx]
        usedSourceIndices.add(fallback.index)
        return fallback.source
      }
    }
  }
  for (let si = 0; si < sources.length; si++) {
    if (usedSourceIndices.has(si)) continue
    usedSourceIndices.add(si)
    return sources[si]
  }
  return null
}

export async function captureAllScreens(): Promise<{ displays: DisplayInfo[]; images: string[] }> {
  const displays = await getDisplays()
  if (displays.length === 0) return { displays, images: [] }

  const layout = computePhysicalLayout(displays)
  const dipVirtualLeft = Math.min(...displays.map(d => d.bounds.x))
  const dipVirtualTop = Math.min(...displays.map(d => d.bounds.y))
  const dipVirtualWidth = Math.max(...displays.map(d => d.bounds.x + d.bounds.width)) - dipVirtualLeft
  const dipVirtualHeight = Math.max(...displays.map(d => d.bounds.y + d.bounds.height)) - dipVirtualTop

  const sources = await desktopCapturer.getSources({
    types: ['screen'],
    thumbnailSize: { width: layout.totalWidth, height: layout.totalHeight },
  })

  const images: string[] = []
  if (sources.length === 0) return { displays, images }

  if (sources.length === 1 && displays.length > 1) {
    const source = sources[0]
    const thumbSize = source.thumbnail.getSize()
    const distToPhysical = Math.abs(thumbSize.width - layout.totalWidth)
    const distToDip = Math.abs(thumbSize.width - dipVirtualWidth)
    const usePhysicalLayout = distToPhysical <= distToDip
    const scaleX = thumbSize.width / (usePhysicalLayout ? layout.totalWidth : dipVirtualWidth)
    const scaleY = thumbSize.height / (usePhysicalLayout ? layout.totalHeight : dipVirtualHeight)

    for (const display of displays) {
      let cx: number, cy: number, cw: number, ch: number
      if (usePhysicalLayout) {
        const pr = layout.rects.get(display.id)!
        cx = Math.max(0, Math.floor(pr.x * scaleX))
        cy = Math.max(0, Math.floor(pr.y * scaleY))
        cw = Math.max(1, Math.min(Math.floor(pr.width * scaleX), thumbSize.width - cx))
        ch = Math.max(1, Math.min(Math.floor(pr.height * scaleY), thumbSize.height - cy))
      } else {
        cx = Math.max(0, Math.floor((display.bounds.x - dipVirtualLeft) * scaleX))
        cy = Math.max(0, Math.floor((display.bounds.y - dipVirtualTop) * scaleY))
        cw = Math.max(1, Math.min(Math.floor(display.bounds.width * scaleX), thumbSize.width - cx))
        ch = Math.max(1, Math.min(Math.floor(display.bounds.height * scaleY), thumbSize.height - cy))
      }
      try {
        const cropped = source.thumbnail.crop({ x: cx, y: cy, width: cw, height: ch })
        images.push(cropped.toDataURL())
      } catch {
        images.push('')
      }
    }
  } else {
    const sortedDisplays = [...displays].sort((a, b) => {
      if (a.bounds.x !== b.bounds.x) return a.bounds.x - b.bounds.x
      return a.bounds.y - b.bounds.y
    })
    const allDisplays = screen.getAllDisplays()
    const sourceEntries = sources.map((s, idx) => {
      let pos = idx * 9999
      let matchedDisp = allDisplays.find(d => s.display_id && String(d.id) === s.display_id)
      if (!matchedDisp) {
        const { width, height } = s.thumbnail.getSize()
        matchedDisp = allDisplays.find(d => {
          const ew = Math.floor(d.bounds.width * d.scaleFactor)
          const eh = Math.floor(d.bounds.height * d.scaleFactor)
          return Math.abs(width - ew) <= 2 && Math.abs(height - eh) <= 2
        })
      }
      if (matchedDisp) pos = matchedDisp.bounds.x
      return { source: s, index: idx, pos }
    })
    const allDefaultPos = sourceEntries.every(e => e.pos % 9999 === 0 && e.pos !== 0)
    if (allDefaultPos && sourceEntries.length > 1) {
      sourceEntries.sort((a, b) => {
        const numA = extractSourceNumber(a.source.name)
        const numB = extractSourceNumber(b.source.name)
        if (numA > 0 && numB > 0) return numA - numB
        return a.index - b.index
      })
    } else {
      sourceEntries.sort((a, b) => a.pos - b.pos)
    }
    const matchResults = new Map<number, Electron.DesktopCapturerSource>()
    const usedSourceIndices = new Set<number>()
    for (let si = 0; si < sourceEntries.length && si < sortedDisplays.length; si++) {
      const display = sortedDisplays[si]
      const sourceInfo = sourceEntries[si]
      if (!usedSourceIndices.has(sourceInfo.index)) {
        matchResults.set(display.id, sourceInfo.source)
        usedSourceIndices.add(sourceInfo.index)
      }
    }
    for (const display of sortedDisplays) {
      if (!matchResults.has(display.id)) {
        const source = matchSourceToDisplay(display, sources, usedSourceIndices)
        if (source) matchResults.set(display.id, source)
      }
    }
    for (const display of displays) {
      const source = matchResults.get(display.id) || sources[0] || null
      if (!source) { images.push(''); continue }
      images.push(source.thumbnail.toDataURL())
    }
  }
  return { displays, images }
}

export function rectsIntersect(a: { x: number; y: number; width: number; height: number }, b: { x: number; y: number; width: number; height: number }): boolean {
  return !(a.x + a.width <= b.x || b.x + b.width <= a.x || a.y + a.height <= b.y || b.y + b.height <= a.y)
}

export function rectIntersection(a: { x: number; y: number; width: number; height: number }, b: { x: number; y: number; width: number; height: number }) {
  const x = Math.max(a.x, b.x)
  const y = Math.max(a.y, b.y)
  const right = Math.min(a.x + a.width, b.x + b.width)
  const bottom = Math.min(a.y + a.height, b.y + b.height)
  if (x >= right || y >= bottom) return null
  return { x, y, width: right - x, height: bottom - y }
}

export async function captureRegion(screenX: number, screenY: number, width: number, height: number): Promise<string | null> {
  if (width <= 0 || height <= 0) return null
  const allDisplays = screen.getAllDisplays()
  if (allDisplays.length === 0) return null

  const cached = getCachedScreenshot()
  if (cached && cached.images.length > 0) {
    return captureRegionFromCache(cached, allDisplays, screenX, screenY, width, height)
  }
  return captureRegionFromDesktopCapturer(allDisplays, screenX, screenY, width, height)
}

function captureRegionFromCache(
  cached: { displays: DisplayInfo[]; images: string[] },
  allDisplays: Electron.Display[],
  screenX: number, screenY: number, width: number, height: number,
): string | null {
  const selRect = { x: screenX, y: screenY, width, height }
  const intersecting = allDisplays.filter(d => rectsIntersect(selRect, d.bounds))
  if (intersecting.length === 0) return null

  if (intersecting.length === 1) {
    const d = intersecting[0]
    const displayIdx = cached.displays.findIndex(dd => dd.id === d.id)
    if (displayIdx < 0 || !cached.images[displayIdx]) return null
    const img = nativeImage.createFromDataURL(cached.images[displayIdx])
    const imgSize = img.getSize()
    const scaleX = imgSize.width / d.bounds.width
    const scaleY = imgSize.height / d.bounds.height
    const localX = screenX - d.bounds.x
    const localY = screenY - d.bounds.y
    const cropX = Math.max(0, Math.floor(localX * scaleX))
    const cropY = Math.max(0, Math.floor(localY * scaleY))
    const cropW = Math.max(1, Math.min(Math.floor(width * scaleX), imgSize.width - cropX))
    const cropH = Math.max(1, Math.min(Math.floor(height * scaleY), imgSize.height - cropY))
    const cropped = img.crop({ x: cropX, y: cropY, width: cropW, height: cropH })
    const dataUrl = cropped.toDataURL()
    clipboard.writeImage(nativeImage.createFromDataURL(dataUrl))
    return dataUrl
  }

  const maxScale = Math.max(...allDisplays.map(d => d.scaleFactor))
  const compositeW = Math.floor(width * maxScale)
  const compositeH = Math.floor(height * maxScale)
  const compositeBuffer = Buffer.alloc(compositeW * compositeH * 4, 0)
  const sorted = [...intersecting].sort((a, b) => a.bounds.x - b.bounds.x)

  for (const d of sorted) {
    const intersection = rectIntersection(selRect, d.bounds)
    if (!intersection) continue
    const displayIdx = cached.displays.findIndex(dd => dd.id === d.id)
    if (displayIdx < 0 || !cached.images[displayIdx]) continue
    const img = nativeImage.createFromDataURL(cached.images[displayIdx])
    const imgSize = img.getSize()
    const sx = imgSize.width / d.bounds.width
    const sy = imgSize.height / d.bounds.height
    const cropX = Math.floor((intersection.x - d.bounds.x) * sx)
    const cropY = Math.floor((intersection.y - d.bounds.y) * sy)
    const cropW = Math.floor(intersection.width * sx)
    const cropH = Math.floor(intersection.height * sy)
    const safeX = Math.min(Math.max(cropX, 0), imgSize.width - 1)
    const safeY = Math.min(Math.max(cropY, 0), imgSize.height - 1)
    const safeW = Math.min(cropW, imgSize.width - safeX)
    const safeH = Math.min(cropH, imgSize.height - safeY)
    if (safeW <= 0 || safeH <= 0) continue
    let cropped = img.crop({ x: safeX, y: safeY, width: safeW, height: safeH })
    if (d.scaleFactor !== maxScale) {
      const ratio = maxScale / d.scaleFactor
      cropped = cropped.resize({ width: Math.floor(safeW * ratio), height: Math.floor(safeH * ratio) })
    }
    const cs = cropped.getSize()
    const buf = cropped.toBitmap()
    const pasteX = Math.floor((intersection.x - screenX) * maxScale)
    const pasteY = Math.floor((intersection.y - screenY) * maxScale)
    for (let row = 0; row < cs.height; row++) {
      const srcRow = row * cs.width * 4
      const dstRow = (pasteY + row) * compositeW * 4 + pasteX * 4
      if (dstRow + cs.width * 4 <= compositeBuffer.length) {
        buf.copy(compositeBuffer, dstRow, srcRow, srcRow + cs.width * 4)
      }
    }
  }
  const composited = nativeImage.createFromBuffer(compositeBuffer, { width: compositeW, height: compositeH })
  const compositeUrl = composited.toDataURL()
  clipboard.writeImage(nativeImage.createFromDataURL(compositeUrl))
  return compositeUrl
}

async function captureRegionFromDesktopCapturer(
  allDisplays: Electron.Display[],
  screenX: number, screenY: number, width: number, height: number,
): Promise<string | null> {
  const layout = computePhysicalLayout(allDisplays)
  const sources = await desktopCapturer.getSources({
    types: ['screen'],
    thumbnailSize: { width: layout.totalWidth, height: layout.totalHeight },
  })
  if (sources.length === 0) return null

  if (sources.length === 1 && allDisplays.length > 1) {
    const source = sources[0]
    const thumbSize = source.thumbnail.getSize()
    const scaleX = thumbSize.width / layout.totalWidth
    const scaleY = thumbSize.height / layout.totalHeight
    const targetDisplay = allDisplays.find(d =>
      screenX >= d.bounds.x && screenX < d.bounds.x + d.bounds.width &&
      screenY >= d.bounds.y && screenY < d.bounds.y + d.bounds.height,
    )
    if (!targetDisplay) return null
    const pr = layout.rects.get(targetDisplay.id)!
    const physSelX = pr.x + (screenX - targetDisplay.bounds.x) * targetDisplay.scaleFactor
    const physSelY = pr.y + (screenY - targetDisplay.bounds.y) * targetDisplay.scaleFactor
    const physSelW = width * targetDisplay.scaleFactor
    const physSelH = height * targetDisplay.scaleFactor
    const cx = Math.max(0, Math.floor(physSelX * scaleX))
    const cy = Math.max(0, Math.floor(physSelY * scaleY))
    const cw = Math.max(1, Math.min(Math.floor(physSelW * scaleX), thumbSize.width - cx))
    const ch = Math.max(1, Math.min(Math.floor(physSelH * scaleY), thumbSize.height - cy))
    const cropped = source.thumbnail.crop({ x: cx, y: cy, width: cw, height: ch })
    const dataUrl = cropped.toDataURL()
    clipboard.writeImage(nativeImage.createFromDataURL(dataUrl))
    return dataUrl
  }

  const selRect = { x: screenX, y: screenY, width, height }
  const intersectingDisplays = allDisplays.filter(d => rectsIntersect(selRect, d.bounds))
  if (intersectingDisplays.length === 0) return null

  if (intersectingDisplays.length === 1) {
    const d = intersectingDisplays[0]
    const source = sources[0]
    const thumbSize = source.thumbnail.getSize()
    const pixelScaleX = thumbSize.width / d.bounds.width
    const pixelScaleY = thumbSize.height / d.bounds.height
    const cropX = Math.floor(Math.max(0, screenX - d.bounds.x) * pixelScaleX)
    const cropY = Math.floor(Math.max(0, screenY - d.bounds.y) * pixelScaleY)
    const cropW = Math.floor(width * pixelScaleX)
    const cropH = Math.floor(height * pixelScaleY)
    const cropped = source.thumbnail.crop({
      x: Math.min(cropX, thumbSize.width - 1),
      y: Math.min(cropY, thumbSize.height - 1),
      width: Math.max(1, Math.min(cropW, thumbSize.width - cropX)),
      height: Math.max(1, Math.min(cropH, thumbSize.height - cropY)),
    })
    const dataUrl = cropped.toDataURL()
    clipboard.writeImage(nativeImage.createFromDataURL(dataUrl))
    return dataUrl
  }

  const maxScale = Math.max(...allDisplays.map(d => d.scaleFactor))
  const compositeW = Math.floor(width * maxScale)
  const compositeH = Math.floor(height * maxScale)
  const compositeBuffer = Buffer.alloc(compositeW * compositeH * 4, 0)
  const sortedDisplays = [...intersectingDisplays].sort((a, b) => a.bounds.x - b.bounds.x)

  for (const d of sortedDisplays) {
    const intersection = rectIntersection(selRect, d.bounds)
    if (!intersection) continue
    const source = sources[0]
    const thumbSize = source.thumbnail.getSize()
    const cropX = Math.floor((intersection.x - d.bounds.x) * d.scaleFactor)
    const cropY = Math.floor((intersection.y - d.bounds.y) * d.scaleFactor)
    const cropW = Math.floor(intersection.width * d.scaleFactor)
    const cropH = Math.floor(intersection.height * d.scaleFactor)
    const safeX = Math.min(Math.max(cropX, 0), thumbSize.width - 1)
    const safeY = Math.min(Math.max(cropY, 0), thumbSize.height - 1)
    const safeW = Math.min(cropW, thumbSize.width - safeX)
    const safeH = Math.min(cropH, thumbSize.height - safeY)
    if (safeW <= 0 || safeH <= 0) continue
    let cropped = source.thumbnail.crop({ x: safeX, y: safeY, width: safeW, height: safeH })
    if (d.scaleFactor !== maxScale) {
      const ratio = maxScale / d.scaleFactor
      cropped = cropped.resize({ width: Math.floor(safeW * ratio), height: Math.floor(safeH * ratio) })
    }
    const cs = cropped.getSize()
    const buf = cropped.toBitmap()
    const pasteX = Math.floor((intersection.x - screenX) * maxScale)
    const pasteY = Math.floor((intersection.y - screenY) * maxScale)
    for (let row = 0; row < cs.height; row++) {
      const srcRow = row * cs.width * 4
      const dstRow = (pasteY + row) * compositeW * 4 + pasteX * 4
      if (dstRow + cs.width * 4 <= compositeBuffer.length) {
        buf.copy(compositeBuffer, dstRow, srcRow, srcRow + cs.width * 4)
      }
    }
  }
  const composited = nativeImage.createFromBuffer(compositeBuffer, { width: compositeW, height: compositeH })
  const compositeUrl = composited.toDataURL()
  clipboard.writeImage(nativeImage.createFromDataURL(compositeUrl))
  return compositeUrl
}

export async function startScreenshot(): Promise<void> {
  if (screenshotWindows.length > 0) {
    for (const w of screenshotWindows) { w.show(); w.focus() }
    return
  }

  try {
    cachedScreenshot = await captureAllScreens()
  } catch (e) {
    console.error('Pre-capture failed:', e)
    cachedScreenshot = null
  }

  const allDisplays = screen.getAllDisplays()

  // ★ 每块屏一个独立覆盖窗口
  //   Windows 多 DPI 下窗口尺寸无法精确匹配屏幕，渲染端自适应
  for (const display of allDisplays) {
    const { bounds } = display
    const win = new BrowserWindow({
      x: bounds.x,
      y: bounds.y,
      width: bounds.width,
      height: bounds.height,
      frame: false,
      enableLargerThanScreen: true,
      backgroundColor: '#1a1a2e',
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

    const baseUrl = process.env.VITE_DEV_SERVER_URL
    if (baseUrl) {
      win.loadURL(`${baseUrl}?view=screenshot`)
    } else {
      win.loadFile(join(__dirname, '../../dist/index.html'), { query: { view: 'screenshot' } })
    }

    win.once('ready-to-show', () => {
      win.setPosition(bounds.x, bounds.y)
      win.setSize(bounds.width, bounds.height)
      win.show()
      win.focus()
    })

    win.on('closed', () => {
      screenshotWindows = screenshotWindows.filter(w => w !== win)
      if (screenshotWindows.length === 0) {
        cachedScreenshot = null
      }
    })

    screenshotWindows.push(win)
  }
}

export function cancelScreenshot(): void {
  for (const w of screenshotWindows) {
    if (!w.isDestroyed()) w.close()
  }
  screenshotWindows = []
  cachedScreenshot = null
}

export async function captureFullscreen(): Promise<string | null> {
  const result = await captureAllScreens()
  const primaryIdx = result.displays.findIndex(d => d.isPrimary)
  if (primaryIdx < 0 || !result.images[primaryIdx]) return null
  const dataUrl = result.images[primaryIdx]
  const display = result.displays[primaryIdx]
  clipboard.writeImage(nativeImage.createFromDataURL(dataUrl))
  addToHistory(dataUrl, 'fullscreen', display.bounds.width, display.bounds.height)
  return dataUrl
}
