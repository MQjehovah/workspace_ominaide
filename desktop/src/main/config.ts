import { app } from 'electron'
import { join } from 'path'
import { Low } from 'lowdb'
import { JSONFile } from 'lowdb/node'
import { existsSync, mkdirSync } from 'fs'

const configDir = join(app.getPath('userData'), 'omniaide-config')
if (!existsSync(configDir)) mkdirSync(configDir, { recursive: true })

const file = join(configDir, 'config.json')
const adapter = new JSONFile<Record<string, any>>(file)
const db = new Low(adapter, {})

let loaded = false

async function ensure() {
  if (!loaded) { await db.read(); loaded = true }
}

export function getConfig(): Record<string, any> {
  ensure()
  return db.data as Record<string, any>
}

export async function setConfig(key: string, value: any) {
  await ensure()
  const keys = key.split('.')
  let obj = db.data as any
  for (let i = 0; i < keys.length - 1; i++) {
    if (!obj[keys[i]]) obj[keys[i]] = {}
    obj = obj[keys[i]]
  }
  obj[keys[keys.length - 1]] = value
  await db.write()
}
