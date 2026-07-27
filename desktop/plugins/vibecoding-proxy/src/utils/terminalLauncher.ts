import { spawn, exec } from 'child_process'
import { resolve } from 'path'

export type AiTool = 'opencode' | 'claude'

interface AiSession {
  id: string
  tool: AiTool
  projectPath: string
}

let currentSession: AiSession | null = null
let signalFn: ((method: string, ...args: any[]) => Promise<any>) | null = null

export function setSignalFn(fn: (method: string, ...args: any[]) => Promise<any>) {
  signalFn = fn
}

async function call(method: string, ...args: any[]) {
  if (!signalFn) throw new Error('signal not available')
  return signalFn(method, ...args)
}

export async function startSession(tool: AiTool, projectPath: string): Promise<{ success: boolean; error?: string }> {
  await endSession()
  const dir = resolve(projectPath)
  try {
    const result = await call('pty:create', tool, [], dir)
    if (result.error) return { success: false, error: result.error }
    currentSession = { id: result.id, tool, projectPath }
    return { success: true }
  } catch (e: any) {
    return { success: false, error: e.message || String(e) }
  }
}

export async function sendInput(input: string): Promise<{ output: string; done: boolean }> {
  if (!currentSession) return { output: '', done: true }
  try {
    await call('pty:write', currentSession.id, input + '\n')
    return { output: '', done: false }
  } catch {
    return { output: '', done: true }
  }
}

export async function pollOutput(): Promise<{ output: string; done: boolean }> {
  if (!currentSession) return { output: '', done: true }
  try {
    return await call('pty:read', currentSession.id)
  } catch {
    return { output: '', done: true }
  }
}

export async function endSession(): Promise<void> {
  if (currentSession) {
    try { await call('pty:kill', currentSession.id) } catch {}
    currentSession = null
  }
}

export async function isSessionActive(): Promise<boolean> {
  return currentSession !== null
}

export function launchTerminal(projectPath: string, tool: AiTool, prompt?: string) {
  const dir = resolve(projectPath)
  const isWindows = process.platform === 'win32'

  if (isWindows) {
    const toolCmd = `${tool} "${dir}"${prompt ? ` --prompt "${prompt.replace(/"/g, '\\"')}"` : ''}`
    spawn('cmd.exe', ['/c', 'start', '', 'cmd', '/k', `cd /d "${dir}" && ${toolCmd}`], {
      detached: true, stdio: 'ignore', shell: false, windowsHide: false,
    }).unref()
  } else {
    const term = process.env.TERM || 'xterm'
    const toolCmd = `${tool} "${dir}"${prompt ? ` --prompt '${prompt.replace(/'/g, "'\\''")}'` : ''}`
    spawn(term, ['-e', `cd "${dir}" && ${toolCmd}`], {
      detached: true, stdio: 'ignore',
    }).unref()
  }
}

let sessionStarted = false

export function resetSession() { sessionStarted = false }

export function spawnAiProcess(tool: AiTool, projectPath: string, input: string): Promise<{ stdout: string; stderr: string; combined: string; code: number | null; error?: string } | null> {
  try {
    const dir = resolve(projectPath)
    const args = sessionStarted
      ? ['run', '-c', input]
      : ['run', input]
    const child = spawn(tool, args, {
      cwd: dir,
      stdio: ['pipe', 'pipe', 'pipe'],
      shell: true,
      timeout: 180000,
    })
    sessionStarted = true
    let stdout = ''
    let stderr = ''
    child.stdout?.on('data', (data: Buffer) => { stdout += data.toString() })
    child.stderr?.on('data', (data: Buffer) => { stderr += data.toString() })
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        child.kill()
        resolve({ stdout, stderr, combined: stdout + stderr, code: null, error: 'timeout (180s)' })
      }, 180000)
      child.on('close', (code: number | null) => {
        clearTimeout(timer)
        resolve({ stdout, stderr, combined: stdout + stderr, code })
      })
      child.on('error', (err) => {
        clearTimeout(timer)
        resolve({ stdout, stderr, combined: stdout + stderr, code: -1, error: err.message })
      })
    })
  } catch (e: any) {
    return Promise.resolve({ stdout: '', stderr: '', combined: '', code: -1, error: e.message || String(e) })
  }
}

export async function checkAiTools(): Promise<{ opencode: boolean; claude: boolean }> {
  const check = (name: string) => new Promise<boolean>(r => {
    exec(`where ${name} 2>nul || which ${name} 2>/dev/null`, (err) => r(!err))
  })
  return { opencode: await check('opencode'), claude: await check('claude') }
}
