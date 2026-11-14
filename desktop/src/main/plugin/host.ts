import { join } from 'path'
import { app, clipboard, BrowserWindow, Notification, shell, dialog, desktopCapturer, screen, Menu } from 'electron'
import { readClipboardTextSafe } from '../clipboard'
import { existsSync } from 'fs'
import { Low } from 'lowdb'
import axios from 'axios'
import { getConfig, setConfig } from '../config'
import * as screenshot from '../screenshot'
import { showEditor } from '../pinWindow'
import { writeLog } from '../logger'
import type {
  PluginInfo,
  PluginPanel,
  SearchProvider,
  ContextMenuItem,
  TrayMenuItem,
  PaletteItem,
  SelectionAction,
} from '../../shared/types'
import {
  PERMISSIONS,
  expandPermissions,
  requiredPermissionsForBridge,
  describePermissions,
  isHighRisk,
  type PermissionId,
} from '../permissions'
import type { PluginManifest } from '../../shared/types'
import {
  startEventSources,
  setEventDispatcher,
  emitEvent as emitPluginEvent,
  hasSubscribers as hasEventSubscribers,
  subscribe as subscribePluginEvent,
  unsubscribe as unsubscribePluginEvent,
  emitFromPlugin,
  clearPluginSubscriptions,
} from './events'
import {
  startScheduler,
  registerSchedule,
  unregisterSchedule,
  clearPluginSchedules,
  listSchedules,
} from './scheduler'
import { loadPlugins } from './loader'
import { PluginProcessManager } from './child-process'
import { channelSend, channelStatus, setInboundDispatcher } from '../backendChannel'
import { handleLocalToolMessage } from '../localTools'

const processManager = new PluginProcessManager()
const plugins = new Map<string, PluginInfo>()
const panels: PluginPanel[] = []

function dispatchPluginEvent(pluginId: string, event: string, payload: unknown): void {
  const proc = processManager.getProcess(pluginId)
  if (!proc) return
  if (event === 'schedule') {
    proc.sendEvent('schedule', payload, 'schedule', (payload as any)?.id)
  } else {
    proc.sendEvent(event, payload, 'event')
  }
}
setEventDispatcher(dispatchPluginEvent)

// ---- Plugin-contributed extension points --------------------------------
const trayItemsByPlugin = new Map<string, TrayMenuItem[]>()
const paletteItems = new Map<string, PaletteItem & { pluginId: string; key: string }>()
const selectionActions = new Map<string, SelectionAction & { pluginId: string; key: string }>()
let trayChangedHandler: (() => void) | null = null

export function onTrayItemsChanged(cb: () => void): void {
  trayChangedHandler = cb
}

function clearPluginExtensions(pluginId: string): void {
  trayItemsByPlugin.delete(pluginId)
  for (const [key, item] of paletteItems) if (item.pluginId === pluginId) paletteItems.delete(key)
  for (const [key, item] of selectionActions) if (item.pluginId === pluginId) selectionActions.delete(key)
}

export function getTrayItems(): Array<TrayMenuItem & { pluginId: string; key: string }> {
  const out: Array<TrayMenuItem & { pluginId: string; key: string }> = []
  for (const [pluginId, items] of trayItemsByPlugin) {
    for (const [index, item] of items.entries()) {
      out.push({ ...item, pluginId, key: `${pluginId}:tray:${index}:${item.id}` })
    }
  }
  return out
}

export function getPaletteItems(): Array<PaletteItem & { pluginId: string; key: string }> {
  return [...paletteItems.values()]
}

export function getSelectionActions(): Array<SelectionAction & { pluginId: string; key: string }> {
  return [...selectionActions.values()]
}

export function getSelectionAction(key: string) {
  return selectionActions.get(key) || null
}

// ---- Permission policy --------------------------------------------------

export interface PluginGrant {
  permissions: PermissionId[]
  declared: PermissionId[]
  version: string
  approvedAt: number
  /** Plugin existed before the permission system; undeclared uses are grandfathered. */
  legacy?: boolean
  /** The user explicitly declined the request; do not prompt again. */
  denied?: boolean
  /** Permissions the user explicitly revoked; never auto-restore these. */
  revoked?: PermissionId[]
}

export interface PluginPermissionState {
  pluginId: string
  displayName: string
  declared: PermissionId[]
  granted: PermissionId[]
  pending: PermissionId[]
  legacy: boolean
  denied: boolean
}

const grants = new Map<string, PluginGrant>()
let baselineIds = new Set<string>()

function isTrustedPlugin(info: PluginInfo): boolean {
  // Bundled plugins ship with the app; dev plugins come from the repo.
  if (!app.isPackaged) return true
  return info.path.startsWith(join(process.resourcesPath, 'plugins'))
}

async function persistGrants(): Promise<void> {
  const data: Record<string, PluginGrant> = {}
  for (const [id, grant] of grants) data[id] = grant
  await setConfig('pluginGrants', data)
}

function makeGrant(info: PluginInfo, approved: PermissionId[], legacy: boolean): PluginGrant {
  return {
    permissions: [...new Set(approved)],
    declared: expandPermissions(info.manifest.permissions),
    version: info.manifest.version || '',
    approvedAt: Date.now(),
    legacy,
  }
}

async function initPermissionPolicy(loaded: Map<string, PluginInfo>): Promise<void> {
  const cfg = await getConfig()
  grants.clear()
  const stored = (cfg.pluginGrants || {}) as Record<string, PluginGrant>
  for (const [id, grant] of Object.entries(stored)) {
    if (!grant) continue
    grants.set(id, {
      permissions: Array.isArray(grant.permissions) ? grant.permissions : [],
      declared: Array.isArray(grant.declared) ? grant.declared : [],
      version: grant.version || '',
      approvedAt: grant.approvedAt || Date.now(),
      legacy: !!grant.legacy,
      denied: !!grant.denied,
      revoked: Array.isArray(grant.revoked) ? grant.revoked : [],
    })
  }

  const hasBaseline = Array.isArray(cfg.pluginPermissionBaseline)
  const baseline = new Set<string>(hasBaseline ? cfg.pluginPermissionBaseline : [])
  if (!hasBaseline) {
    // First run after the permission system shipped: grandfather everything
    // currently installed so upgrades do not break working plugins.
    for (const id of loaded.keys()) baseline.add(id)
    await setConfig('pluginPermissionBaseline', [...baseline])
    if (baseline.size > 0) {
      writeLog('system', 'system', `permission baseline created for ${baseline.size} plugins`)
    }
  }
  baselineIds = baseline

  for (const [id, info] of loaded) {
    const declared = expandPermissions(info.manifest.permissions)
    const existing = grants.get(id)
    const legacy = baseline.has(id)
    if (existing) {
      // Keep the declaration in sync with the on-disk manifest.
      existing.declared = declared
      existing.version = info.manifest.version || existing.version
      if (legacy) {
        existing.legacy = true
        const revoked = new Set(existing.revoked || [])
        for (const perm of declared) {
          if (revoked.has(perm)) continue
          if (!existing.permissions.includes(perm)) existing.permissions.push(perm)
        }
      }
      continue
    }
    const approved = declared.filter((perm) => !isHighRisk(perm) || legacy || isTrustedPlugin(info))
    grants.set(id, makeGrant(info, approved, legacy))
  }

  await persistGrants()
}

const runtimePrompted = new Set<string>()

/**
 * A plugin installed before its manifest declared a capability may still call
 * it. Ask the user once at runtime instead of silently breaking the plugin or
 * silently granting dangerous access.
 */
async function promptUndeclaredPermission(
  pluginId: string,
  info: PluginInfo,
  permission: PermissionId,
): Promise<boolean> {
  const key = `${pluginId}:${permission}`
  if (runtimePrompted.has(key)) return false
  if (grants.get(pluginId)?.revoked?.includes(permission)) return false
  runtimePrompted.add(key)

  const meta = PERMISSIONS[permission]
  const { response } = await dialog.showMessageBox({
    type: 'warning',
    title: '插件请求额外权限',
    message: `「${info.manifest.displayName || pluginId}」想使用「${meta.label}」`,
    detail:
      `${meta.description}\n\n` +
      '该插件没有在清单里声明这个权限，可能由旧版本安装。' +
      '允许后本次会话内不再询问，也可以在「插件管理 → 权限」中收回。',
    buttons: ['允许', '拒绝'],
    defaultId: 1,
    cancelId: 1,
    noLink: true,
  })

  if (response !== 0) {
    writeLog(pluginId, 'warn', `runtime permission declined: ${permission}`)
    return false
  }

  let grant = grants.get(pluginId)
  if (!grant) {
    grant = makeGrant(info, [], baselineIds.has(pluginId))
    grants.set(pluginId, grant)
  }
  if (!grant.permissions.includes(permission)) grant.permissions.push(permission)
  grant.approvedAt = Date.now()
  await persistGrants()
  writeLog(pluginId, 'system', `runtime permission granted: ${permission}`)
  return true
}

export async function checkBridgePermission(
  pluginId: string,
  method: string,
): Promise<{ allowed: boolean; error?: string }> {
  const required = requiredPermissionsForBridge(method)
  if (required.length === 0) return { allowed: true }

  const info = knownPlugins.get(pluginId)
  if (!info) return { allowed: false, error: '插件未注册，无法调用该能力' }

  let grant = grants.get(pluginId)
  if (!grant) {
    grant = makeGrant(info, [], baselineIds.has(pluginId))
    grants.set(pluginId, grant)
  }

  if (grant.revoked?.some((perm) => required.includes(perm))) {
    const blocked = required.filter((perm) => grant.revoked!.includes(perm))
    writeLog(pluginId, 'warn', `permission denied (revoked): ${blocked.join(', ')} via ${method}`)
    return {
      allowed: false,
      error: `权限已被收回：${blocked.map((p) => `「${PERMISSIONS[p].label}」`).join('、')}`,
    }
  }

  const missing: PermissionId[] = []
  for (const perm of required) {
    if (grant.permissions.includes(perm)) continue

    if (grant.legacy) {
      // Legacy plugins may use capabilities they never declared. Grant once,
      // audit it, and let the user review/revoke it in the plugin manager.
      grant.permissions.push(perm)
      writeLog(
        pluginId,
        'warn',
        `legacy permission auto-granted: ${perm} via ${method} — review in 插件管理 → 权限`,
      )
      persistGrants().catch(() => {})
      continue
    }

    if (!grant.declared.includes(perm)) {
      // Bundled plugins and dev plugins are trusted: declaration drift should
      // not interrupt them with a prompt.
      if (isTrustedPlugin(info)) {
        grant.permissions.push(perm)
        writeLog(pluginId, 'system', `trusted plugin auto-granted: ${perm}`)
        persistGrants().catch(() => {})
        continue
      }
      if (isHighRisk(perm)) {
        const approved = await promptUndeclaredPermission(pluginId, info, perm)
        if (approved) continue
      }
      writeLog(pluginId, 'warn', `permission denied: ${method} uses undeclared permission ${perm}`)
      return {
        allowed: false,
        error: `权限不足：${method} 需要「${PERMISSIONS[perm].label}」，但插件未声明该权限`,
      }
    }
    missing.push(perm)
  }

  if (missing.length > 0) {
    writeLog(pluginId, 'warn', `permission denied: ${method} requires ${missing.join(', ')}`)
    return {
      allowed: false,
      error: `权限不足：${method} 需要 ${missing.map((p) => `「${PERMISSIONS[p].label}」`).join('、')}`,
    }
  }
  return { allowed: true }
}

export function getPluginPermissionStates(): PluginPermissionState[] {
  return [...knownPlugins.values()].map((info) => {
    const declared = expandPermissions(info.manifest.permissions)
    const grant = grants.get(info.id)
    const granted = grant?.permissions || []
    return {
      pluginId: info.id,
      displayName: info.manifest.displayName || info.id,
      declared,
      granted,
      pending: declared.filter((perm) => !granted.includes(perm)),
      legacy: !!grant?.legacy,
      denied: !!grant?.denied,
    }
  }).sort((a, b) => a.pluginId.localeCompare(b.pluginId))
}

export async function setPluginPermission(
  pluginId: string,
  permission: PermissionId,
  enabled: boolean,
): Promise<{ success: boolean; error?: string }> {
  const info = knownPlugins.get(pluginId)
  if (!info) return { success: false, error: '插件不存在' }
  if (!PERMISSIONS[permission]) return { success: false, error: '未知权限' }

  let grant = grants.get(pluginId)
  if (!grant) {
    grant = makeGrant(info, [], baselineIds.has(pluginId))
    grants.set(pluginId, grant)
  }
  const declared = expandPermissions(info.manifest.permissions)
  if (!declared.includes(permission) && !grant.permissions.includes(permission)) {
    return { success: false, error: '插件未声明该权限' }
  }

  const revoked = new Set(grant.revoked || [])
  if (enabled) {
    if (!grant.permissions.includes(permission)) grant.permissions.push(permission)
    revoked.delete(permission)
    grant.denied = false
  } else {
    grant.permissions = grant.permissions.filter((p) => p !== permission)
    revoked.add(permission)
  }
  grant.revoked = [...revoked]
  grant.approvedAt = Date.now()
  await persistGrants()
  writeLog(pluginId, 'system', `permission ${enabled ? 'granted' : 'revoked'}: ${permission}`)
  broadcastPluginUpdate()
  return { success: true }
}

async function requestPermissionConsent(
  manifest: PluginManifest,
  pluginId: string,
  sourceLabel?: string,
): Promise<boolean> {
  const declared = expandPermissions(manifest.permissions)
  const highRisk = declared.filter(isHighRisk)
  if (highRisk.length === 0) return true

  const existing = grants.get(pluginId)
  if (existing?.denied && sourceLabel !== 'install') return false

  const { response } = await dialog.showMessageBox({
    type: 'warning',
    title: '插件权限确认',
    message: `「${manifest.displayName || pluginId}」请求 ${highRisk.length} 项敏感权限`,
    detail:
      describePermissions(highRisk) +
      '\n\n允许后可在「插件管理 → 权限」中随时收回。' +
      (sourceLabel === 'install' ? '\n拒绝将取消安装。' : '\n拒绝后插件仍会启动，但相关功能不可用。'),
    buttons: ['允许', '拒绝'],
    defaultId: 1,
    cancelId: 1,
    noLink: true,
  })

  if (response !== 0) {
    if (existing) {
      existing.denied = true
      existing.approvedAt = Date.now()
      persistGrants().catch(() => {})
    }
    writeLog(pluginId, 'warn', 'sensitive permissions declined by user')
    return false
  }

  const info = knownPlugins.get(pluginId)
  const approved = info
    ? makeGrant(info, declared, baselineIds.has(pluginId))
    : {
        permissions: [...declared],
        declared,
        version: manifest.version || '',
        approvedAt: Date.now(),
        legacy: false,
      }
  approved.denied = false
  grants.set(pluginId, approved)
  await persistGrants()
  writeLog(pluginId, 'system', `permissions approved: ${declared.join(', ') || 'none'}`)
  return true
}

/** Called by install flows before files are copied. */
export async function requestInstallConsent(
  manifest: PluginManifest,
  pluginId: string,
): Promise<boolean> {
  return requestPermissionConsent(manifest, pluginId, 'install')
}

function pendingHighRisk(info: PluginInfo): PermissionId[] {
  const declared = expandPermissions(info.manifest.permissions)
  const grant = grants.get(info.id)
  if (grant?.legacy) return []
  return declared.filter((perm) => !grant?.permissions.includes(perm)).filter(isHighRisk)
}

// ---- Runtime lifecycle & observability -----------------------------------

export type PluginRuntimeState =
  | 'running'
  | 'starting'
  | 'restarting'
  | 'stopped'
  | 'crashed'
  | 'disabled'

export interface PluginRuntimeStatus {
  id: string
  displayName: string
  version: string
  enabled: boolean
  state: PluginRuntimeState
  pid?: number
  startedAt?: number
  restarts: number
  lastExitCode?: number | null
  lastError?: string
  nextRetryAt?: number
}

interface RuntimeRecord {
  state: PluginRuntimeState
  pid?: number
  startedAt?: number
  restarts: number
  lastExitCode?: number | null
  lastError?: string
  nextRetryAt?: number
}

const knownPlugins = new Map<string, PluginInfo>()
const runtime = new Map<string, RuntimeRecord>()
const disabledPlugins = new Set<string>()
const restartTimers = new Map<string, NodeJS.Timeout>()
const restartAttempts = new Map<string, number>()
const stableTimers = new Map<string, NodeJS.Timeout>()
const intentionalStops = new Set<string>()
let pluginsShuttingDown = false

const MAX_AUTO_RESTARTS = 5
const STABLE_RESET_MS = 60_000

function runtimeRecord(id: string): RuntimeRecord {
  let rec = runtime.get(id)
  if (!rec) {
    rec = { state: 'stopped', restarts: 0 }
    runtime.set(id, rec)
  }
  return rec
}

function patchRuntime(id: string, patch: Partial<RuntimeRecord>): void {
  const rec = runtimeRecord(id)
  Object.assign(rec, patch)
  broadcastPluginUpdate()
}

let broadcastTimer: NodeJS.Timeout | null = null

function broadcastPluginUpdate(): void {
  if (broadcastTimer) return
  broadcastTimer = setTimeout(() => {
    broadcastTimer = null
    BrowserWindow.getAllWindows().forEach(win => {
      if (!win.isDestroyed()) win.webContents.send('plugins:updated')
    })
  }, 150)
}

export function getPluginStatuses(): PluginRuntimeStatus[] {
  return [...knownPlugins.values()].map((info) => {
    const rec = runtime.get(info.id) || { state: 'stopped', restarts: 0 }
    const running = !!processManager.getProcess(info.id)?.isRunning()
    const disabled = disabledPlugins.has(info.id)
    let state: PluginRuntimeState = rec.state
    if (disabled) state = 'disabled'
    else if (running && (state === 'stopped' || state === 'crashed')) state = 'running'
    else if (!running && (state === 'running' || state === 'starting')) state = 'stopped'
    return {
      id: info.id,
      displayName: info.manifest.displayName || info.id,
      version: info.manifest.version || '',
      enabled: !disabled,
      state,
      pid: rec.pid,
      startedAt: rec.startedAt,
      restarts: rec.restarts,
      lastExitCode: rec.lastExitCode,
      lastError: rec.lastError,
      nextRetryAt: rec.nextRetryAt,
    }
  }).sort((a, b) => a.id.localeCompare(b.id))
}

export function markPluginsShuttingDown(): void {
  pluginsShuttingDown = true
  for (const timer of restartTimers.values()) clearTimeout(timer)
  for (const timer of stableTimers.values()) clearTimeout(timer)
  restartTimers.clear()
  stableTimers.clear()
}

/**
 * Start a plugin process, wire lifecycle logging/status and the panel entry.
 * Safe to call again after removePlugin().
 */
async function ensureGrantFor(info: PluginInfo): Promise<void> {
  if (grants.has(info.id)) return
  const declared = expandPermissions(info.manifest.permissions)
  const approved = declared.filter(perm => !isHighRisk(perm) || isTrustedPlugin(info))
  grants.set(info.id, makeGrant(info, approved, baselineIds.has(info.id)))
  await persistGrants()
}

async function startPluginInstance(info: PluginInfo): Promise<boolean> {
  const id = info.id
  try {
    const modulePath = join(info.path, info.manifest.main || 'dist/index.js')
    if (!existsSync(modulePath)) {
      writeLog(id, 'error', `main entry not found: ${modulePath}`)
      patchRuntime(id, { state: 'crashed', lastError: '入口文件不存在' })
      return false
    }

    // Plugins started at runtime (hot install / manual copy) need a grant too.
    await ensureGrantFor(info)

    // Sensitive permissions must be approved before the plugin can use them.
    if (!isTrustedPlugin(info)) {
      const pending = pendingHighRisk(info)
      if (pending.length > 0) {
        await requestPermissionConsent(info.manifest, id, 'startup')
      }
    }

    // A fresh start must not inherit a stale "user stopped it" flag.
    intentionalStops.delete(id)
    patchRuntime(id, { state: 'starting', startedAt: Date.now(), nextRetryAt: undefined })
    writeLog(id, 'system', `starting ${info.manifest.displayName || id} v${info.manifest.version || '?'}`)

    const proc = await processManager.startPlugin(info)
    registerBridgeHandlers(proc)
    attachLifecycle(id, proc)

    const ready = await proc.waitForReady(8000)
    if (!ready) {
      // The process may still start; keep it and surface the warning in logs.
      writeLog(id, 'warn', 'ready timeout after 8000ms')
    }

    plugins.set(id, info)
    if (!panels.some(p => p.pluginId === id)) {
      const hasPage = existsSync(join(info.path, 'frontend', 'index.html'))
      panels.push({ id: `${id}-panel`, pluginId: id, height: 120, hasPage })
    }

    const rec = runtimeRecord(id)
    patchRuntime(id, {
      state: 'running',
      pid: proc.pid,
      startedAt: rec.startedAt || Date.now(),
      lastError: undefined,
      nextRetryAt: undefined,
    })
    writeLog(id, 'system', `running (pid=${proc.pid ?? '?'})`)
    console.log(`[plugin] started in child process: ${id} (${info.manifest.version})`)
    return true
  } catch (e: any) {
    const message = e?.message || String(e)
    writeLog(id, 'error', `failed to start: ${message}`)
    patchRuntime(id, { state: 'crashed', lastError: message })
    console.error(`[plugin] failed to start ${id}:`, e)
    return false
  }
}

function attachLifecycle(id: string, proc: import('./child-process').PluginChildProcess): void {
  proc.on('ready', () => {
    const rec = runtimeRecord(id)
    patchRuntime(id, { state: 'running', pid: proc.pid, startedAt: rec.startedAt || Date.now() })
    // Only treat the plugin as healthy after it stays up for a while.
    const existing = stableTimers.get(id)
    if (existing) clearTimeout(existing)
    stableTimers.set(id, setTimeout(() => {
      stableTimers.delete(id)
      restartAttempts.delete(id)
    }, STABLE_RESET_MS))
  })

  proc.on('stderr', (msg: string) => {
    writeLog(id, 'stderr', msg)
    const trimmed = String(msg).split(/\r?\n/).filter(Boolean).pop() || ''
    // Update silently: chatty plugins would otherwise spam every window.
    if (trimmed) runtimeRecord(id).lastError = trimmed.slice(0, 300)
  })

  proc.on('exit', (code: number | null) => {
    clearPluginSubscriptions(id)
    clearPluginSchedules(id)
    const stable = stableTimers.get(id)
    if (stable) { clearTimeout(stable); stableTimers.delete(id) }

    const intentional = intentionalStops.delete(id)
    const rec = runtimeRecord(id)
    patchRuntime(id, {
      state: intentional ? 'stopped' : 'crashed',
      pid: undefined,
    })
    if (intentional) {
      writeLog(id, 'system', `stopped (code=${code ?? '?'})`)
      return
    }

    writeLog(id, 'error', `exited unexpectedly (code=${code ?? '?'})`)
    if (pluginsShuttingDown) return
    if (disabledPlugins.has(id)) return

    scheduleAutoRestart(id)
  })
}

function scheduleAutoRestart(id: string): void {
  if (restartTimers.has(id)) return
  const attempts = (restartAttempts.get(id) || 0) + 1
  restartAttempts.set(id, attempts)

  if (attempts > MAX_AUTO_RESTARTS) {
    writeLog(id, 'error', `crash loop detected (${MAX_AUTO_RESTARTS} attempts), auto-restart disabled`)
    patchRuntime(id, {
      state: 'crashed',
      lastError: `连续崩溃 ${MAX_AUTO_RESTARTS} 次，已停止自动重启`,
      nextRetryAt: undefined,
    })
    return
  }

  const delay = Math.min(1000 * 2 ** (attempts - 1), 30_000)
  const rec = runtimeRecord(id)
  rec.restarts += 1
  patchRuntime(id, {
    state: 'restarting',
    nextRetryAt: Date.now() + delay,
    lastError: rec.lastError,
  })
  writeLog(id, 'system', `restarting in ${Math.round(delay / 1000)}s (attempt ${attempts}/${MAX_AUTO_RESTARTS})`)

  const timer = setTimeout(async () => {
    restartTimers.delete(id)
    if (pluginsShuttingDown || disabledPlugins.has(id)) return
    const info = knownPlugins.get(id)
    if (!info) return
    await startPluginInstance(info)
  }, delay)
  restartTimers.set(id, timer)
}

export async function restartPlugin(id: string): Promise<{ success: boolean; error?: string }> {
  const info = knownPlugins.get(id) || loadPlugins().get(id)
  if (!info) return { success: false, error: '插件不存在' }
  if (disabledPlugins.has(id)) return { success: false, error: '插件已停用，请先启用' }
  writeLog(id, 'system', 'manual restart requested')
  removePlugin(id)
  restartAttempts.delete(id)
  runtimeRecord(id).restarts = 0
  const ok = await startPluginInstance(info)
  broadcastPluginUpdate()
  return ok ? { success: true } : { success: false, error: '启动失败，请查看日志' }
}

// channel namespace -> pluginId that subscribed to it
const channelSubscriptions = new Map<string, string>()

setInboundDispatcher((channel, msg) => {
  if (channel === 'local-tools') {
    handleLocalToolMessage(msg).catch((err) => {
      writeLog('system', 'error', `local-tools handler error: ${err?.message || err}`)
    })
    return
  }
  const pluginId = channelSubscriptions.get(channel)
  if (!pluginId) return
  const proc = processManager.getProcess(pluginId)
  proc?.executeCommand('channelMessage', { channel, msg }).catch(() => {})
})

export function getProcessManager(): PluginProcessManager {
  return processManager
}

export async function initPlugins() {
  const loaded = loadPlugins()
  const cfg = await getConfig()

  disabledPlugins.clear()
  for (const id of cfg.disabledPlugins || []) disabledPlugins.add(id)

  await initPermissionPolicy(loaded)

  for (const [id, info] of loaded) {
    knownPlugins.set(id, info)
    if (disabledPlugins.has(id)) {
      runtimeRecord(id).state = 'disabled'
      console.log(`[plugin] ${id}: disabled by user, not starting`)
      continue
    }
    await startPluginInstance(info)
  }

  startClipboardMonitoring()
  startEventSources()
  startScheduler(dispatchPluginEvent)
  broadcastPluginUpdate()
}

export async function reloadNewPlugins(): Promise<string[]> {
  const loaded = loadPlugins()
  const cfg = await getConfig()
  for (const id of cfg.disabledPlugins || []) disabledPlugins.add(id)

  const started: string[] = []
  for (const [id, info] of loaded) {
    knownPlugins.set(id, info)
    if (plugins.has(id) || disabledPlugins.has(id)) continue
    if (await startPluginInstance(info)) {
      console.log(`[plugin] hot-loaded: ${id} (${info.manifest.version})`)
      started.push(id)
    }
  }

  if (started.length > 0) broadcastPluginUpdate()
  return started
}

let lastClipboardText = ''
let clipboardTimer: NodeJS.Timeout | null = null
let clipboardBusy = false

function startClipboardMonitoring() {
  if (clipboardTimer) return
  clipboardTimer = setInterval(async () => {
    // Only read the clipboard when a plugin actually needs it.
    if (clipboardBusy || (!plugins.has('clipboard-history') && !hasEventSubscribers('clipboard'))) return
    clipboardBusy = true
    try {
      // Run pbpaste in a child process with a timeout. A stuck macOS
      // pasteboard must never block the Electron main process.
      const text = await readClipboardTextSafe()
      if (!text || text === lastClipboardText) return
      lastClipboardText = text
      emitPluginEvent('clipboard', { text })

      BrowserWindow.getAllWindows().forEach(win => {
        if (!win.isDestroyed()) win.webContents.send('panel:updated', 'clipboard-history')
      })

      const proc = processManager.getProcess('clipboard-history')
      if (proc) {
        proc.executeCommand('onClipboardChange', text).catch(() => {})
      }
    } catch {
    } finally {
      clipboardBusy = false
    }
  }, 1000)
}

const notificationLastAt = new Map<string, number>()

function showPluginNotification(pluginId: string, input: any): void {
  const data = input && typeof input === 'object' ? input : { title: String(input || '') }
  const title = String(data.title || '').trim()
  if (!title) return

  // Per-plugin rate limit: a chatty plugin must not flood the notification center.
  const now = Date.now()
  const last = notificationLastAt.get(pluginId) || 0
  if (now - last < 800) {
    writeLog(pluginId, 'debug', 'notification rate-limited')
    return
  }
  notificationLastAt.set(pluginId, now)

  const actions = Array.isArray(data.actions)
    ? data.actions.filter((a: any) => a && a.id).slice(0, 3)
    : []

  try {
    const notification = new Notification({
      title,
      body: data.body ? String(data.body) : undefined,
      silent: !!data.silent,
      ...(process.platform === 'darwin' && actions.length
        ? { actions: actions.map((a: any) => ({ type: 'button', text: String(a.title || a.id) })) }
        : {}),
    })

    notification.on('click', () => {
      if (data.command) {
        executeCommand(pluginId, String(data.command), data.args).catch((e) => {
          writeLog(pluginId, 'warn', `notification command failed: ${e?.message || e}`)
        })
      } else {
        processManager.getProcess(pluginId)?.sendEvent('notification-click', {
          title,
          body: data.body || '',
        })
      }
      if (data.deepLink && /^https?:\/\//i.test(String(data.deepLink))) {
        shell.openExternal(String(data.deepLink)).catch(() => {})
      }
    })

    notification.on('action', (_event: any, index: number) => {
      const action = actions[index]
      if (!action) return
      if (action.command) {
        executeCommand(pluginId, String(action.command), action.args).catch((e) => {
          writeLog(pluginId, 'warn', `notification action failed: ${e?.message || e}`)
        })
      } else {
        processManager.getProcess(pluginId)?.sendEvent('notification-action', {
          actionId: action.id,
          title,
        })
      }
    })

    notification.show()
  } catch (e: any) {
    writeLog(pluginId, 'warn', `notification failed: ${e?.message || e}`)
  }
}

function registerBridgeHandlers(proc: import('./child-process').PluginChildProcess): void {
  const store = { db: null as Low<any> | null }

  // Central enforcement point: every bridge call (including context.signal)
  // is checked against the plugin's approved permissions.
  proc.setPermissionCheck((method) => checkBridgePermission(proc.pluginId, method))

  clearPluginExtensions(proc.pluginId)

  proc.registerBridgeHandler('log:write', async ([level, message]) => {
    writeLog(proc.pluginId, level, message)
  })

  // Shared backend channel bridges: any plugin can send on a channel namespace
  // and subscribe to inbound messages routed back via 'channelMessage' command.
  proc.registerBridgeHandler('channel:subscribe', async ([channel]) => {
    if (channel) channelSubscriptions.set(String(channel), proc.pluginId)
    return true
  })
  proc.registerBridgeHandler('channel:unsubscribe', async ([channel]) => {
    if (channel && channelSubscriptions.get(String(channel)) === proc.pluginId) {
      channelSubscriptions.delete(String(channel))
    }
    return true
  })
  proc.registerBridgeHandler('channel:send', async ([channel, msg]) => {
    if (channel) channelSend(String(channel), msg || {})
    return true
  })
  proc.registerBridgeHandler('channel:status', async () => channelStatus())

  proc.registerBridgeHandler('api:get', async ([path]) => {
    const cfg = await getConfig()
    const res = await axios.get(`${cfg.serverUrl || 'https://mqgeek.com/ominaide'}/api${path}`, {
      headers: { Authorization: 'Bearer ' + (cfg.token || '') },
      timeout: 15000,
    })
    return res.data
  })

  proc.registerBridgeHandler('api:post', async ([path, body]) => {
    const cfg = await getConfig()
    const base = cfg.serverUrl || 'https://mqgeek.com/ominaide'
    const timeout = String(path).startsWith('/vibecoding/agent') ? 180000 : 15000
    const send = (token: string) => axios.post(`${base}/api${path}`, body, {
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      timeout,
    })
    try {
      const res = await send(cfg.token || '')
      return res.data
    } catch (e: any) {
      if (e.response?.status === 401 && cfg.refresh_token) {
        try {
          const r = await axios.post(`${base}/api/auth/refresh`, { refresh_token: cfg.refresh_token }, {
            headers: { Authorization: 'Bearer ' + (cfg.token || '') },
          })
          if (r.data?.access_token) {
            await setConfig('token', r.data.access_token)
            if (r.data.refresh_token) await setConfig('refresh_token', r.data.refresh_token)
            const res = await send(r.data.access_token)
            return res.data
          }
        } catch { }
      }
      throw new Error(e.response?.data?.detail || e.response?.data || e.message)
    }
  })

  proc.registerBridgeHandler('api:put', async ([path, body]) => {
    const cfg = await getConfig()
    const res = await axios.put(`${cfg.serverUrl || 'https://mqgeek.com/ominaide'}/api${path}`, body, {
      headers: { Authorization: 'Bearer ' + (cfg.token || ''), 'Content-Type': 'application/json' },
      timeout: 15000,
    })
    return res.data
  })

  proc.registerBridgeHandler('api:delete', async ([path]) => {
    const cfg = await getConfig()
    const res = await axios.delete(`${cfg.serverUrl || 'https://mqgeek.com/ominaide'}/api${path}`, {
      headers: { Authorization: 'Bearer ' + (cfg.token || '') },
      timeout: 15000,
    })
    return res.data
  })

  proc.registerBridgeHandler('shell:openPath', async ([path]) => {
    writeLog(proc.pluginId, 'debug', `shell:openPath called: ${String(path)}`)
    const result = await shell.openPath(path)
    writeLog(proc.pluginId, 'debug', `shell:openPath result: ${String(result)}`)
    return result
  })
  proc.registerBridgeHandler('shell:openExternal', async ([url]) => shell.openExternal(url))
  proc.registerBridgeHandler('shell:exec', async ([command, args]) => {
    const { spawn } = require('child_process')
    writeLog(proc.pluginId, 'debug', `shell:exec called: ${String(command)} ${JSON.stringify(args || [])}`)
    try {
      const child = spawn(command, args || [], { detached: true, stdio: 'ignore', windowsHide: true })
      child.on('error', () => {})
      child.unref()
      return { ok: true }
    } catch (e: any) {
      writeLog(proc.pluginId, 'debug', `shell:exec error: ${e.message}`)
      return { ok: false, error: e.message }
    }
  })
  proc.registerBridgeHandler('dialog:showOpenDialog', async ([opts]) => dialog.showOpenDialog(opts))

  // BOM-tolerant JSON adapter: strip UTF-8 BOM on read, write without BOM.
  const jsonAdapter = (file: string) => ({
    async read(): Promise<any> {
      try {
        const raw = require('fs').readFileSync(file, 'utf-8').replace(/^\uFEFF/, '')
        return raw.trim() ? JSON.parse(raw) : {}
      } catch {
        return {}
      }
    },
    async write(data: any): Promise<void> {
      const { mkdirSync } = require('fs')
      const { dirname } = require('path')
      mkdirSync(dirname(file), { recursive: true })
      require('fs').writeFileSync(file, JSON.stringify(data, null, 2), 'utf-8')
    },
  })

  proc.registerBridgeHandler('storage:get', async ([key]) => {
    const file = join(app.getPath('userData'), 'plugin-data', `${proc.pluginId}.json`)
    const adapter = jsonAdapter(file)
    const db = new Low(adapter as any, {})
    await db.read()
    return (db.data as any)?.[key]
  })

  proc.registerBridgeHandler('storage:set', async ([key, value]) => {
    const file = join(app.getPath('userData'), 'plugin-data', `${proc.pluginId}.json`)
    const adapter = jsonAdapter(file)
    const db = new Low(adapter as any, {})
    await db.read()
    ;(db.data as any)[key] = value
    await db.write()
  })

  proc.registerBridgeHandler('config:get', async ([key]) => {
    const cfg = await getConfig()
    return (cfg as any)?.[key]
  })

  proc.registerBridgeHandler('event:subscribe', async ([event, id, options]) => {
    return subscribePluginEvent(proc.pluginId, String(event || ''), String(id || ''), options || {})
  })
  proc.registerBridgeHandler('event:unsubscribe', async ([event, id]) => {
    unsubscribePluginEvent(proc.pluginId, String(event || ''), id ? String(id) : undefined)
    return true
  })
  proc.registerBridgeHandler('event:emit', async ([event, payload]) => {
    const delivered = emitFromPlugin(proc.pluginId, String(event || ''), payload)
    return { ok: true, delivered }
  })
  proc.registerBridgeHandler('schedule:register', async ([spec]) => {
    return registerSchedule(proc.pluginId, spec || {})
  })
  proc.registerBridgeHandler('schedule:unregister', async ([id]) => {
    return { removed: unregisterSchedule(proc.pluginId, id ? String(id) : undefined) }
  })
  proc.registerBridgeHandler('schedule:list', async () => listSchedules(proc.pluginId))

  proc.registerBridgeHandler('notification:show', async ([input, legacyBody]) => {
    showPluginNotification(
      proc.pluginId,
      typeof input === 'string' ? { title: input, body: legacyBody } : input,
    )
  })

  proc.registerBridgeHandler('screenshot:start', async () => { screenshot.startScreenshot() })
  proc.registerBridgeHandler('screenshot:capture-fullscreen', async () => screenshot.captureFullscreen())
  proc.registerBridgeHandler('screenshot:show-editor', async ([dataUrl]) => showEditor(dataUrl))
  proc.registerBridgeHandler('screenshot:get-history', async () => screenshot.getHistory())
  proc.registerBridgeHandler('screenshot:clear-history', async () => screenshot.clearHistory())
  proc.registerBridgeHandler('screenshot:delete-history', async ([id]) => screenshot.deleteFromHistory(id))

  proc.registerBridgeHandler('remote:get-sources', async () => {
    const sources = await desktopCapturer.getSources({
      types: ['screen'], fetchWindowIcons: false, thumbnailSize: { width: 1, height: 1 }
    })
    return sources.map(s => ({ id: s.id, name: s.name, display_id: (s as any).display_id }))
  })

  proc.registerBridgeHandler('remote:screen-size', async () => {
    const d = screen.getPrimaryDisplay()
    const sf = d.scaleFactor || 1
    return { width: Math.round(d.bounds.width * sf), height: Math.round(d.bounds.height * sf) }
  })

  proc.registerBridgeHandler('remote:get-all-displays', async () =>
    screen.getAllDisplays().map(d => ({
      id: d.id, name: `${d.bounds.width}x${d.bounds.height}`,
      bounds: { x: d.bounds.x, y: d.bounds.y, width: d.bounds.width, height: d.bounds.height },
      scaleFactor: d.scaleFactor || 1,
    }))
  )

  proc.registerBridgeHandler('remote:open-connection', async ([hostDeviceId, viewerId]) => {
    console.log('[remote] open-connection window:', { hostDeviceId, viewerId })
    const preloadPath = join(__dirname, '../preload/index.js')
    const display = screen.getPrimaryDisplay().workArea
    const win = new BrowserWindow({
      width: 280, height: 40, show: false, frame: false, resizable: false,
      alwaysOnTop: true, skipTaskbar: true,
      x: display.width - 290, y: display.height - 50,
      webPreferences: { preload: preloadPath, contextIsolation: true, nodeIntegration: false },
    })
    const query = `mode=webrtc-accept${viewerId ? '&viewer=' + viewerId : ''}`
    const url = `plugin-app://remote/index.html?${query}`
    win.loadURL(url)
    win.once('ready-to-show', () => win.show())
    win.on('closed', () => win.destroy())
  })

  // Forward remote WS messages from plugin to App.vue (and disconnect)
  proc.registerBridgeHandler('remote:ws-connect', async ([data]) => {
    console.log('[host] remote:ws-connect signal received', data?.deviceId)
    BrowserWindow.getAllWindows().forEach(win => {
      if (!win.isDestroyed()) win.webContents.send('remote:ws-connect', data)
    })
  })
  proc.registerBridgeHandler('remote:ws-send', async ([data]) => {
    console.log('[host] remote:ws-send: type=' + (data?.type))
    BrowserWindow.getAllWindows().forEach(win => {
      if (!win.isDestroyed()) win.webContents.send('remote:ws-send', data)
    })
  })
  proc.registerBridgeHandler('remote:ws-disconnect', async () => {
    console.log('[host] remote:ws-disconnect')
    BrowserWindow.getAllWindows().forEach(win => {
      if (!win.isDestroyed()) win.webContents.send('remote:ws-disconnect')
    })
  })

  proc.registerBridgeHandler('openPage', async ([pluginId, query]) => {
    const preloadPath = join(__dirname, '../preload/index.js')
    const win = new BrowserWindow({
      width: 900, height: 700,
      webPreferences: { preload: preloadPath, contextIsolation: true },
    })
    const extra = query ? '?' + query : ''
    const url = process.env.VITE_DEV_SERVER_URL
      ? `${process.env.VITE_DEV_SERVER_URL}?view=plugin-page&pluginId=${pluginId}${extra}`
      : `file://${join(__dirname, '../../../dist/index.html').replace(/\\/g, '/')}?view=plugin-page&pluginId=${pluginId}${extra}`
    win.loadURL(url)
  })

  // Electron proxy handlers (child process require('electron') bridge)
  const winMap = new Map<string, BrowserWindow>()

  proc.registerBridgeHandler('BrowserWindow:create', async ([opts]) => {
    // Create window but don't return it to child (child has stub)
    const preloadPath = join(__dirname, '../preload/index.js')
    const win = new BrowserWindow({
      ...opts,
      webPreferences: { ...opts.webPreferences, preload: preloadPath, contextIsolation: true },
    })
    return null // child doesn't use return value
  })
  proc.registerBridgeHandler('BrowserWindow:loadURL', async ([url]) => {})
  proc.registerBridgeHandler('BrowserWindow:show', async () => {})
  proc.registerBridgeHandler('BrowserWindow:focus', async () => {})
  proc.registerBridgeHandler('BrowserWindow:hide', async () => {})
  proc.registerBridgeHandler('BrowserWindow:close', async () => {})
  proc.registerBridgeHandler('BrowserWindow:setAlwaysOnTop', async () => {})
  proc.registerBridgeHandler('BrowserWindow:setSkipTaskbar', async () => {})
  proc.registerBridgeHandler('globalShortcut:register', async ([accelerator]) => {
    const { globalShortcut } = require('electron')
    globalShortcut.register(accelerator, () => {
      proc.executeCommand('toggleAssistant').catch(() => {})
    })
  })
  proc.registerBridgeHandler('globalShortcut:unregister', async ([accelerator]) => {
    const { globalShortcut } = require('electron')
    globalShortcut.unregister(accelerator)
  })
  proc.registerBridgeHandler('globalShortcut:unregisterAll', async () => {
    const { globalShortcut } = require('electron')
    globalShortcut.unregisterAll()
  })
  proc.registerBridgeHandler('clipboard:writeText', async ([text]) => {
    clipboard.writeText(text)
  })
  proc.registerBridgeHandler('clipboard:readText', async () => {
    return readClipboardTextSafe()
  })
  proc.registerBridgeHandler('shell:showItemInFolder', async ([path]) => {
    shell.showItemInFolder(path)
  })
  proc.registerBridgeHandler('panel:updated', async () => {
    BrowserWindow.getAllWindows().forEach(win => {
      if (!win.isDestroyed()) win.webContents.send('panel:updated', proc.pluginId)
    })
  })

  // ---- Rich UI / extension points ---------------------------------------
  proc.registerBridgeHandler('menu:show', async ([items]) => {
    return new Promise<string | null>((resolve) => {
      let resolved = false
      const finish = (value: string | null) => {
        if (resolved) return
        resolved = true
        resolve(value)
      }
      const build = (list: ContextMenuItem[]): Electron.MenuItemConstructorOptions[] => {
        const out: Electron.MenuItemConstructorOptions[] = []
        for (const [index, item] of (list || []).entries()) {
          if (item.type === 'separator') { out.push({ type: 'separator' }); continue }
          const id = item.id || `item-${index}`
          out.push({
            label: item.label || id,
            type: item.type === 'checkbox' ? 'checkbox' : 'normal',
            checked: item.checked,
            enabled: item.enabled !== false,
            submenu: item.submenu ? build(item.submenu) : undefined,
            click: () => finish(id),
          })
        }
        return out
      }
      try {
        const menu = Menu.buildFromTemplate(build(items || []))
        menu.popup({
          window: BrowserWindow.getFocusedWindow() || undefined,
          callback: () => setTimeout(() => finish(null), 0),
        })
      } catch (e) {
        console.error('[menu:show] failed:', e)
        finish(null)
      }
    })
  })

  proc.registerBridgeHandler('tray:set', async ([items]) => {
    const list = Array.isArray(items)
      ? items.filter((i: TrayMenuItem) => !!i && (i.type === 'separator' || !!i.id)).slice(0, 30)
      : []
    trayItemsByPlugin.set(proc.pluginId, list)
    trayChangedHandler?.()
  })

  proc.registerBridgeHandler('palette:register', async ([item]) => {
    if (!item?.id || !item?.title || !item?.command) return
    const key = `${proc.pluginId}:${item.id}`
    paletteItems.set(key, {
      id: String(item.id),
      title: String(item.title),
      subtitle: item.subtitle ? String(item.subtitle) : undefined,
      keywords: Array.isArray(item.keywords) ? item.keywords.map(String) : [],
      icon: item.icon,
      command: String(item.command),
      args: item.args,
      pluginId: proc.pluginId,
      key,
    })
    BrowserWindow.getAllWindows().forEach(win => {
      if (!win.isDestroyed()) win.webContents.send('palette:updated')
    })
  })

  proc.registerBridgeHandler('selection:register', async ([action]) => {
    if (!action?.id || !action?.title || !action?.command) return
    const key = `${proc.pluginId}:${action.id}`
    selectionActions.set(key, {
      id: String(action.id),
      title: String(action.title),
      description: action.description ? String(action.description) : undefined,
      icon: action.icon,
      command: String(action.command),
      args: action.args && typeof action.args === 'object' ? action.args : {},
      pluginId: proc.pluginId,
      key,
    })
  })

  // PTY (pseudo-terminal) for interactive AI sessions
  const ptySessions = new Map<string, any>()
  let ptyCounter = 0

  proc.registerBridgeHandler('pty:create', async ([cmd, cmdArgs, cwd]) => {
    try {
      const { execSync } = require('child_process')
      const isWin = process.platform === 'win32'
      const pty = require('node-pty')
      const id = `pty_${proc.pluginId}_${++ptyCounter}`
      const rows = 30, cols = 120

      // On Windows, wrap in cmd.exe to resolve .cmd/.bat scripts correctly
      const spawnCmd = isWin ? 'cmd.exe' : cmd
      const spawnArgs = isWin ? ['/c', cmd, ...(cmdArgs || [])] : (cmdArgs || [])

      const term = pty.spawn(spawnCmd, spawnArgs, {
        name: 'xterm-color', cols, rows, cwd: cwd || process.cwd(),
        env: { ...process.env, TERM: 'xterm-256color' },
      })
      let output = ''
      term.onData((data: string) => { output += data })
      ptySessions.set(id, { term, read: () => { const o = output; output = ''; return o } })
      term.onExit(() => { output = ''; ptySessions.delete(id) })
      return { id, rows, cols }
    } catch (e: any) {
      return { error: e.message || String(e) }
    }
  })

  proc.registerBridgeHandler('pty:write', async ([id, data]) => {
    const s = ptySessions.get(id)
    if (!s) return { error: 'no session' }
    s.term.write(data)
    return { success: true }
  })

  proc.registerBridgeHandler('pty:read', async ([id]) => {
    const s = ptySessions.get(id)
    if (!s) return { output: '', done: true }
    return { output: s.read(), done: false }
  })

  proc.registerBridgeHandler('pty:kill', async ([id]) => {
    const s = ptySessions.get(id)
    if (s) { s.term.kill(); ptySessions.delete(id) }
  })
}

export async function startPluginById(id: string): Promise<boolean> {
  if (plugins.has(id)) return true
  const info = knownPlugins.get(id) || loadPlugins().get(id)
  if (!info) return false
  knownPlugins.set(id, info)
  disabledPlugins.delete(id)
  const ok = await startPluginInstance(info)
  if (ok) broadcastPluginUpdate()
  return ok
}

export async function setPluginEnabled(id: string, enabled: boolean): Promise<boolean> {
  if (enabled) {
    disabledPlugins.delete(id)
    writeLog(id, 'system', 'enabled by user')
    return startPluginById(id)
  }
  disabledPlugins.add(id)
  writeLog(id, 'system', 'disabled by user')
  removePlugin(id)
  broadcastPluginUpdate()
  return true
}

export function removePlugin(id: string): boolean {
  const timer = restartTimers.get(id)
  if (timer) { clearTimeout(timer); restartTimers.delete(id) }
  const stable = stableTimers.get(id)
  if (stable) { clearTimeout(stable); stableTimers.delete(id) }

  intentionalStops.add(id)
  const proc = processManager.getProcess(id)
  if (proc) processManager.stopPlugin(id)

  clearPluginExtensions(id)
  clearPluginSubscriptions(id)
  clearPluginSchedules(id)
  trayChangedHandler?.()

  const rec = runtimeRecord(id)
  if (disabledPlugins.has(id)) {
    rec.state = 'disabled'
  } else if (rec.state !== 'crashed') {
    rec.state = 'stopped'
  }
  rec.pid = undefined
  rec.nextRetryAt = undefined

  // remove from panels array
  const idx = panels.findIndex(p => p.pluginId === id)
  if (idx >= 0) panels.splice(idx, 1)
  return plugins.delete(id)
}

export function getPlugins(): PluginInfo[] {
  return Array.from(plugins.values())
}

/** All discovered plugins, including disabled or crashed ones. */
export function getAllPlugins(): PluginInfo[] {
  return Array.from(knownPlugins.values())
}

export function getPanels(): PluginPanel[] {
  return panels
}

export function getSearchProviders(): Array<SearchProvider & { pluginId: string }> {
  const providers: Array<SearchProvider & { pluginId: string }> = []
  for (const [id] of plugins) {
    const proc = processManager.getProcess(id)
    if (proc && proc.searchProviders) {
      for (const p of proc.searchProviders as any[]) {
        providers.push({ ...p, pluginId: id })
      }
    }
  }
  return providers
}

export async function executeCommand(pluginId: string, command: string, args?: unknown): Promise<unknown> {
  const proc = processManager.getProcess(pluginId)
  if (!proc) throw new Error(`Plugin ${pluginId} not running`)
  const result = await proc.executeCommand(command, args)

  if (pluginId === 'clipboard-history' && command === 'copy') {
    BrowserWindow.getAllWindows().forEach(win => {
      if (!win.isDestroyed()) win.webContents.send('panel:updated', 'clipboard-history')
    })
  }

  const playerReadonlyCommands = ['getPanelData', 'getPageData', 'cloudGetStreamUrl', 'cloudListPlaylists', 'cloudListSongs', 'cloudListAudioFiles']
  if (pluginId === 'player' && !playerReadonlyCommands.includes(command)) {
    BrowserWindow.getAllWindows().forEach(win => {
      if (!win.isDestroyed()) win.webContents.send('panel:updated', 'player')
    })
  }

  const todoReadonlyCommands = ['getPanelData', 'getPageData']
  if (pluginId === 'todo' && !todoReadonlyCommands.includes(command)) {
    BrowserWindow.getAllWindows().forEach(win => {
      if (!win.isDestroyed()) win.webContents.send('panel:updated', 'todo')
    })
  }

  return result
}

export function getPluginPage(pluginId: string): any {
  return null
}
