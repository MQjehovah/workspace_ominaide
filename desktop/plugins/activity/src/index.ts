import { execFile } from 'child_process'

/**
 * 用户行为采集 plugin.
 *
 * Collects desktop activity (active-window app usage) and optionally clipboard
 * content, and reports them to the cloud event stream (`/api/activities`).
 *
 * PRIVACY: both toggles are OFF by default. The user enables them in the panel.
 * - App usage: app name + window title + duration only.
 * - Clipboard: only a short truncated preview + length/type metadata.
 */

const ACTIVITY_INTERVAL = 15 * 1000
const CLIPBOARD_INTERVAL = 4 * 1000
const MIN_SESSION_MINUTES = 1
const CLIPBOARD_PREVIEW_LEN = 200
const FLUSH_INTERVAL = 60 * 1000 // try to flush buffered events every minute

// Map process names to friendly, aggregated names.
const APP_ALIASES: Record<string, string> = {
  code: 'VSCode', 'code-insiders': 'VSCode', 'cursor': 'Cursor',
  chrome: 'Chrome', msedge: 'Edge', firefox: 'Firefox', opera: 'Opera',
  explorer: '资源管理器', WeChat: '微信', wechat: '微信', QQ: 'QQ',
  WeCom: '企业微信', DingTalk: '钉钉', feishu: '飞书', Lark: '飞书',
  devenv: 'Visual Studio', idea64: 'IntelliJ IDEA', pycharm64: 'PyCharm',
  'WebStorm64': 'WebStorm', goland64: 'GoLand', studio64: 'Android Studio',
  WindowsTerminal: '终端', cmd: '命令行', powershell: 'PowerShell',
  node: 'Node.js', python: 'Python', java: 'Java',
  slack: 'Slack', Teams: 'Teams', zoom: 'Zoom',
}

function normalizeApp(name: string): string {
  const key = (name || '').toLowerCase()
  const map: Record<string, string> = {}
  for (const [k, v] of Object.entries(APP_ALIASES)) map[k.toLowerCase()] = v
  return map[key] || name
}

const WINDOWS_PS = [
  '$OutputEncoding = [System.Text.Encoding]::UTF8;',
  '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8;',
  'Add-Type -TypeDefinition \'using System;using System.Runtime.InteropServices;',
  'public class W{[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();',
  '[DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h,System.Text.StringBuilder t,int c);',
  '[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);}\'',
  '$h=[W]::GetForegroundWindow();',
  '$sb=New-Object System.Text.StringBuilder 512;',
  '[W]::GetWindowText($h,$sb,512)|Out-Null;',
  '$p=0;[W]::GetWindowThreadProcessId($h,[ref]$p)|Out-Null;',
  '$proc=Get-Process -Id $p -ErrorAction SilentlyContinue;',
  'if($proc){Write-Output ($proc.ProcessName+"`t"+$sb.ToString())}',
].join('\n')

let activeWindowInFlight = false

function getActiveWindow(): Promise<{ app: string; title: string } | null> {
  // Prevent overlapping PowerShell calls (which would spawn accumulating processes).
  if (activeWindowInFlight) return Promise.resolve(null)
  activeWindowInFlight = true
  return new Promise((resolve) => {
    if (process.platform !== 'win32') { activeWindowInFlight = false; return resolve(null) }
    // Use -EncodedCommand to avoid Windows command-line quoting/parsing issues.
    const encoded = Buffer.from(WINDOWS_PS, 'utf16le').toString('base64')
    const child = execFile('powershell', ['-NoProfile', '-EncodedCommand', encoded], { timeout: 5000 }, (err, stdout) => {
      activeWindowInFlight = false
      if (err) return resolve(null)
      const line = stdout.trim().split(/\r?\n/)[0] || ''
      const idx = line.indexOf('\t')
      if (idx <= 0) return resolve(null)
      resolve({ app: normalizeApp(line.slice(0, idx)), title: line.slice(idx + 1).trim() })
    })
    // Explicitly kill the child after the timeout so no process leaks.
    setTimeout(() => { try { child.kill() } catch { /* ignore */ } }, 6000)
  })
}

let ctx: any = null
let activityTimer: any = null
let clipboardTimer: any = null
let flushTimer: any = null
let current: { app: string; title: string; startedAt: number } | null = null
let lastClipboard = ''

async function getConfig(): Promise<Record<string, any>> {
  try { return (await ctx?.storage?.get('activity_config')) || {} } catch { return {} }
}

async function saveConfig(cfg: Record<string, any>) {
  try { await ctx?.storage?.set('activity_config', cfg) } catch { /* ignore */ }
}

async function reportEvent(payload: Record<string, unknown>) {
  try {
    await ctx?.api?.post('/activities', payload)
    // After a successful report, try to flush anything buffered while offline.
    await flushBuffer()
  } catch (e: any) {
    console.error('[activity] report failed, buffering:', e?.message || e)
    await bufferEvent(payload)
  }
}

async function bufferEvent(payload: Record<string, unknown>) {
  try {
    const q = (await ctx?.storage?.get('pending_events')) || []
    q.push({ payload, ts: Date.now() })
    await ctx?.storage?.set('pending_events', q.slice(-200))
  } catch { /* ignore */ }
}

async function flushBuffer() {
  let q: any[] = []
  try {
    q = (await ctx?.storage?.get('pending_events')) || []
  } catch { return }
  if (!q.length) return
  const remaining: any[] = []
  for (const item of q) {
    try {
      await ctx?.api?.post('/activities', item.payload)
    } catch {
      remaining.push(item) // keep for later retry
      break // stop on first failure to avoid hammering the backend
    }
  }
  try {
    await ctx?.storage?.set('pending_events', remaining)
  } catch { /* ignore */ }
  if (remaining.length !== q.length) {
    console.log(`[activity] flushed ${q.length - remaining.length} buffered events`)
  }
}

async function activityTick() {
  const win = await getActiveWindow()
  if (!win) return
  const now = Date.now()
  if (!current) { current = { ...win, startedAt: now }; return }
  if (current.app === win.app && current.title === win.title) return
  const minutes = Math.round((now - current.startedAt) / 60000)
  if (minutes >= MIN_SESSION_MINUTES) {
    await reportEvent({
      event_type: 'app.used',
      entity_type: 'app',
      summary: `使用 ${current.app} ${minutes} 分钟`,
      details: {
        app: current.app,
        title: current.title.slice(0, 200),
        minutes,
        end: new Date(now).toISOString(),
      },
    })
  }
  current = { ...win, startedAt: now }
}

async function clipboardTick() {
  try {
    const text = (await ctx?.signal('clipboard:readText')) || ''
    if (!text || text === lastClipboard) return
    lastClipboard = text
    const preview = text.replace(/\s+/g, ' ').trim().slice(0, CLIPBOARD_PREVIEW_LEN)
    await reportEvent({
      event_type: 'clipboard.copy',
      entity_type: 'clipboard',
      summary: '复制内容',
      details: {
        length: text.length,
        type: text.length > 500 ? 'long' : 'short',
        preview,
      },
    })
  } catch { /* ignore */ }
}

function applyTimers() {
  Promise.resolve(getConfig()).then((cfg) => {
    const anyOn = !!cfg.activity || !!cfg.clipboard
    if (anyOn && !flushTimer) {
      flushTimer = setInterval(() => flushBuffer().catch(() => {}), FLUSH_INTERVAL)
    } else if (!anyOn) {
      if (flushTimer) { clearInterval(flushTimer); flushTimer = null }
    }
    if (cfg.activity && !activityTimer) {
      activityTimer = setInterval(() => activityTick().catch(() => {}), ACTIVITY_INTERVAL)
    } else if (!cfg.activity) {
      if (activityTimer) { clearInterval(activityTimer); activityTimer = null }
      current = null
    }
    if (cfg.clipboard && !clipboardTimer) {
      clipboardTimer = setInterval(() => clipboardTick().catch(() => {}), CLIPBOARD_INTERVAL)
    } else if (!cfg.clipboard) {
      if (clipboardTimer) { clearInterval(clipboardTimer); clipboardTimer = null }
      lastClipboard = ''
    }
  })
}

export default {
  async activate(context: any) {
    ctx = context

    context.registerCommand('getPanelData', async () => {
      const cfg = await getConfig()
      const on = !!(cfg.activity || cfg.clipboard)
      return {
        title: '用户行为采集',
        subtitle: on ? '采集已开启' : '未开启',
        description: '采集应用使用与剪贴板内容，供 AI 分析你的行为习惯。默认关闭，隐私可控。',
        switches: [
          { label: '应用活动采集', value: !!cfg.activity, command: 'toggleActivity' },
          { label: '剪贴板采集', value: !!cfg.clipboard, command: 'toggleClipboard' },
        ],
      }
    })

    context.registerCommand('toggleActivity', async () => {
      const cfg = await getConfig()
      cfg.activity = !cfg.activity
      await saveConfig(cfg)
      applyTimers()
      return { value: !!cfg.activity }
    })

    context.registerCommand('toggleClipboard', async () => {
      const cfg = await getConfig()
      cfg.clipboard = !cfg.clipboard
      await saveConfig(cfg)
      applyTimers()
      return { value: !!cfg.clipboard }
    })

    // Start polling if previously enabled (persisted in plugin storage).
    applyTimers()
  },
  deactivate() {
    if (activityTimer) { clearInterval(activityTimer); activityTimer = null }
    if (clipboardTimer) { clearInterval(clipboardTimer); clipboardTimer = null }
    if (flushTimer) { clearInterval(flushTimer); flushTimer = null }
    current = null
  },
}
