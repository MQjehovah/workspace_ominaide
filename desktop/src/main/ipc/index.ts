import axios from 'axios'
import { app, ipcMain, BrowserWindow, dialog } from 'electron'
import { join, basename } from 'path'
import { existsSync, readFileSync, mkdirSync, cpSync, writeFileSync, createWriteStream } from 'fs'
import { getPlugins, getPanels, executeCommand, getPluginPage, reloadNewPlugins } from '../plugin/host'
import { getConfig, setConfig } from '../config'
import { getCustomShortcuts, addCustomShortcut, removeCustomShortcut, getBuiltinShortcuts, updateBuiltinShortcut } from '../shortcut'
import * as screenshot from '../screenshot'
import { showEditor, pinImage, saveImage, copyImage, closeEditor, closeAllPins } from '../pinWindow'
import { clipboard as electronClipboard, nativeImage, BrowserWindow as BW } from 'electron'

let nutLoader: any = null
function getNut(): any {
  if (nutLoader) return nutLoader
  nutLoader = require('@nut-tree-fork/nut-js')
  return nutLoader
}

const buttonMap: Record<string, string> = { left: 'LEFT', right: 'RIGHT', middle: 'MIDDLE' }

const keyMap: Record<string, string> = {
  KeyA: 'A', KeyB: 'B', KeyC: 'C', KeyD: 'D', KeyE: 'E', KeyF: 'F', KeyG: 'G', KeyH: 'H', KeyI: 'I', KeyJ: 'J',
  KeyK: 'K', KeyL: 'L', KeyM: 'M', KeyN: 'N', KeyO: 'O', KeyP: 'P', KeyQ: 'Q', KeyR: 'R', KeyS: 'S', KeyT: 'T',
  KeyU: 'U', KeyV: 'V', KeyW: 'W', KeyX: 'X', KeyY: 'Y', KeyZ: 'Z',
  Digit0: 'Num0', Digit1: 'Num1', Digit2: 'Num2', Digit3: 'Num3', Digit4: 'Num4',
  Digit5: 'Num5', Digit6: 'Num6', Digit7: 'Num7', Digit8: 'Num8', Digit9: 'Num9',
  Enter: 'Enter', Space: 'Space', Backspace: 'Backspace', Tab: 'Tab', Escape: 'Escape',
  ShiftLeft: 'LeftShift', ShiftRight: 'RightShift',
  ControlLeft: 'LeftControl', ControlRight: 'RightControl',
  AltLeft: 'LeftAlt', AltRight: 'RightAlt',
  ArrowUp: 'Up', ArrowDown: 'Down', ArrowLeft: 'Left', ArrowRight: 'Right',
  Semicolon: 'Semicolon', Quote: 'Quote', Comma: 'Comma', Period: 'Period', Slash: 'Slash', Backquote: 'Grave', Backslash: 'Backslash', Minus: 'Minus', Equal: 'Equal',
  BracketLeft: 'LeftBracket', BracketRight: 'RightBracket',
  CapsLock: 'CapsLock',
  MetaLeft: 'LeftSuper', MetaRight: 'RightSuper',
  Numpad0: 'NumPad0', Numpad1: 'NumPad1', Numpad2: 'NumPad2', Numpad3: 'NumPad3', Numpad4: 'NumPad4',
  Numpad5: 'NumPad5', Numpad6: 'NumPad6', Numpad7: 'NumPad7', Numpad8: 'NumPad8', Numpad9: 'NumPad9',
  NumpadEnter: 'Enter', NumpadAdd: 'Add', NumpadSubtract: 'Subtract', NumpadMultiply: 'Multiply', NumpadDivide: 'Divide', NumpadDecimal: 'Decimal',
  Home: 'Home', End: 'End', PageUp: 'PageUp', PageDown: 'PageDown', Insert: 'Insert', Delete: 'Delete',
  F1: 'F1', F2: 'F2', F3: 'F3', F4: 'F4', F6: 'F6', F7: 'F7', F8: 'F8', F9: 'F9', F10: 'F10',
}

export function registerIpcHandlers() {
  // Config
  ipcMain.handle('config:get', async (_, key: string) => (await getConfig())?.[key])
  ipcMain.handle('config:set', async (_, key: string, value: any) => setConfig(key, value))

  // Auth
  ipcMain.handle('auth:set', async (_, serverUrl: string, token: string) => {
    await setConfig('serverUrl', serverUrl)
    await setConfig('token', token)
  })
  // Plugin management
  ipcMain.handle('plugin:list', async () => {
    const cfg = await getConfig()
    const disabled: string[] = cfg.disabledPlugins || []
    return getPlugins().filter(p => !disabled.includes(p.id))
  })
  ipcMain.handle('plugin:list-all', async () => {
    const cfg = await getConfig()
    const disabled: string[] = cfg.disabledPlugins || []
    return getPlugins().map(p => ({ ...p, enabled: !disabled.includes(p.id) }))
  })
  ipcMain.handle('plugin:get-panels', async () => {
    const cfg = await getConfig()
    const disabled: string[] = cfg.disabledPlugins || []
    return getPanels().filter(p => !disabled.includes(p.pluginId))
  })
  ipcMain.handle('plugin:get-page', (_, pluginId: string) => ({ pluginId, hasPage: !!getPluginPage(pluginId) }))
  ipcMain.handle('plugin:execute', async (_, pluginId: string, command: string, args?: unknown) => {
    try { return await executeCommand(pluginId, command, args) }
    catch (e) { return { error: (e as Error).message } }
  })
  ipcMain.handle('plugin:get-panel-data', async (_, pluginId: string) => {
    try {
      const result = await executeCommand(pluginId, 'getPanelData')
      if (result && typeof result === 'object' && !result.error) {
        return {
          title: result.title || pluginId,
          subtitle: result.subtitle || undefined,
          description: result.description || undefined,
          items: (result.items || []).map((i: any) => ({
            title: i.title || '',
            subtitle: i.subtitle || undefined,
            action: i.action || undefined,
            actionArgs: i.actionArgs || undefined,
          })),
          switches: (result.switches || []).map((s: any) => ({
            label: s.label || '',
            value: !!s.value,
            command: s.command || '',
            commandArgs: s.commandArgs || undefined,
          })),
          buttons: (result.buttons || []).map((b: any) => ({
            label: b.label || '',
            command: b.command || '',
          })),
        }
      }
      if (result?.error) {
        console.warn(`[panel-data] ${pluginId}: execute error:`, result.error)
      }
    } catch (e: any) {
      console.warn(`[panel-data] ${pluginId}:`, e?.message)
    }
    return null
  })
  ipcMain.handle('plugin:set-enabled', async (_, pluginId: string, enabled: boolean) => {
    const cfg = await getConfig()
    const disabled: string[] = cfg.disabledPlugins || []
    if (enabled) {
      cfg.disabledPlugins = disabled.filter((id: string) => id !== pluginId)
    } else {
      if (!disabled.includes(pluginId)) disabled.push(pluginId)
      cfg.disabledPlugins = disabled
    }
    await setConfig('disabledPlugins', cfg.disabledPlugins)
    // Notify all windows to refresh plugin data
    BrowserWindow.getAllWindows().forEach(win => win.webContents.send('plugins:updated'))
  })
  ipcMain.handle('plugin:import', async () => {
    const result = await dialog.showOpenDialog({ properties: ['openDirectory'] })
    if (result.canceled) return { success: false }
    const pluginPath = result.filePaths[0]
    const pkgPath = join(pluginPath, 'package.json')
    if (!existsSync(pkgPath)) return { success: false, error: '所选目录没有 package.json' }
    try {
      const pkg = JSON.parse(readFileSync(pkgPath, 'utf-8'))
      const pluginId = pkg.omniaide?.id || pkg.name
      const dest = join(__dirname, '../../../plugins', pluginId)
      if (existsSync(dest)) return { success: false, error: '插件 ' + pluginId + ' 已存在' }
      mkdirSync(dest, { recursive: true })
      cpSync(pluginPath, dest, { recursive: true })
      await reloadNewPlugins()
      return { success: true, pluginId }
    } catch { return { success: false, error: '导入失败' } }
  })
  ipcMain.handle('plugin:list-marketplace', async () => {
    try {
      const cfg = await getConfig()
      const base = cfg.serverUrl || 'http://localhost:8000'
      const res = await axios.get(`${base}/api/plugins/marketplace`, {
        headers: { Authorization: 'Bearer ' + (cfg.token || '') }
      })
      return res.data
    } catch { return [] }
  })
  ipcMain.handle('plugin:install-from-market', async (_, pluginId: string) => {
    try {
      const cfg = await getConfig()
      const base = cfg.serverUrl || 'http://localhost:8000'
      const url = `${base}/api/plugins/marketplace/${pluginId}/download`
      const res = await axios.get(url, {
        responseType: 'stream',
        headers: { Authorization: 'Bearer ' + (cfg.token || '') }
      })

      const pluginsDir = join(app.getPath('userData'), 'plugins')
      const dest = join(pluginsDir, pluginId)
      if (existsSync(dest)) return { success: false, error: '插件已存在' }
      mkdirSync(dest, { recursive: true })

      const zipPath = join(dest, 'plugin.zip')
      await new Promise<void>((resolve, reject) => {
        const writer = createWriteStream(zipPath)
        res.data.pipe(writer)
        writer.on('finish', resolve)
        writer.on('error', reject)
      })

      // Extract zip
      const { execSync } = require('child_process')
      const { platform } = require('os')
      if (platform() === 'win32') {
        execSync(`powershell -Command "Expand-Archive -Path '${zipPath}' -DestinationPath '${dest}' -Force"`, { stdio: 'ignore' })
      } else {
        execSync(`unzip -o "${zipPath}" -d "${dest}"`, { stdio: 'ignore' })
      }
      writeFileSync(join(dest, '.installed_from'), `marketplace:${pluginId}`)

      // Notify windows to reload plugins
      BrowserWindow.getAllWindows().forEach(win => {
        if (!win.isDestroyed()) win.webContents.send('plugins:updated')
      })

      return { success: true, pluginId }
    } catch (e) {
      return { success: false, error: String(e) }
    }
  })
  ipcMain.handle('plugin:reload', async () => {
    try {
      const started = await reloadNewPlugins()
      return { success: true, started }
    } catch (e) {
      return { success: false, error: String(e) }
    }
  })

  // Shortcuts
  ipcMain.handle('shortcut:list', async () => getCustomShortcuts())
  ipcMain.handle('shortcut:add', async (_, binding: any) => addCustomShortcut(binding))
  ipcMain.handle('shortcut:remove', async (_, accelerator: string) => removeCustomShortcut(accelerator))
  ipcMain.handle('shortcut:get-builtin', async () => getBuiltinShortcuts())
  ipcMain.handle('shortcut:update-builtin', async (_, key: string, accelerator: string) => updateBuiltinShortcut(key, accelerator))

  // Search
  ipcMain.handle('search:plugin', async (_, keyword: string, query: string) => {
    const allPlugins = getPlugins()
    const results: any[] = []
    for (const plugin of allPlugins) {
      try {
        const res = await executeCommand(plugin.id, '__search__', { keyword, query })
        if (Array.isArray(res)) results.push(...res)
      } catch {}
      if (results.length >= 20) break
    }
    return results.slice(0, 20)
  })
  ipcMain.handle('search:get-providers', async () => {
    const allPlugins = getPlugins()
    const providers: any[] = []
    for (const plugin of allPlugins) {
      try {
        const res = await executeCommand(plugin.id, '__search__', { getProviders: true })
        if (Array.isArray(res)) providers.push(...res)
      } catch {}
    }
    return providers
  })

  // API proxy
  async function tryRefresh(): Promise<boolean> {
    try {
      const c = await getConfig()
      if (!c.refresh_token) return false
      const res = await axios.post(`${c.serverUrl || 'http://localhost:8000'}/api/auth/refresh`,
        { refresh_token: c.refresh_token },
        { headers: { Authorization: 'Bearer ' + (c.token || '') } }
      )
      if (res.data?.access_token && res.data?.refresh_token) {
        await setConfig('token', res.data.access_token)
        await setConfig('refresh_token', res.data.refresh_token)
        return true
      }
    } catch {}
    return false
  }

  async function apiRequest(method: string, path: string, body?: any) {
    const c = await getConfig()
    const baseUrl = c.serverUrl || 'http://localhost:8000'
    const headers: any = { Authorization: 'Bearer ' + (c.token || '') }
    if (body && !(body instanceof FormData)) headers['Content-Type'] = 'application/json'
    try {
      const res = await axios({ method, url: `${baseUrl}/api${path}`, headers, data: body })
      return res.data
    } catch (err: any) {
      if (err?.response?.status === 401) {
        const refreshed = await tryRefresh()
        if (refreshed) {
          const c2 = await getConfig()
          headers.Authorization = 'Bearer ' + (c2.token || '')
          const retry = await axios({ method, url: `${baseUrl}/api${path}`, headers, data: body })
          return retry.data
        }
        await setConfig('token', '')
        BrowserWindow.getAllWindows().forEach(w => w.close())
      }
      throw err
    }
  }

  ipcMain.handle('api:get', async (_, path: string) => apiRequest('get', path))
  ipcMain.handle('api:post', async (_, path: string, body?: any) => apiRequest('post', path, body))
  ipcMain.handle('api:put', async (_, path: string, body?: any) => apiRequest('put', path, body))
  ipcMain.handle('api:delete', async (_, path: string) => apiRequest('delete', path))

  // Window
  ipcMain.handle('window:open-search', async () => {
    const cfg = await getConfig()
    if (!cfg.token) return
    const searchWin = new BrowserWindow({
      width: 640, height: 400, resizable: false, frame: false, transparent: true,
      webPreferences: { preload: join(__dirname, '../preload/index.js'), contextIsolation: true },
    })
    const url = process.env.VITE_DEV_SERVER_URL
      ? `${process.env.VITE_DEV_SERVER_URL}?view=search`
      : 'file://' + join(__dirname, '../../dist/index.html').replace(/\\/g, '/') + '?view=search'
    searchWin.loadURL(url)
    searchWin.on('blur', () => searchWin.close())
  })
  ipcMain.handle('window:open-plugin-manager', async () => {
    const cfg = await getConfig()
    if (!cfg.token) return
    const win = new BrowserWindow({
      width: 500, height: 640, frame: false, resizable: true, show: false,
      webPreferences: { preload: join(__dirname, '../preload/index.js'), contextIsolation: true },
    })
    const url = process.env.VITE_DEV_SERVER_URL
      ? `${process.env.VITE_DEV_SERVER_URL}?view=plugin-manager`
      : 'file://' + join(__dirname, '../../dist/index.html').replace(/\\/g, '/') + '?view=plugin-manager'
    win.loadURL(url)
    win.once('ready-to-show', () => win.show())
  })
  ipcMain.handle('window:hide', () => {
    BrowserWindow.getFocusedWindow()?.hide()
  })

  ipcMain.handle('shell:open-external', (_, url: string) => {
    const { shell } = require('electron')
    shell.openExternal(url)
  })

  ipcMain.handle('file:open-url', async (_, url: string, name: string) => {
    const { shell } = require('electron')
    const tmp = join(app.getPath('temp'), 'omniaide-' + name)
    try {
      const res = await axios.get(url, { responseType: 'arraybuffer' })
      writeFileSync(tmp, Buffer.from(res.data))
      shell.openPath(tmp)
    } catch {}
  })

  ipcMain.handle('dialog:select-folder', async () => {
    const result = await dialog.showOpenDialog({ properties: ['openDirectory'] })
    return result.canceled ? null : result.filePaths[0]
  })

  // Screenshot
  ipcMain.handle('screenshot:get-all-screens', async () => {
    try {
      const cached = screenshot.getCachedScreenshot()
      if (cached) return cached
      return await screenshot.captureAllScreens()
    } catch (e) {
      console.error('screenshot:get-all-screens error:', e)
      return { displays: [], images: [] }
    }
  })

  ipcMain.handle('screenshot:capture', async (_, x: number, y: number, width: number, height: number) => {
    try {
      const dataUrl = await screenshot.captureRegion(x, y, width, height)
      if (dataUrl) {
        screenshot.addToHistory(dataUrl, 'region', width, height)
        screenshot.cancelScreenshot()
        showEditor(dataUrl)
      }
      return dataUrl
    } catch (e) {
      console.error('screenshot:capture error:', e)
      return null
    }
  })

  ipcMain.handle('screenshot:capture-fullscreen', async () => {
    try {
      return await screenshot.captureFullscreen()
    } catch (e) {
      console.error('screenshot:capture-fullscreen error:', e)
      return null
    }
  })

  ipcMain.handle('screenshot:get-history', async () => screenshot.getHistory())
  ipcMain.handle('screenshot:delete-history', async (_, id: string) => screenshot.deleteFromHistory(id))
  ipcMain.handle('screenshot:clear-history', async () => screenshot.clearHistory())

  ipcMain.on('screenshot:start', async () => {
    try { await screenshot.startScreenshot() } catch (e) { console.error('screenshot:start error:', e) }
  })
  ipcMain.on('screenshot:cancel', () => screenshot.cancelScreenshot())
  ipcMain.on('screenshot:show-editor', (_, dataUrl: string) => showEditor(dataUrl))
  ipcMain.on('screenshot:pin', (_, dataUrl: string) => pinImage(dataUrl))
  ipcMain.on('screenshot:pin-close', (event) => {
    const win = BW.fromWebContents(event.sender)
    if (win && !win.isDestroyed()) win.close()
  })
  ipcMain.on('screenshot:save', async (_, dataUrl: string) => {
    try { await saveImage(dataUrl) } catch (e) { console.error('screenshot:save error:', e) }
  })
  ipcMain.on('screenshot:close-editor', () => closeEditor())
  ipcMain.on('screenshot:close-all-pins', () => closeAllPins())

  ipcMain.handle('clipboard:write-image', async (_, dataUrl: string) => {
    try { await copyImage(dataUrl); return true } catch { return false }
  })

  ipcMain.handle('remote:get-sources', async () => {
    try {
      const { desktopCapturer } = require('electron')
      const sources = await desktopCapturer.getSources({ types: ['screen'], fetchWindowIcons: false, thumbnailSize: { width: 1, height: 1 } })
      return sources.map((s: any) => ({ id: s.id, name: s.name, display_id: s.display_id }))
    } catch {
      return []
    }
  })

  ipcMain.handle('remote:screen-size', async () => {
    try {
      const { screen } = require('electron')
      const d = screen.getPrimaryDisplay()
      const sf = d.scaleFactor || 1
      return { width: Math.round(d.bounds.width * sf), height: Math.round(d.bounds.height * sf) }
    } catch {
      return { width: 0, height: 0 }
    }
  })

  ipcMain.handle('remote:get-all-displays', async () => {
    try {
      const { screen } = require('electron')
      return screen.getAllDisplays().map((d: any) => ({
        id: d.id,
        name: `${d.bounds.width}x${d.bounds.height}`,
        bounds: { x: d.bounds.x, y: d.bounds.y, width: d.bounds.width, height: d.bounds.height },
        scaleFactor: d.scaleFactor || 1,
      }))
    } catch {
      return []
    }
  })

  ipcMain.handle('remote:inject', async (_e, event: any) => {
    try {
      const nut = getNut()
      const ev = event || {}
      if (ev.type === 'mouseMove') {
        await nut.mouse.setPosition(new nut.Point(Math.round(ev.x), Math.round(ev.y)))
      } else if (ev.type === 'mouseDown') {
        const b = buttonMap[ev.button]
        if (b && nut.Button[b] !== undefined) await nut.mouse.pressButton(nut.Button[b])
      } else if (ev.type === 'mouseUp') {
        const b = buttonMap[ev.button]
        if (b && nut.Button[b] !== undefined) await nut.mouse.releaseButton(nut.Button[b])
      } else if (ev.type === 'wheel') {
        const amt = Math.max(1, Math.min(10, Math.round(Math.abs(ev.deltaY) / 100) || 1))
        if (ev.deltaY > 0) await nut.mouse.scrollDown(amt)
        else await nut.mouse.scrollUp(amt)
      } else if (ev.type === 'keyDown') {
        const k = keyMap[ev.code]
        if (k && nut.Key[k] !== undefined) await nut.keyboard.pressKey(nut.Key[k])
      } else if (ev.type === 'keyUp') {
        const k = keyMap[ev.code]
        if (k && nut.Key[k] !== undefined) await nut.keyboard.releaseKey(nut.Key[k])
      }
      return { ok: true }
    } catch (e: any) {
      return { ok: false, error: e?.message || String(e) }
    }
  })
}
