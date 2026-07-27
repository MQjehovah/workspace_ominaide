import { spawn, exec } from 'child_process'
import { resolve } from 'path'

export type AiTool = 'opencode' | 'claude'

export function launchTerminal(projectPath: string, tool: AiTool, prompt?: string) {
  const dir = resolve(projectPath)
  let cmd = tool === 'opencode' ? `opencode "${dir}"` : `claude "${dir}"`
  if (prompt) cmd += ` --prompt "${prompt.replace(/"/g, '\\"')}"`

  const isWindows = process.platform === 'win32'
  if (isWindows) {
    exec(`start cmd /k "${cmd}"`)
  } else {
    const term = process.env.TERM || 'xterm'
    exec(`${term} -e "${cmd}" &`)
  }
}

export function spawnAiProcess(tool: AiTool, projectPath: string, input: string): { stdout: string; stderr: string } | null {
  try {
    const dir = resolve(projectPath)
    const child = spawn(tool, [dir, '--prompt', input], {
      cwd: dir,
      stdio: ['pipe', 'pipe', 'pipe'],
      shell: true,
      timeout: 30000,
    })

    let stdout = ''
    let stderr = ''
    child.stdout?.on('data', (data: Buffer) => { stdout += data.toString() })
    child.stderr?.on('data', (data: Buffer) => { stderr += data.toString() })

    return new Promise((resolve) => {
      child.on('close', (code: number | null) => {
        resolve({ stdout, stderr, code })
      })
      child.on('error', () => resolve({ stdout, stderr, code: -1 }))
    }) as any
  } catch {
    return null
  }
}

export async function checkAiTools(): Promise<{ opencode: boolean; claude: boolean }> {
  const check = (name: string) => new Promise<boolean>(r => {
    exec(`where ${name} 2>nul || which ${name} 2>/dev/null`, (err) => r(!err))
  })
  return { opencode: await check('opencode'), claude: await check('claude') }
}
