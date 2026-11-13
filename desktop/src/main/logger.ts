import { app } from 'electron'
import { mkdirSync, appendFileSync, closeSync, existsSync, openSync, readSync, statSync } from 'fs'
import { join } from 'path'

const LOG_DIR = app.isPackaged
  ? join(app.getPath('userData'), 'logs')
  : join(app.getAppPath(), 'logs')

mkdirSync(LOG_DIR, { recursive: true })

const LOG_FILE = join(LOG_DIR, 'plugins.log')
const MAX_BUFFER = 500

export interface LogEntry {
  time: number
  level: string
  message: string
}

// Keep a small in-memory ring buffer so the log viewer is instant even when
// the log file grows large.
const buffers = new Map<string, LogEntry[]>()

function pushBuffer(pluginId: string, entry: LogEntry) {
  let list = buffers.get(pluginId)
  if (!list) {
    list = []
    buffers.set(pluginId, list)
  }
  list.push(entry)
  if (list.length > MAX_BUFFER) list.splice(0, list.length - MAX_BUFFER)
}

export function writeLog(pluginId: string, level: string, message: string) {
  const time = Date.now()
  const stamp = new Date(time).toISOString().replace('T', ' ').slice(0, 23)
  const text = String(message ?? '')
  pushBuffer(pluginId, { time, level, message: text })
  // Keep each entry on one line so the viewer and grep stay readable.
  const singleLine = text.replace(/\r?\n/g, ' ⏎ ')
  try {
    appendFileSync(LOG_FILE, `[${stamp}] [${pluginId}] [${level.toUpperCase()}] ${singleLine}\n`)
  } catch {}
}

export function getLogDir(): string {
  return LOG_DIR
}

export function getLogFilePath(): string {
  return LOG_FILE
}

function readTail(file: string, maxBytes = 256 * 1024): string {
  if (!existsSync(file)) return ''
  try {
    const size = statSync(file).size
    const start = Math.max(0, size - maxBytes)
    const length = size - start
    if (length <= 0) return ''
    const fd = openSync(file, 'r')
    try {
      const buf = Buffer.alloc(length)
      readSync(fd, buf, 0, length, start)
      let text = buf.toString('utf8')
      // The first line may be cut in half.
      if (start > 0) {
        const nl = text.indexOf('\n')
        text = nl >= 0 ? text.slice(nl + 1) : ''
      }
      return text
    } finally {
      closeSync(fd)
    }
  } catch {
    return ''
  }
}

const LINE_RE = /^\[([^\]]+)\] \[([^\]]+)\] \[([A-Z]+)\] (.*)$/

/**
 * Return the most recent log entries for a plugin (or all plugins when
 * pluginId is empty). Reads from disk so entries from previous runs show up,
 * falling back to the in-memory buffer.
 */
export function getRecentLogs(pluginId: string, limit = 300): LogEntry[] {
  const cap = Math.max(1, Math.min(2000, limit))
  const fromFile: LogEntry[] = []

  for (const line of readTail(LOG_FILE).split('\n')) {
    if (!line.trim()) continue
    const m = LINE_RE.exec(line)
    if (!m) continue
    if (pluginId && m[2] !== pluginId) continue
    const parsed = Date.parse(m[1].replace(' ', 'T'))
    fromFile.push({
      time: Number.isFinite(parsed) ? parsed : Date.now(),
      level: m[3].toLowerCase(),
      message: m[4],
    })
  }

  if (fromFile.length > 0) return fromFile.slice(-cap)
  const buffered = buffers.get(pluginId) || []
  return buffered.slice(-cap)
}

export function clearLogs(pluginId: string) {
  buffers.delete(pluginId)
  // The file is shared by all plugins; clearing it would lose everyone's
  // history, so only the in-memory view is cleared here.
}
