import { spawn } from 'child_process'
import {
  existsSync, statSync, readFileSync, writeFileSync, mkdirSync, readdirSync, openSync, readSync, closeSync,
} from 'fs'
import { resolve, relative, isAbsolute, dirname, join } from 'path'

export interface CodingToolCall {
  id: string
  type?: string
  function: { name: string; arguments: string }
}

export interface CodingStepResult {
  content?: string | null
  reasoning_content?: string | null
  tool_calls?: CodingToolCall[]
  finish_reason?: string | null
}

export type CodingStepFn = (messages: any[], tools: any[]) => Promise<CodingStepResult>
export type CodingEmitFn = (event: string, data: Record<string, unknown>) => void

interface ToolOptions {
  allowPush?: boolean
  allowCommit?: boolean
  identity?: { name?: string; email?: string }
}

const SKIP_DIRS = new Set([
  'node_modules', '.git', 'dist', 'build', 'dist-electron', 'out', 'target',
  '__pycache__', '.venv', 'venv', '.next', '.nuxt', 'coverage', '.idea', '.vscode',
])
const MAX_FILE_BYTES = 1024 * 1024
const MAX_READ_CHARS = 200_000
const MAX_TOOL_RESULT_CHARS = 20_000
const MAX_DIR_ENTRIES = 400
const MAX_COMMAND_OUTPUT = 30_000

const TOOLS = [
  {
    type: 'function',
    function: {
      name: 'list_dir',
      description: 'List files and directories under the project. Paths are relative to the project root.',
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'Relative directory path, default "."' },
          depth: { type: 'number', description: 'Recursion depth 1-4, default 2' },
        },
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'read_file',
      description: 'Read a UTF-8 text file. Use offset/limit for large files.',
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'Relative file path' },
          offset: { type: 'number', description: 'Start line offset, default 0' },
          limit: { type: 'number', description: 'Max lines, default 400' },
        },
        required: ['path'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'write_file',
      description: 'Create or overwrite a file with the given content. Parent directories are created automatically.',
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'Relative file path' },
          content: { type: 'string', description: 'Full file content' },
        },
        required: ['path', 'content'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'edit_file',
      description: 'Replace an exact string in a file. Use replace_all to change every occurrence.',
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'Relative file path' },
          old_string: { type: 'string', description: 'Exact text to replace' },
          new_string: { type: 'string', description: 'Replacement text' },
          replace_all: { type: 'boolean', description: 'Replace all occurrences, default false' },
        },
        required: ['path', 'old_string', 'new_string'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'search_text',
      description: 'Search text files in the project with a regular expression. Returns file path, line number and line text.',
      parameters: {
        type: 'object',
        properties: {
          pattern: { type: 'string', description: 'Regular expression' },
          path: { type: 'string', description: 'Relative directory to search, default "."' },
          include: { type: 'string', description: 'Optional file suffix filter, e.g. ".ts,.vue"' },
          max_results: { type: 'number', description: 'Max matches, default 50' },
        },
        required: ['pattern'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'run_command',
      description: 'Run a shell command in the project directory and return stdout/stderr/exit code. Use for builds, tests and git.',
      parameters: {
        type: 'object',
        properties: {
          command: { type: 'string', description: 'Command line to run' },
          cwd: { type: 'string', description: 'Relative working directory, default "."' },
          timeout_ms: { type: 'number', description: 'Timeout in ms, default 120000' },
        },
        required: ['command'],
      },
    },
  },
]

export const CODING_TOOLS = TOOLS

function safePath(root: string, p?: string): string {
  const target = resolve(root, p || '.')
  const rel = relative(root, target)
  if (rel.startsWith('..') || isAbsolute(rel)) {
    throw new Error(`path escapes project root: ${p}`)
  }
  return target
}

function relPath(root: string, abs: string): string {
  return relative(root, abs).split('\\').join('/') || '.'
}

function clamp(s: string, max: number): string {
  return s.length > max ? s.slice(0, max) + `\n...[truncated ${s.length - max} chars]` : s
}

function isProbablyBinary(abs: string): boolean {
  try {
    const fd = openSync(abs, 'r')
    const buf = Buffer.alloc(4096)
    const n = readSync(fd, buf, 0, 4096, 0)
    closeSync(fd)
    for (let i = 0; i < n; i++) if (buf[i] === 0) return true
    return false
  } catch {
    return true
  }
}

function walkFiles(root: string, start: string, onFile: (abs: string) => boolean): void {
  const stack = [start]
  while (stack.length) {
    const dir = stack.pop() as string
    let entries
    try {
      entries = readdirSync(dir, { withFileTypes: true })
    } catch {
      continue
    }
    for (const e of entries) {
      const abs = join(dir, e.name)
      if (e.isDirectory()) {
        if (!SKIP_DIRS.has(e.name)) stack.push(abs)
      } else if (e.isFile()) {
        if (onFile(abs) === false) return
      }
    }
  }
}

function describeTool(name: string, args: any): string {
  switch (name) {
    case 'run_command': return String(args.command || '').slice(0, 160)
    case 'read_file':
    case 'write_file':
    case 'edit_file': return String(args.path || '')
    case 'list_dir': return String(args.path || '.')
    case 'search_text': return `${args.pattern || ''} in ${args.path || '.'}`
    default: return JSON.stringify(args).slice(0, 160)
  }
}

function resolvePowershell(): string {
  const root = process.env.SystemRoot
  if (root) {
    const p = resolve(root, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
    try { if (existsSync(p)) return p } catch { }
  }
  return 'powershell.exe'
}

async function runCommand(root: string, args: any, opts: ToolOptions = {}): Promise<any> {
  const cwd = safePath(root, args.cwd || '.')
  if (!existsSync(cwd) || !statSync(cwd).isDirectory()) {
    return { error: `working directory not found: ${args.cwd || '.'}` }
  }
  const timeout = Math.min(Math.max(Number(args.timeout_ms) || 120000, 1000), 600000)
  const isWindows = process.platform === 'win32'
  const command = String(args.command || '')
  if (!command.trim()) return { error: 'command is required' }

  const isGitPush = /(^|[;&|]\s*)git\s+push\b/.test(command)
  const isGitCommit = /(^|[;&|]\s*)git\s+commit\b/.test(command)
  if (isGitPush && !opts.allowPush) {
    return { error: 'git push is not allowed by the developer profile' }
  }
  if (isGitCommit && !opts.allowCommit) {
    return { error: 'git commit is not allowed by the developer profile' }
  }
  if (isGitPush && /--force(?!-with-lease)\b|(^|\s)-f\b/.test(command)) {
    return { error: 'force push is blocked' }
  }

  const env = { ...process.env }
  if (opts.identity?.name) {
    env.GIT_AUTHOR_NAME = opts.identity.name
    env.GIT_COMMITTER_NAME = opts.identity.name
  }
  if (opts.identity?.email) {
    env.GIT_AUTHOR_EMAIL = opts.identity.email
    env.GIT_COMMITTER_EMAIL = opts.identity.email
  }

  const shellCmd = isWindows ? resolvePowershell() : '/bin/sh'
  const shellArgs = isWindows
    ? ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', Buffer.from(command, 'utf16le').toString('base64')]
    : ['-c', command]

  return await new Promise((resolvePromise) => {
    const child = spawn(shellCmd, shellArgs, { cwd, env, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true })
    let stdout = ''
    let stderr = ''
    let timedOut = false
    const timer = setTimeout(() => {
      timedOut = true
      try {
        if (isWindows && child.pid) spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true })
        else child.kill('SIGTERM')
      } catch { }
    }, timeout)

    child.stdout?.on('data', (d: Buffer) => {
      if (stdout.length < MAX_COMMAND_OUTPUT) stdout += d.toString()
    })
    child.stderr?.on('data', (d: Buffer) => {
      if (stderr.length < MAX_COMMAND_OUTPUT) stderr += d.toString()
    })
    child.on('error', (e) => {
      clearTimeout(timer)
      resolvePromise({ error: e.message, stdout, stderr })
    })
    child.on('close', (code) => {
      clearTimeout(timer)
      resolvePromise({
        code,
        timed_out: timedOut,
        stdout: clamp(stdout, MAX_COMMAND_OUTPUT),
        stderr: clamp(stderr, MAX_COMMAND_OUTPUT),
      })
    })
  })
}

export async function executeTool(root: string, name: string, args: any, opts: ToolOptions = {}): Promise<any> {
  args = args || {}
  switch (name) {
    case 'list_dir': {
      const base = safePath(root, args.path || '.')
      if (!existsSync(base) || !statSync(base).isDirectory()) return { error: `not a directory: ${args.path || '.'}` }
      const depth = Math.min(Math.max(Number(args.depth) || 2, 1), 4)
      const out: string[] = []
      const walk = (dir: string, level: number) => {
        if (out.length >= MAX_DIR_ENTRIES) return
        let entries
        try { entries = readdirSync(dir, { withFileTypes: true }) } catch { return }
        for (const e of entries) {
          if (out.length >= MAX_DIR_ENTRIES) break
          const abs = join(dir, e.name)
          if (e.isDirectory()) {
            if (SKIP_DIRS.has(e.name)) continue
            out.push(relPath(root, abs) + '/')
            if (level < depth) walk(abs, level + 1)
          } else if (e.isFile()) {
            out.push(relPath(root, abs))
          }
        }
      }
      walk(base, 1)
      return { root, path: relPath(root, base), entries: out, truncated: out.length >= MAX_DIR_ENTRIES }
    }

    case 'read_file': {
      const abs = safePath(root, args.path)
      if (!existsSync(abs) || !statSync(abs).isFile()) return { error: `not a file: ${args.path}` }
      if (statSync(abs).size > MAX_FILE_BYTES) return { error: `file too large (>${MAX_FILE_BYTES} bytes): ${args.path}` }
      if (isProbablyBinary(abs)) return { error: `binary file is not readable as text: ${args.path}` }
      const text = readFileSync(abs, 'utf8')
      const lines = text.split(/\r?\n/)
      const offset = Math.max(Number(args.offset) || 0, 0)
      const limit = Math.min(Math.max(Number(args.limit) || 400, 1), 2000)
      let content = lines.slice(offset, offset + limit).join('\n')
      let truncated = offset + limit < lines.length
      if (content.length > MAX_READ_CHARS) {
        content = content.slice(0, MAX_READ_CHARS)
        truncated = true
      }
      return { path: args.path, offset, total_lines: lines.length, content, truncated }
    }

    case 'write_file': {
      const abs = safePath(root, args.path)
      mkdirSync(dirname(abs), { recursive: true })
      const content = String(args.content ?? '')
      writeFileSync(abs, content, 'utf8')
      return { path: args.path, bytes: Buffer.byteLength(content, 'utf8') }
    }

    case 'edit_file': {
      const abs = safePath(root, args.path)
      if (!existsSync(abs) || !statSync(abs).isFile()) return { error: `not a file: ${args.path}` }
      const oldText = String(args.old_string ?? '')
      if (!oldText) return { error: 'old_string is required' }
      const text = readFileSync(abs, 'utf8')
      const count = text.split(oldText).length - 1
      if (count === 0) return { error: 'old_string not found', path: args.path }
      if (count > 1 && !args.replace_all) {
        return { error: `old_string matched ${count} times; provide more context or set replace_all=true`, path: args.path }
      }
      const next = args.replace_all
        ? text.split(oldText).join(String(args.new_string ?? ''))
        : text.replace(oldText, String(args.new_string ?? ''))
      writeFileSync(abs, next, 'utf8')
      return { path: args.path, replaced: count, bytes: Buffer.byteLength(next, 'utf8') }
    }

    case 'search_text': {
      const base = safePath(root, args.path || '.')
      const pattern = String(args.pattern || '')
      if (!pattern) return { error: 'pattern is required' }
      let re: RegExp
      try { re = new RegExp(pattern, 'i') } catch (e: any) { return { error: `invalid regex: ${e.message}` } }
      const max = Math.min(Math.max(Number(args.max_results) || 50, 1), 200)
      const include = String(args.include || '').split(',').map((s) => s.trim()).filter(Boolean)
      const matches: Array<{ path: string; line: number; text: string }> = []
      walkFiles(root, base, (abs) => {
        if (matches.length >= max) return false
        if (include.length && !include.some((suf) => abs.toLowerCase().endsWith(suf.toLowerCase()))) return true
        try {
          if (statSync(abs).size > MAX_FILE_BYTES || isProbablyBinary(abs)) return true
        } catch { return true }
        const lines = readFileSync(abs, 'utf8').split(/\r?\n/)
        for (let i = 0; i < lines.length; i++) {
          if (re.test(lines[i])) {
            matches.push({ path: relPath(root, abs), line: i + 1, text: lines[i].trim().slice(0, 240) })
            if (matches.length >= max) break
          }
        }
        return true
      })
      return { matches, truncated: matches.length >= max }
    }

    case 'run_command':
      return await runCommand(root, args, opts)

    default:
      return { error: `unknown tool: ${name}` }
  }
}

function systemPrompt(dir: string, developer?: any): string {
  const platform = process.platform === 'win32' ? 'Windows' : process.platform
  const lines = [
    '你是 OmniAide 内置的编程 Agent，运行在用户自己的电脑上，当前为全自动模式。',
    `项目根目录：${dir}`,
    `操作系统：${platform}`,
    '',
    '工作方式：',
    '1. 先理解项目结构与相关代码，再动手修改；优先读取现有实现而不是猜测。',
    '2. 使用工具真正完成工作，不要只输出计划或伪代码。',
    '3. 所有路径都使用相对项目根目录的路径；不要访问项目根目录以外的位置。',
    '4. 修改后尽量运行构建、测试或最小验证命令确认没有破坏。',
    '5. 不要执行格式化磁盘、关机、删除项目根目录等破坏性命令。',
    '6. 完成后用中文简要说明改了什么、验证结果，以及仍需用户注意的事项。',
    '',
    '可用工具：list_dir / read_file / write_file / edit_file / search_text / run_command。',
  ]

  if (developer) {
    const perms: string[] = Array.isArray(developer.permissions) ? developer.permissions : []
    lines.push('', '【开发者档案】')
    if (developer.github_username) lines.push(`GitHub 用户名：${developer.github_username}`)
    if (developer.github_email) lines.push(`Git 提交邮箱：${developer.github_email}`)
    if (developer.default_org) lines.push(`默认组织：${developer.default_org}`)
    if (developer.default_branch) lines.push(`默认分支：${developer.default_branch}`)
    if (developer.workspace_roots?.length) lines.push(`工作区根目录：${developer.workspace_roots.join(', ')}`)
    if (developer.commit_style) lines.push(`提交信息规范：${developer.commit_style}`)
    lines.push(`允许的代码操作：${perms.length ? perms.join(', ') : '仅读取与修改'}`)
    if (perms.includes('push')) {
      lines.push('推送使用 SSH（~/.ssh/id_rsa）。若 remote 是 https://github.com/...，改用 git@github.com:<owner>/<repo>.git 推送；禁止 force push。除非用户明确要求，优先新建分支推送，不要直接推 main/master。')
    } else {
      lines.push('不要执行 git commit 或 git push。')
    }
    if (developer.notes) lines.push(`补充说明：${developer.notes}`)
  } else {
    lines.push('', '未配置开发者档案：只允许读取和修改文件，不要执行 git commit 或 git push。')
  }

  return lines.join('\n')
}

function messageChars(m: any): number {
  return typeof m.content === 'string' ? m.content.length : 0
}

function trimMessages(messages: any[], maxChars = 300_000): void {
  let total = messages.reduce((n, m) => n + messageChars(m), 0)
  while (total > maxChars && messages.length > 8) {
    const m = messages[2]
    if (!m) break
    const removed = new Set<any>([m])
    if (m.role === 'assistant' && Array.isArray(m.tool_calls)) {
      const ids = new Set(m.tool_calls.map((tc: any) => tc.id))
      let j = 3
      while (j < messages.length && messages[j].role === 'tool' && ids.has(messages[j].tool_call_id)) {
        removed.add(messages[j])
        j++
      }
    }
    for (let k = messages.length - 1; k >= 2; k--) {
      if (removed.has(messages[k])) {
        total -= messageChars(messages[k])
        messages.splice(k, 1)
      }
    }
  }
}

export async function runCodingAgent(opts: {
  taskId: string
  dir: string
  input: string
  source: string
  step: CodingStepFn
  emit: CodingEmitFn
  maxTurns?: number
  shouldStop?: () => boolean
  history?: any[]
  onMessages?: (messages: any[]) => void
  developer?: any
}): Promise<{ code: number; output: string; error?: string; duration_ms: number; cancelled?: boolean }> {
  const t0 = Date.now()
  const emit = opts.emit
  const perms: string[] = Array.isArray(opts.developer?.permissions) ? opts.developer.permissions : []
  const toolOptions: ToolOptions = {
    allowPush: perms.includes('push'),
    allowCommit: perms.includes('commit'),
    identity: {
      name: opts.developer?.github_username || undefined,
      email: opts.developer?.github_email || undefined,
    },
  }
  const projectName = opts.dir.split(/[\\/]/).filter(Boolean).pop() || opts.dir
  emit('started', {
    tool: 'omniaide',
    project: opts.dir,
    project_name: projectName,
    input: opts.input.slice(0, 500),
    source: opts.source,
  })
  emit('milestone', { stage: 'executing' })

  let messages: any[]
  if (opts.history && opts.history.length) {
    messages = [...opts.history]
    if (messages[0]?.role === 'system') messages[0] = { role: 'system', content: systemPrompt(opts.dir, opts.developer) }
    else messages.unshift({ role: 'system', content: systemPrompt(opts.dir, opts.developer) })
    messages.push({ role: 'user', content: opts.input })
  } else {
    messages = [
      { role: 'system', content: systemPrompt(opts.dir, opts.developer) },
      { role: 'user', content: opts.input },
    ]
  }
  let final = ''
  let lastText = ''
  const maxTurns = Math.min(Math.max(opts.maxTurns || 40, 1), 80)

  try {
    for (let turn = 0; turn < maxTurns; turn++) {
      if (opts.shouldStop?.()) {
        emit('milestone', { stage: 'cancelled' })
        opts.onMessages?.(messages)
        return { code: 0, output: lastText, duration_ms: Date.now() - t0, cancelled: true }
      }
      const res = await opts.step(messages, TOOLS)
      const content = (res.content || '').trim()
      if (content) {
        lastText = content
        emit('output', { chunk: content + '\n' })
      }
      const calls = res.tool_calls || []
      if (!calls.length) {
        final = content
        break
      }

      const assistant: any = { role: 'assistant', content: res.content || null }
      if (res.reasoning_content) assistant.reasoning_content = res.reasoning_content
      assistant.tool_calls = calls.map((tc) => ({
        id: tc.id,
        type: 'function',
        function: { name: tc.function?.name || '', arguments: tc.function?.arguments || '{}' },
      }))
      messages.push(assistant)

      for (const tc of calls) {
        const name = tc.function?.name || ''
        let args: any = {}
        try { args = JSON.parse(tc.function?.arguments || '{}') } catch { args = {} }
        emit('tool', { name, detail: describeTool(name, args) })

        let result: any
        try {
          result = await executeTool(opts.dir, name, args, toolOptions)
          if ((name === 'write_file' || name === 'edit_file') && !result?.error) {
            emit('file', { path: String(args.path || ''), action: 'modified' })
          }
        } catch (e: any) {
          result = { error: e?.message || String(e) }
        }
        const text = clamp(JSON.stringify(result), MAX_TOOL_RESULT_CHARS)
        messages.push({ role: 'tool', tool_call_id: tc.id, content: text })
      }
      trimMessages(messages)
      opts.onMessages?.(messages)
    }

    const duration = Date.now() - t0
    if (!final) final = lastText || '已达到最大步数，未生成最终总结。'
    opts.onMessages?.(messages)
    emit('done', { code: 0, duration_ms: duration, output: clamp(final, MAX_TOOL_RESULT_CHARS) })
    return { code: 0, output: final, duration_ms: duration }
  } catch (e: any) {
    const duration = Date.now() - t0
    const error = e?.message || String(e)
    opts.onMessages?.(messages)
    emit('failed', { error, duration_ms: duration, code: -1 })
    return { code: -1, output: '', error, duration_ms: duration }
  }
}
