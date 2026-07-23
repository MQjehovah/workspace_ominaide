import { app } from 'electron'
import { mkdirSync, appendFileSync } from 'fs'
import { join } from 'path'

const LOG_DIR = join(app.getPath('userData'), 'logs')
mkdirSync(LOG_DIR, { recursive: true })

export function writeLog(pluginId: string, level: string, message: string) {
  const time = new Date().toISOString().replace('T', ' ').slice(0, 23)
  const line = `[${time}] [${pluginId}] [${level.toUpperCase()}] ${message}\n`
  try { appendFileSync(join(LOG_DIR, 'plugins.log'), line) } catch {}
}
