import { spawn, ChildProcess } from 'child_process'
import { resolve } from 'path'

interface AcpInstance {
  proc: ChildProcess
  port: number
  projectPath: string
}

let instances: Map<string, AcpInstance> = new Map()
let nextPort = 8577

import { writeFileSync, appendFileSync } from 'fs'
import { join } from 'path'

const LOG_FILE = join(process.cwd(), 'acp-debug.log')
function log(msg: string) {
  try { appendFileSync(LOG_FILE, `${new Date().toISOString()} ${msg}\n`) } catch {}
}

export function startAcp(projectPath: string, tool: string = 'opencode'): { port: number; success: boolean; error?: string } {
  const dir = resolve(projectPath)
  const existing = Array.from(instances.values()).find(i => i.projectPath === dir)
  if (existing && !existing.proc.killed) return { port: existing.port, success: true }
  if (existing) instances.delete(dir)

  const port = nextPort++
  log(`startAcp: ${tool} serve --port ${port} cwd=${dir}`)
  try {
    spawnAcp(dir, tool, port)
    instances.set(dir, { proc: null as any, port, projectPath: dir })
    return { port, success: true }
  } catch (e: any) {
    log(`exception: ${e.message}`)
    return { port: 0, success: false, error: e.message }
  }
}

function spawnAcp(dir: string, tool: string, port: number, restartCount = 0) {
  const proc = spawn(tool, ['acp', '--port', String(port), '--hostname', '127.0.0.1'], {
    cwd: dir, stdio: ['ignore', 'pipe', 'pipe'], detached: false, shell: true,
  })

  let stderr = ''
  proc.stderr?.on('data', (d: Buffer) => { stderr += d.toString(); log(`[stderr] ${d}`) })
  proc.stdout?.on('data', (d: Buffer) => { log(`[stdout] ${d}`) })

  // Update the instance's proc reference
  const existing = Array.from(instances.values()).find(i => i.projectPath === dir)
  if (existing) existing.proc = proc

  proc.on('error', (err) => {
    log(`error: ${err.message}`)
  })

  proc.on('exit', (code, sig) => {
    log(`exit code=${code} signal=${sig} restartCount=${restartCount}\nstderr=${stderr}`)
    // Auto-restart up to 5 times
    if (restartCount < 5) {
      log(`restarting in 2s...`)
      setTimeout(() => spawnAcp(dir, tool, port, restartCount + 1), 2000)
    }
  })
}

async function checkAlive(port: number) {
  for (const path of ['/api/message', '/message', '/acp/message', '/api/chat', '/health', '/']) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}${path}`, { method: 'GET' })
      log(`health check ${path}: ${res.status}`)
    } catch (e: any) {
      log(`health check ${path}: ${e.message}`)
    }
  }
}

export function stopAcp(projectPath: string): boolean {
  const inst = Array.from(instances.values()).find(i => i.projectPath === resolve(projectPath))
  if (!inst) return false
  try { inst.proc.kill() } catch {}
  instances.delete(inst.projectPath)
  return true
}

export function getAcpPort(projectPath: string): number | null {
  const inst = Array.from(instances.values()).find(i => i.projectPath === resolve(projectPath))
  return inst ? inst.port : null
}

export function getAcpStatus(): Array<{ path: string; port: number; running: boolean }> {
  return Array.from(instances.values()).map(i => ({
    path: i.projectPath,
    port: i.port,
    running: !i.proc.killed,
  }))
}

const API_PATHS = ['/api/message', '/message', '/acp/message', '/chat', '/api/chat']

export async function sendAcpMessage(port: number, message: string): Promise<string | null> {
  for (const path of API_PATHS) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, prompt: message, input: message }),
      })
      if (!res.ok) continue
      const data: any = await res.json()
      return data.content || data.response || data.reply || data.text || JSON.stringify(data)
    } catch { continue }
  }
  return null
}

export function stopAllAcp() {
  for (const [_, inst] of instances) {
    try { inst.proc.kill() } catch {}
  }
  instances.clear()
}
