import { spawn, exec } from 'child_process'
import { resolve } from 'path'
import { existsSync } from 'fs'

export type AiTool = 'opencode' | 'claude' | 'codex'

export const AI_TOOL_LABELS: Record<AiTool, string> = {
  opencode: 'opencode',
  claude: 'Claude Code',
  codex: 'Codex CLI',
}

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

// ===== 持续会话执行（飞书 / 终端 tab 共用）=====

/** Resolve a working powershell.exe path (child process PATH may lack it). */
function powershellPath(): string {
  const candidates = [
    process.env.SystemRoot ? resolve(process.env.SystemRoot, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe') : '',
    resolve('C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'),
    resolve('C:/Windows/SysWOW64/WindowsPowerShell/v1.0/powershell.exe'),
    'powershell.exe',
  ]
  for (const c of candidates) {
    if (!c) continue
    try { if (existsSync(c)) return c } catch {}
  }
  return 'powershell.exe'
}

export interface SessionState {
  tool: AiTool
  projectPath: string
  firstRun: boolean
}

let state: SessionState | null = null

export function resetSession() { state = null }

export function currentSessionTool(): AiTool | null { return state ? state.tool : null }

/** Build the full shell command line for a tool. */
function buildToolCommand(tool: AiTool, input: string, continuation: boolean): string {
  const q = (s: string) => '"' + s.replace(/"/g, '""') + '"'
  switch (tool) {
    case 'opencode':
      return continuation ? `opencode run --dangerously-skip-permissions -c ${q(input)}` : `opencode run --dangerously-skip-permissions ${q(input)}`
    case 'claude':
      return continuation ? `claude -p --dangerously-skip-permissions --continue ${q(input)}` : `claude -p --dangerously-skip-permissions ${q(input)}`
    case 'codex':
      return continuation ? `codex exec -s danger-full-access --dangerously-bypass-approvals-and-sandbox resume --last ${q(input)}` : `codex exec -s danger-full-access --dangerously-bypass-approvals-and-sandbox ${q(input)}`
  }
}

export async function spawnAiProcess(tool: AiTool, projectPath: string, input: string): Promise<{ stdout: string; stderr: string; combined: string; code: number | null; error?: string } | null> {
  try {
    const dir = resolve(projectPath)
    const continuation = state !== null && state.tool === tool && state.projectPath === dir
    const cmdLine = buildToolCommand(tool, input, continuation)
    state = { tool, projectPath: dir, firstRun: !continuation }

    // Windows: run via PowerShell -EncodedCommand so multi-word + CJK prompts survive intact.
    const isWindows = process.platform === 'win32'
    const result = isWindows
      ? await runChild(powershellPath(), ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', Buffer.from(`Set-Location -LiteralPath ${JSON.stringify(dir)}; ${cmdLine}`, 'utf16le').toString('base64')], dir)
      : await runChild('/bin/sh', ['-c', cmdLine], dir)
    if (!result) return null
    // Clean noise (CLIXML, headers) and keep only the agent reply
    result.combined = cleanAgentOutput(result.combined, tool)
    return result
  } catch (e: any) {
    return Promise.resolve({ stdout: '', stderr: '', combined: '', code: -1, error: e.message || String(e) })
  }
}

/** Remove PowerShell CLIXML noise + agent header banners, keep only the reply. */
export function cleanAgentOutput(raw: string, tool: AiTool): string {
  let t = String(raw || '')
  // Strip PowerShell CLIXML progress objects entirely
  t = t.replace(/<Objs[\s\S]*?<\/Objs>/gi, '')
  t = t.replace(/#<\s*CLIXML[\s\S]*?>/gi, '')
  // Drop ANSI escape sequences
  t = t.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
  // Drop common agent noise lines
  t = t.split('\n').filter((l: string) => {
    const s = l.trim()
    if (!s) return true
    if (s.includes('Reading additional input from stdin')) return false
    if (s.startsWith('OpenAI Codex v')) return false
    if (/^--------$/.test(s) && t.split('--------').length > 2) return false
    if (/^\d+ \d+$/.test(s)) return false
    return true
  }).join('\n')

  // For codex, keep the tail after the final "codex" answer marker and strip "tokens used".
  if (tool === 'codex') {
    const tokensIdx = t.lastIndexOf('tokens used')
    if (tokensIdx > -1) t = t.slice(0, tokensIdx)
    const marker = 'codex\n'
    const lastMarker = t.lastIndexOf(marker)
    if (lastMarker > -1) {
      t = t.slice(lastMarker + marker.length).trim()
    } else {
      // fallback: keep last non-empty block
      const blocks = t.split('\n\n').map(b => b.trim()).filter(Boolean)
      if (blocks.length) t = blocks[blocks.length - 1]
    }
  } else {
    const lines = t.split('\n').map(l => l.trim()).filter(Boolean)
    if (lines.length) t = lines.join('\n')
  }

  return t.trim()
}

function runChild(command: string, args: string[], cwd: string): Promise<{ stdout: string; stderr: string; combined: string; code: number | null; error?: string }> {
  const child = spawn(command, args, {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    timeout: 600000,
  })
  let stdout = ''
  let stderr = ''
  child.stdout?.on('data', (data: Buffer) => { stdout += data.toString() })
  child.stderr?.on('data', (data: Buffer) => { stderr += data.toString() })
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      child.kill()
      resolve({ stdout, stderr, combined: stdout + stderr, code: null, error: 'timeout (600s)' })
    }, 600000)
    child.on('close', (code: number | null) => {
      clearTimeout(timer)
      resolve({ stdout, stderr, combined: stdout + stderr, code })
    })
    child.on('error', (err) => {
      clearTimeout(timer)
      resolve({ stdout, stderr, combined: stdout + stderr, code: -1, error: err.message })
    })
  })
}

export async function checkAiTools(): Promise<Record<AiTool, boolean>> {
  const check = (name: string) => new Promise<boolean>(r => {
    exec(`where ${name} 2>nul || which ${name} 2>/dev/null`, (err) => r(!err))
  })
  return { opencode: await check('opencode'), claude: await check('claude'), codex: await check('codex') }
}
