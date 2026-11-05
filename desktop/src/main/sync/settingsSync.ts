import axios from 'axios'
import { getConfig, setConfig } from '../config'

/** Settings small enough to keep consistent across every desktop device. */
const NAMESPACE = 'desktop'
const KEYS = ['shortcut', 'customShortcuts', 'disabledPlugins', 'desktopAgentApproval']

let timer: ReturnType<typeof setInterval> | null = null
let running = false

async function api(method: 'get' | 'put', path: string, body?: any) {
  const cfg = await getConfig()
  if (!cfg.token) return null
  const base = (cfg.serverUrl || 'https://mqgeek.com/ominaide').replace(/\/$/, '')
  const res = await axios({
    method,
    url: `${base}/api${path}`,
    headers: { Authorization: 'Bearer ' + cfg.token },
    data: body,
    timeout: 15000,
  })
  return res.data
}

export async function syncSettingsOnce(): Promise<Record<string, { from: any; to: any }>> {
  if (running) return {}
  running = true
  const changed: Record<string, { from: any; to: any }> = {}
  try {
    const data = await api('get', `/sync/settings/${NAMESPACE}`)
    if (!data) return changed
    const remote = new Map<string, any>((data.items || []).map((i: any) => [i.key, i]))

    const cfg = await getConfig()
    const meta: Record<string, string> = { ...(cfg.syncMeta || {}) }
    const lastValues: Record<string, any> = { ...(cfg.syncValues || {}) }
    const deviceId = cfg.hostDeviceId || 'desktop'

    for (const key of KEYS) {
      const localValue = cfg[key]
      const r = remote.get(key)
      const seenBefore = key in lastValues
      const localDirty = seenBefore &&
        JSON.stringify(localValue) !== JSON.stringify(lastValues[key])

      // First run on this device: adopt what the other devices already have.
      if (!seenBefore && r) {
        if (JSON.stringify(localValue) !== JSON.stringify(r.value)) {
          await setConfig(key, r.value)
          changed[key] = { from: localValue, to: r.value }
        }
        meta[key] = r.updated_at
        lastValues[key] = r.value
        continue
      }

      if (localDirty) {
        await api('put', `/sync/settings/${NAMESPACE}/${key}`, {
          value: localValue,
          device_id: deviceId,
        })
        meta[key] = new Date().toISOString()
        lastValues[key] = localValue
        continue
      }

      if (r && (!meta[key] || new Date(r.updated_at) > new Date(meta[key]))) {
        if (JSON.stringify(localValue) !== JSON.stringify(r.value)) {
          await setConfig(key, r.value)
          changed[key] = { from: localValue, to: r.value }
        }
        meta[key] = r.updated_at
        lastValues[key] = r.value
      } else if (!r && localValue !== undefined) {
        await api('put', `/sync/settings/${NAMESPACE}/${key}`, {
          value: localValue,
          device_id: deviceId,
        })
        meta[key] = new Date().toISOString()
        lastValues[key] = localValue
      }
    }

    await setConfig('syncMeta', meta)
    await setConfig('syncValues', lastValues)
    return changed
  } catch {
    return changed
  } finally {
    running = false
  }
}

export function startSettingsSync(
  onRemoteApplied?: (changed: Record<string, { from: any; to: any }>) => void | Promise<void>,
) {
  stopSettingsSync()
  const run = async () => {
    const changed = await syncSettingsOnce()
    if (Object.keys(changed).length && onRemoteApplied) {
      try { await onRemoteApplied(changed) } catch { /* ignore */ }
    }
  }
  setTimeout(run, 5000)
  timer = setInterval(run, 60_000)
}

export function stopSettingsSync() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}
