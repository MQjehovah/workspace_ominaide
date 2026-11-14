import { powerMonitor, screen, net } from 'electron'
import { watch, existsSync, statSync, type FSWatcher } from 'fs'
import { homedir } from 'os'
import { resolve } from 'path'
import { writeLog } from '../logger'

export interface PluginEventOptions {
  /** Directory (or file) to watch for the `file` event. */
  path?: string
  recursive?: boolean
  /** Seconds of system idle time before `idle` fires. Default 300. */
  thresholdSeconds?: number
}

interface Subscription {
  pluginId: string
  id: string
  event: string
  options: PluginEventOptions
}

type Dispatcher = (pluginId: string, event: string, payload: unknown) => void

const MAX_SUBSCRIPTIONS_PER_PLUGIN = 50
const subscriptions: Subscription[] = []
const watchers = new Map<string, { watcher: FSWatcher; refs: number }>()
const idleStates = new Map<string, boolean>()

let dispatch: Dispatcher | null = null
let started = false
let pollTimer: NodeJS.Timeout | null = null
let lastNetworkOnline: boolean | null = null

export function setEventDispatcher(fn: Dispatcher): void {
  dispatch = fn
}

function normalizePath(input: string): string {
  let value = String(input || '').trim()
  if (!value) return ''
  if (value.startsWith('~')) value = homedir() + value.slice(1)
  return resolve(value)
}

function deliver(pluginId: string, event: string, payload: unknown): void {
  try {
    dispatch?.(pluginId, event, payload)
  } catch (e) {
    writeLog('events', 'warn', `dispatch failed: ${(e as Error)?.message || e}`)
  }
}

function matches(sub: Subscription, event: string, payload: any): boolean {
  if (sub.event !== event) return false
  if (event === 'file') {
    const base = normalizePath(sub.options.path || '')
    const changed = normalizePath(payload?.path || '')
    if (!base || !changed) return false
    return changed === base || changed.startsWith(base.endsWith('/') ? base : base + '/')
  }
  return true
}

export function emitEvent(event: string, payload: unknown): void {
  for (const sub of [...subscriptions]) {
    if (matches(sub, event, payload)) deliver(sub.pluginId, event, payload)
  }
}

/** Custom event from one plugin to every other subscriber. */
export function emitFromPlugin(fromPluginId: string, event: string, payload: unknown): number {
  let delivered = 0
  for (const sub of [...subscriptions]) {
    if (sub.pluginId === fromPluginId) continue
    if (matches(sub, event, payload)) {
      deliver(sub.pluginId, event, payload)
      delivered += 1
    }
  }
  return delivered
}

export function hasSubscribers(event: string): boolean {
  return subscriptions.some(sub => sub.event === event)
}

export function getSubscriptions(pluginId: string): Subscription[] {
  return subscriptions.filter(sub => sub.pluginId === pluginId)
}

function ensureWatcher(path: string): void {
  const key = normalizePath(path)
  if (watchers.has(key)) return
  if (!existsSync(key)) {
    throw new Error(`path does not exist: ${key}`)
  }
  const isDirectory = statSync(key).isDirectory()
  const recursive = isDirectory && process.platform !== 'linux'
  const watcher = watch(key, { recursive }, (eventType, filename) => {
    const changed = filename ? resolve(key, String(filename)) : key
    const exists = existsSync(changed)
    const type = eventType === 'rename' ? (exists ? 'add' : 'unlink') : 'change'
    emitEvent('file', { path: changed, type })
  })
  watcher.on('error', (err) => {
    writeLog('events', 'warn', `file watcher error for ${key}: ${err.message}`)
  })
  watchers.set(key, { watcher, refs: 0 })
}

function refreshWatchers(): void {
  const needed = new Map<string, number>()
  for (const sub of subscriptions) {
    if (sub.event !== 'file' || !sub.options.path) continue
    const key = normalizePath(sub.options.path)
    needed.set(key, (needed.get(key) || 0) + 1)
  }
  for (const [path, entry] of [...watchers]) {
    if (!needed.has(path)) {
      try { entry.watcher.close() } catch {}
      watchers.delete(path)
    }
  }
  for (const path of needed.keys()) {
    if (!watchers.has(path)) {
      try { ensureWatcher(path) } catch (e: any) {
        writeLog('events', 'warn', `cannot watch ${path}: ${e?.message || e}`)
      }
    }
  }
}

export function subscribe(
  pluginId: string,
  event: string,
  id: string,
  options: PluginEventOptions = {},
): { ok: boolean; error?: string } {
  const name = String(event || '').trim()
  if (!name) return { ok: false, error: 'event name is required' }
  if (getSubscriptions(pluginId).length >= MAX_SUBSCRIPTIONS_PER_PLUGIN) {
    return { ok: false, error: `too many subscriptions (max ${MAX_SUBSCRIPTIONS_PER_PLUGIN})` }
  }
  if (name === 'file') {
    if (!options.path) return { ok: false, error: 'file subscriptions require options.path' }
    if (!existsSync(normalizePath(options.path))) {
      return { ok: false, error: `path does not exist: ${options.path}` }
    }
  }
  const existing = subscriptions.find(sub => sub.pluginId === pluginId && sub.event === name && sub.id === id)
  if (existing) existing.options = { ...options }
  else subscriptions.push({ pluginId, id: id || `${name}-${Date.now()}`, event: name, options: { ...options } })

  if (name === 'file') refreshWatchers()
  if (name === 'idle') idleStates.set(`${pluginId}:${id}`, false)
  if (name === 'network') {
    const online = net.isOnline()
    queueMicrotask(() => deliver(pluginId, 'network', { online }))
  }
  return { ok: true }
}

export function unsubscribe(pluginId: string, event: string, id?: string): void {
  for (let i = subscriptions.length - 1; i >= 0; i--) {
    const sub = subscriptions[i]
    if (sub.pluginId !== pluginId) continue
    if (sub.event !== event) continue
    if (id && sub.id !== id) continue
    if (sub.event === 'idle') idleStates.delete(`${pluginId}:${sub.id}`)
    subscriptions.splice(i, 1)
  }
  refreshWatchers()
}

export function clearPluginSubscriptions(pluginId: string): void {
  for (let i = subscriptions.length - 1; i >= 0; i--) {
    const sub = subscriptions[i]
    if (sub.pluginId !== pluginId) continue
    if (sub.event === 'idle') idleStates.delete(`${pluginId}:${sub.id}`)
    subscriptions.splice(i, 1)
  }
  refreshWatchers()
}

function pollIdleAndNetwork(): void {
  // Idle thresholds are per subscription, so each one gets its own transition.
  const idleSeconds = powerMonitor.getSystemIdleTime()
  for (const sub of [...subscriptions]) {
    if (sub.event !== 'idle') continue
    const threshold = Math.max(5, Number(sub.options.thresholdSeconds) || 300)
    const key = `${sub.pluginId}:${sub.id}`
    const idle = idleSeconds >= threshold
    const previous = idleStates.get(key) || false
    if (idle !== previous) {
      idleStates.set(key, idle)
      deliver(sub.pluginId, 'idle', { idle, seconds: idleSeconds })
    }
  }

  const online = net.isOnline()
  if (lastNetworkOnline !== null && online !== lastNetworkOnline) {
    lastNetworkOnline = online
    emitEvent('network', { online })
  } else if (lastNetworkOnline === null) {
    lastNetworkOnline = online
  }
}

export function startEventSources(): void {
  if (started) return
  started = true

  const powerEvents = ['suspend', 'resume', 'lock-screen', 'unlock-screen', 'on-ac', 'on-battery', 'shutdown']
  for (const type of powerEvents) {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(powerMonitor as any).on(type, () => emitEvent('power', { type }))
    } catch {}
  }

  try {
    screen.on('display-added', (_event, display) => {
      emitEvent('display', { type: 'added', display: { id: display.id, bounds: display.bounds, scaleFactor: display.scaleFactor } })
    })
    screen.on('display-removed', (_event, display) => {
      emitEvent('display', { type: 'removed', display: { id: display.id, bounds: display.bounds, scaleFactor: display.scaleFactor } })
    })
    screen.on('display-metrics-changed', (_event, display) => {
      emitEvent('display', { type: 'changed', display: { id: display.id, bounds: display.bounds, scaleFactor: display.scaleFactor } })
    })
  } catch {}

  if (!pollTimer) {
    lastNetworkOnline = net.isOnline()
    pollTimer = setInterval(pollIdleAndNetwork, 5000)
  }
}
