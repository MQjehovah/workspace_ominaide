import { spawn } from 'child_process'
import { promises as fsp, existsSync, statSync } from 'fs'
import type { Dirent, Stats } from 'fs'
import { homedir, hostname } from 'os'
import { basename, dirname, isAbsolute, join, relative, resolve } from 'path'
import { dialog } from 'electron'

import { getConfig, setConfig } from './config'
import { channelSend } from './backendChannel'
import { writeLog } from './logger'

const MAX_STDOUT = 30_000
const MAX_STDERR = 8_000
const DEFAULT_TIMEOUT = 600
const MAX_READ_BYTES = 2_000_000
const MAX_GREP_FILES = 2_000
const MAX_GREP_FILE_BYTES = 1_000_000
const SKIP_DIRS = new Set([
  'node_modules', '.git', '.ssh', '.gnupg', '.aws', '.config',
  'dist', 'build', 'dist-electron', 'out', 'target', '__pycache__',
  '.venv', 'venv', '.next', '.nuxt', 'coverage', '.idea', '.vscode',
])
const SENSITIVE_NAMES = new Set([
  '.env', 'id_rsa', 'id_ed25519', 'id_dsa', 'id_ecdsa',
])

type LocalArgs = Record<string, any>

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

function resolveLocalPath(value?: string): string {
  const raw = expandHome(String(value || '').trim() || '~')
  return resolve(isAbsolute(raw) ? raw : join(homedir(), raw))
}

function resolveCwd(value?: string): string {
  const cwd = resolveLocalPath(value || '~')
  const stat = statSync(cwd)
  if (!stat.isDirectory()) throw new Error(`执行目录不是文件夹：${cwd}`)
  return cwd
}

function isSensitiveName(name: string): boolean {
  const lower = name.toLowerCase()
  if (SENSITIVE_NAMES.has(lower)) return true
  if (lower.startsWith('.env.') && lower !== '.env.example') return true
  if (lower.endsWith('.pem') || lower.endsWith('.key') || lower.endsWith('.p12')) {
    return true
  }
  return false
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

async function runShell(args: LocalArgs): Promise<LocalShellResult> {
  const command = String(args.command || '').trim()
  if (!command) throw new Error('command 不能为空')

  const cwd = resolveCwd(args.cwd)
  const timeout = Math.min(
    Math.max(Number(args.timeout_seconds) || DEFAULT_TIMEOUT, 1),
    3600,
  )
  const spec = shellSpec(command)
  const started = Date.now()

  return await new Promise<LocalShellResult>((resolvePromise, reject) => {
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
      resolvePromise({
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

async function listDir(args: LocalArgs) {
  const path = resolveLocalPath(args.path)
  const stat = await fsp.stat(path)
  if (!stat.isDirectory()) throw new Error(`不是目录：${path}`)

  const includeHidden = Boolean(args.include_hidden)
  const entries = await fsp.readdir(path, { withFileTypes: true })
  const filtered = entries
    .filter((entry) => includeHidden || !entry.name.startsWith('.'))
    .sort((a, b) => {
      if (a.isDirectory() !== b.isDirectory()) return a.isDirectory() ? -1 : 1
      return a.name.localeCompare(b.name)
    })

  const out: Array<Record<string, unknown>> = []
  for (const entry of filtered.slice(0, 500)) {
    const full = join(path, entry.name)
    try {
      const info = await fsp.lstat(full)
      out.push({
        name: entry.name,
        path: full,
        type: entry.isDirectory() ? 'dir' : entry.isSymbolicLink() ? 'link' : 'file',
        size: info.size,
        mtime: info.mtime.toISOString(),
      })
    } catch {
      out.push({ name: entry.name, path: full, type: 'unknown' })
    }
  }
  return {
    path,
    entries: out,
    truncated: filtered.length > 500,
  }
}

async function readFile(args: LocalArgs) {
  const path = resolveLocalPath(args.path)
  const stat = await fsp.stat(path)
  if (stat.isDirectory()) throw new Error(`不是文件：${path}`)
  const maxBytes = Math.min(
    Math.max(Number(args.max_bytes) || 200_000, 1),
    MAX_READ_BYTES,
  )
  const handle = await fsp.open(path, 'r')
  try {
    const buffer = Buffer.alloc(Math.min(Math.max(stat.size, 1), maxBytes + 1))
    const { bytesRead } = await handle.read(buffer, 0, buffer.length, 0)
    const slice = buffer.subarray(0, Math.min(bytesRead, maxBytes))
    const binary = slice.includes(0)
    return {
      path,
      size: stat.size,
      binary,
      content: binary ? '' : slice.toString('utf8'),
      truncated: stat.size > maxBytes,
    }
  } finally {
    await handle.close()
  }
}

async function writeFile(args: LocalArgs) {
  const path = resolveLocalPath(args.path)
  const content = String(args.content ?? '')
  const exists = existsSync(path)
  if (exists) {
    const info = statSync(path)
    if (info.isDirectory()) throw new Error(`目标是目录：${path}`)
    if (!args.overwrite) {
      throw new Error('文件已存在；需要 overwrite=true 才能覆盖')
    }
  }
  if (args.create_dirs !== false) {
    await fsp.mkdir(dirname(path), { recursive: true })
  }
  await fsp.writeFile(path, content, 'utf8')
  return {
    path,
    bytes: Buffer.byteLength(content, 'utf8'),
    created: !exists,
  }
}

function globToRegExp(glob: string): RegExp {
  const escaped = glob
    .replace(/[.+^${}()|[\]\\]/g, '\\$&')
    .replace(/\*/g, '.*')
    .replace(/\?/g, '.')
  return new RegExp(`^${escaped}$`, 'i')
}

async function grep(args: LocalArgs) {
  const root = resolveLocalPath(args.path)
  const maxResults = Math.min(Math.max(Number(args.max_results) || 100, 1), 500)
  const flags = args.case_sensitive === false ? 'i' : ''
  const regex = new RegExp(String(args.pattern || ''), flags)
  const glob = String(args.glob || '').trim()
  const globRe = glob ? globToRegExp(glob) : null

  const rootStat = await fsp.stat(root)
  const files: string[] = []
  let truncated = false

  async function walk(dir: string, depth: number): Promise<void> {
    if (files.length >= MAX_GREP_FILES || depth > 12) {
      truncated = true
      return
    }
    let entries: Dirent[]
    try {
      entries = await fsp.readdir(dir, { withFileTypes: true })
    } catch {
      return
    }
    for (const entry of entries) {
      if (files.length >= MAX_GREP_FILES) {
        truncated = true
        return
      }
      if (SKIP_DIRS.has(entry.name) || isSensitiveName(entry.name)) continue
      const full = join(dir, entry.name)
      if (entry.isDirectory()) {
        await walk(full, depth + 1)
      } else if (entry.isFile()) {
        if (globRe && !globRe.test(entry.name)) continue
        files.push(full)
      }
    }
  }

  if (rootStat.isDirectory()) {
    await walk(root, 0)
  } else if (rootStat.isFile()) {
    files.push(root)
  } else {
    throw new Error(`不是文件或目录：${root}`)
  }

  const matches: Array<Record<string, unknown>> = []
  for (const file of files) {
    if (matches.length >= maxResults) {
      truncated = true
      break
    }
    let info: Stats
    try {
      info = await fsp.stat(file)
    } catch {
      continue
    }
    if (info.size > MAX_GREP_FILE_BYTES) continue
    let buffer: Buffer
    try {
      buffer = await fsp.readFile(file)
    } catch {
      continue
    }
    if (buffer.includes(0)) continue
    const lines = buffer.toString('utf8').split(/\r?\n/)
    for (let index = 0; index < lines.length; index += 1) {
      if (!regex.test(lines[index])) continue
      matches.push({
        path: relative(root, file) || basename(file),
        line: index + 1,
        text: lines[index].slice(0, 500),
      })
      if (matches.length >= maxResults) {
        truncated = true
        break
      }
    }
  }

  return { path: root, matches, truncated }
}

async function localPolicy(): Promise<string> {
  const cfg = await getConfig()
  const value = String(cfg.localToolPolicy || cfg.localShellPolicy || 'ask')
  return ['ask', 'always', 'never'].includes(value) ? value : 'ask'
}

async function setAlwaysAllow(): Promise<void> {
  await setConfig('localToolPolicy', 'always')
  // Keep the old key in sync for existing installations.
  await setConfig('localShellPolicy', 'always')
  writeLog('system', 'info', 'local tool policy set to always')
}

function approvalDetail(tool: string, args: LocalArgs): string {
  const lines = [`本地机器：${hostname()}`]
  if (tool === 'shell') {
    const cwd = args.cwd ? resolveLocalPath(String(args.cwd)) : homedir()
    const command = String(args.command || '')
    lines.push(`目录：${cwd}`, '', '命令：')
    lines.push(command.length > 4000 ? `${command.slice(0, 4000)}…` : command)
    return lines.join('\n')
  }

  const path = args.path ? resolveLocalPath(String(args.path)) : ''
  if (tool === 'list_dir') {
    lines.push(`操作：列出目录`, `目录：${path}`)
  } else if (tool === 'read_file') {
    lines.push(`操作：读取文件`, `文件：${path}`)
  } else if (tool === 'write_file') {
    const content = String(args.content ?? '')
    lines.push(
      `操作：${args.overwrite ? '覆盖文件' : '写入文件'}`,
      `文件：${path}`,
      `大小：${Buffer.byteLength(content, 'utf8')} 字节`,
      '',
      '内容预览：',
      content.length > 1500 ? `${content.slice(0, 1500)}…` : content,
    )
  } else if (tool === 'grep') {
    lines.push(
      `操作：搜索文本`,
      `目录：${path}`,
      `模式：${String(args.pattern || '')}`,
    )
    if (args.glob) lines.push(`文件：${String(args.glob)}`)
  } else {
    lines.push(`操作：${tool}`, `路径：${path}`)
  }
  if (isSensitiveName(basename(path))) {
    lines.push('', '⚠ 这是敏感文件路径，请确认后再允许。')
  }
  return lines.join('\n')
}

async function ensureApproved(tool: string, args: LocalArgs): Promise<void> {
  const policy = await localPolicy()
  if (policy === 'always') return
  if (policy === 'never') {
    throw new Error('本地工具已被设置为禁止（localToolPolicy=never）')
  }

  // Serialize approvals so several bot calls do not stack dialogs.
  let release: () => void = () => {}
  const previous = approvalChain
  approvalChain = new Promise<void>((resolveChain) => { release = resolveChain })
  try {
    await previous
    const { response } = await dialog.showMessageBox({
      type: 'warning',
      buttons: ['允许一次', '始终允许', '拒绝'],
      defaultId: 0,
      cancelId: 2,
      noLink: true,
      title: 'OmniAide 本地操作',
      message: 'Bot 请求在你的电脑上操作',
      detail: approvalDetail(tool, args),
    })
    if (response === 2) throw new Error('用户拒绝执行本地操作')
    if (response === 1) await setAlwaysAllow()
  } finally {
    release()
  }
}

async function runTool(tool: string, args: LocalArgs): Promise<unknown> {
  switch (tool) {
    case 'shell':
      return await runShell(args)
    case 'list_dir':
      return await listDir(args)
    case 'read_file':
      return await readFile(args)
    case 'write_file':
      return await writeFile(args)
    case 'grep':
      return await grep(args)
    default:
      throw new Error(`不支持的本地工具：${tool || '-'}`)
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
  const args: LocalArgs =
    msg?.args && typeof msg.args === 'object' ? msg.args : {}

  try {
    await ensureApproved(tool, args)
    const result = await runTool(tool, args)
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
