import { spawn } from 'child_process'
import { statSync } from 'fs'
import { homedir, hostname } from 'os'
import { join } from 'path'
import { dialog } from 'electron'

import { getConfig, setConfig } from './config'
import { channelSend } from './backendChannel'
import { writeLog } from './logger'

const MAX_STDOUT = 30_000
const MAX_STDERR = 8_000
const DEFAULT_TIMEOUT = 600

type LocalShellArgs = {
  command?: string
  cwd?: string
  timeout_seconds?: number
}

type LocalShellResult = {
  stdout: string
  stderr: string
  exit_code: number | null
  timed_out: boolean
  cwd: string
  duration_ms: number
}

let approvalChain: Promise<void> = Promise.resolve()

function expandHome(value: string): string {
  if (value === '~') return homedir()
  if (value.startsWith('~/') || value.startsWith('~\\')) {
    return join(homedir(), value.slice(2))
  }
  return value
}

function resolveCwd(value?: string): string {
  const cwd = expandHome((value || '~').trim() || '~')
  const stat = statSync(cwd)
  if (!stat.isDirectory()) throw new Error(`执行目录不是文件夹：${cwd}`)
  return cwd
}

function shellSpec(command: string): { file: string; args: string[] } {
  if (process.platform === 'win32') {
    return {
      file: process.env.ComSpec || 'cmd.exe',
      args: ['/d', '/s', '/c', command],
    }
  }
  return {
    file: process.env.SHELL || '/bin/sh',
    args: ['-lc', command],
  }
}

function killTree(child: ReturnType<typeof spawn>): void {
  try {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore' })
      return
    }
    if (child.pid) process.kill(-child.pid, 'SIGKILL')
  } catch {
    try {
      child.kill('SIGKILL')
    } catch {
      /* already gone */
    }
  }
}

async function runShell(args: LocalShellArgs): Promise<LocalShellResult> {
  const command = String(args.command || '').trim()
  if (!command) throw new Error('command 不能为空')

  const cwd = resolveCwd(args.cwd)
  const timeout = Math.min(
    Math.max(Number(args.timeout_seconds) || DEFAULT_TIMEOUT, 1),
    3600,
  )
  const spec = shellSpec(command)
  const started = Date.now()

  return await new Promise<LocalShellResult>((resolve, reject) => {
    const child = spawn(spec.file, spec.args, {
      cwd,
      env: process.env,
      detached: process.platform !== 'win32',
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    })

    let stdout = ''
    let stderr = ''
    let timedOut = false
    let finished = false

    const timer = setTimeout(() => {
      timedOut = true
      killTree(child)
    }, timeout * 1000)

    child.stdout?.on('data', (chunk: Buffer) => {
      if (stdout.length < MAX_STDOUT) stdout += chunk.toString('utf8')
    })
    child.stderr?.on('data', (chunk: Buffer) => {
      if (stderr.length < MAX_STDERR) stderr += chunk.toString('utf8')
    })
    child.on('error', (err) => {
      clearTimeout(timer)
      if (finished) return
      finished = true
      reject(err)
    })
    child.on('close', (code) => {
      clearTimeout(timer)
      if (finished) return
      finished = true
      resolve({
        stdout: stdout.slice(0, MAX_STDOUT).trim(),
        stderr: stderr.slice(0, MAX_STDERR).trim(),
        exit_code: code,
        timed_out: timedOut,
        cwd,
        duration_ms: Date.now() - started,
      })
    })
  })
}

async function ensureApproved(args: LocalShellArgs): Promise<void> {
  const cfg = await getConfig()
  const policy = String(cfg.localShellPolicy || 'ask')
  if (policy === 'always') return
  if (policy === 'never') throw new Error('本地命令已被设置为禁止（localShellPolicy=never）')

  const command = String(args.command || '').trim()
  const cwd = args.cwd ? expandHome(String(args.cwd)) : homedir()
  const detail = [
    `设备：${hostname()}`,
    `目录：${cwd}`,
    '',
    '命令：',
    command.length > 4000 ? `${command.slice(0, 4000)}…` : command,
  ].join('\n')

  // Serialize approvals so several bot calls do not stack dialogs.
  let release: () => void = () => {}
  const previous = approvalChain
  approvalChain = new Promise<void>((resolve) => { release = resolve })
  try {
    await previous
    const { response } = await dialog.showMessageBox({
      type: 'warning',
      buttons: ['允许一次', '始终允许', '拒绝'],
      defaultId: 0,
      cancelId: 2,
      noLink: true,
      title: 'OmniAide 本地命令',
      message: 'Bot 请求在你的电脑上执行命令',
      detail,
    })
    if (response === 2) throw new Error('用户拒绝执行本地命令')
    if (response === 1) {
      await setConfig('localShellPolicy', 'always')
      writeLog('system', 'info', 'local shell policy set to always')
    }
  } finally {
    release()
  }
}

/**
 * Handle one inbound `local-tools` call from the server.
 * Results are sent back on the same channel and correlated by call_id.
 */
export async function handleLocalToolMessage(msg: any): Promise<void> {
  const callId = String(msg?.call_id || '')
  if (!callId || msg?.type !== 'call') return

  const tool = String(msg?.tool || '')
  const args: LocalShellArgs =
    msg?.args && typeof msg.args === 'object' ? msg.args : {}

  try {
    if (tool !== 'shell') throw new Error(`不支持的本地工具：${tool || '-'}`)
    await ensureApproved(args)
    const result = await runShell(args)
    channelSend('local-tools', {
      type: 'result',
      call_id: callId,
      ok: true,
      result,
    })
  } catch (err: any) {
    const message = err?.message || String(err)
    writeLog('system', 'warn', `local ${tool} failed: ${message}`)
    channelSend('local-tools', {
      type: 'result',
      call_id: callId,
      ok: false,
      error: message,
    })
  }
}
