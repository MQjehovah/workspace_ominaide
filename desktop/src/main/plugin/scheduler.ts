import { writeLog } from '../logger'

export interface PluginScheduleSpec {
  id: string
  /** Interval in milliseconds or a string like "30s", "5m", "2h". */
  every?: number | string
  /** Standard five-field cron: minute hour day-of-month month day-of-week. */
  cron?: string
  /** One-shot time (ISO string or epoch milliseconds). */
  at?: string | number
}

interface Job {
  pluginId: string
  spec: PluginScheduleSpec
  nextAt: number | null
  oneShot: boolean
}

type Dispatcher = (pluginId: string, event: string, payload: unknown) => void

const MAX_SCHEDULES_PER_PLUGIN = 50
const jobs = new Map<string, Job>()
const cronCache = new Map<string, ReturnType<typeof parseCron> | null>()

let dispatch: Dispatcher | null = null
let timer: NodeJS.Timeout | null = null

function jobKey(pluginId: string, id: string): string {
  return `${pluginId}:${id}`
}

function parseEvery(value: number | string): number | null {
  if (typeof value === 'number') {
    return Number.isFinite(value) && value >= 1000 ? Math.floor(value) : null
  }
  const match = /^(\d+(?:\.\d+)?)\s*(s|m|h|d)$/i.exec(String(value || '').trim())
  if (!match) return null
  const amount = parseFloat(match[1])
  const unit = match[2].toLowerCase()
  const factor = unit === 's' ? 1000 : unit === 'm' ? 60_000 : unit === 'h' ? 3_600_000 : 86_400_000
  const ms = Math.floor(amount * factor)
  return ms >= 1000 ? ms : null
}

function parseCronField(value: string, min: number, max: number): Set<number> | null {
  const out = new Set<number>()
  for (const part of value.split(',')) {
    const text = part.trim()
    if (!text) return null
    let step = 1
    let range = text
    const stepMatch = /^(.*)\/(\d+)$/.exec(text)
    if (stepMatch) {
      range = stepMatch[1]
      step = parseInt(stepMatch[2], 10)
      if (!step || step < 1) return null
    }
    let start = min
    let end = max
    if (range !== '*') {
      const bounds = range.split('-')
      if (bounds.length === 2) {
        start = parseInt(bounds[0], 10)
        end = parseInt(bounds[1], 10)
      } else {
        start = parseInt(range, 10)
        end = start
      }
      if (!Number.isFinite(start) || !Number.isFinite(end)) return null
      if (start < min || end > max || start > end) return null
    }
    for (let n = start; n <= end; n += step) out.add(n)
  }
  return out.size ? out : null
}

function parseCron(expr: string) {
  const parts = String(expr || '').trim().split(/\s+/)
  if (parts.length !== 5) return null
  const minute = parseCronField(parts[0], 0, 59)
  const hour = parseCronField(parts[1], 0, 23)
  const day = parseCronField(parts[2], 1, 31)
  const month = parseCronField(parts[3], 1, 12)
  const weekdayRaw = parseCronField(parts[4], 0, 7)
  if (!minute || !hour || !day || !month || !weekdayRaw) return null
  const weekday = new Set<number>()
  for (const value of weekdayRaw) weekday.add(value === 7 ? 0 : value)
  return {
    minute,
    hour,
    day,
    month,
    weekday,
    dayRestricted: parts[2] !== '*',
    weekdayRestricted: parts[4] !== '*',
  }
}

function nextCronTime(expr: string, from: number): number | null {
  let parsed = cronCache.get(expr)
  if (parsed === undefined) {
    parsed = parseCron(expr)
    cronCache.set(expr, parsed)
  }
  if (!parsed) return null

  const cursor = new Date(from)
  cursor.setSeconds(0, 0)
  cursor.setMinutes(cursor.getMinutes() + 1)
  for (let i = 0; i < 527040; i++) {
    const month = cursor.getMonth() + 1
    const day = cursor.getDate()
    const weekday = cursor.getDay()
    const domMatch = parsed.day.has(day)
    const dowMatch = parsed.weekday.has(weekday)
    const dayMatch = parsed.dayRestricted && parsed.weekdayRestricted
      ? domMatch || dowMatch
      : domMatch && dowMatch
    if (
      parsed.month.has(month) &&
      dayMatch &&
      parsed.hour.has(cursor.getHours()) &&
      parsed.minute.has(cursor.getMinutes())
    ) {
      return cursor.getTime()
    }
    cursor.setMinutes(cursor.getMinutes() + 1)
  }
  return null
}

function computeNext(spec: PluginScheduleSpec, from: number): { nextAt: number | null; oneShot: boolean; error?: string } {
  if (spec.cron) {
    const nextAt = nextCronTime(spec.cron, from)
    return nextAt ? { nextAt, oneShot: false } : { nextAt: null, oneShot: false, error: 'invalid cron expression' }
  }
  if (spec.every !== undefined) {
    const interval = parseEvery(spec.every)
    if (!interval) return { nextAt: null, oneShot: false, error: 'invalid every interval (min 1s)' }
    return { nextAt: from + interval, oneShot: false }
  }
  if (spec.at !== undefined) {
    const time = typeof spec.at === 'number' ? spec.at : Date.parse(String(spec.at))
    if (!Number.isFinite(time)) return { nextAt: null, oneShot: true, error: 'invalid at time' }
    return { nextAt: Math.max(time, from + 250), oneShot: true }
  }
  return { nextAt: null, oneShot: false, error: 'spec requires cron, every or at' }
}

export function startScheduler(fn: Dispatcher): void {
  dispatch = fn
  if (timer) return
  // One second granularity keeps short intervals and minute cron accurate.
  timer = setInterval(tick, 1000)
  tick()
}

export function registerSchedule(
  pluginId: string,
  spec: PluginScheduleSpec,
): { ok: boolean; nextAt?: number; error?: string } {
  if (!spec || !spec.id) return { ok: false, error: 'schedule id is required' }
  const id = String(spec.id)
  const existingCount = [...jobs.values()].filter(j => j.pluginId === pluginId).length
  if (!jobs.has(jobKey(pluginId, id)) && existingCount >= MAX_SCHEDULES_PER_PLUGIN) {
    return { ok: false, error: `too many schedules (max ${MAX_SCHEDULES_PER_PLUGIN})` }
  }
  const next = computeNext(spec, Date.now())
  if (!next.nextAt) return { ok: false, error: next.error || 'cannot compute next run' }
  jobs.set(jobKey(pluginId, id), {
    pluginId,
    spec: { ...spec, id },
    nextAt: next.nextAt,
    oneShot: next.oneShot,
  })
  writeLog(pluginId, 'system', `schedule registered: ${id} next=${new Date(next.nextAt).toISOString()}`)
  return { ok: true, nextAt: next.nextAt }
}

export function unregisterSchedule(pluginId: string, id?: string): number {
  let removed = 0
  for (const [key, job] of [...jobs]) {
    if (job.pluginId !== pluginId) continue
    if (id && job.spec.id !== id) continue
    jobs.delete(key)
    removed += 1
  }
  return removed
}

export function clearPluginSchedules(pluginId: string): void {
  for (const [key, job] of [...jobs]) {
    if (job.pluginId === pluginId) jobs.delete(key)
  }
}

export function listSchedules(pluginId: string): Array<{ id: string; nextAt: number | null; spec: PluginScheduleSpec }> {
  return [...jobs.values()]
    .filter(job => job.pluginId === pluginId)
    .map(job => ({ id: job.spec.id, nextAt: job.nextAt, spec: job.spec }))
}

function tick(): void {
  const now = Date.now()
  for (const [key, job] of [...jobs]) {
    if (!job.nextAt || job.nextAt > now) continue
    try {
      dispatch?.(job.pluginId, 'schedule', { id: job.spec.id })
    } catch (e) {
      writeLog(job.pluginId, 'warn', `schedule dispatch failed: ${(e as Error)?.message || e}`)
    }

    if (job.oneShot) {
      jobs.delete(key)
      continue
    }
    const next = computeNext(job.spec, now)
    if (!next.nextAt) {
      writeLog(job.pluginId, 'warn', `schedule disabled (invalid): ${job.spec.id}`)
      jobs.delete(key)
      continue
    }
    job.nextAt = next.nextAt
  }
}
