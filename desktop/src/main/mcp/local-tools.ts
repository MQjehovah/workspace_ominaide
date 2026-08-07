import { readFileSync, readdirSync, statSync, existsSync, writeFileSync, mkdirSync, rmSync } from 'fs'
import { join, resolve, basename } from 'path'
import { homedir, cpus, totalmem, freemem, hostname, platform, release } from 'os'
import { exec } from 'child_process'

export interface LocalToolDef {
  name: string
  description: string
  inputSchema: any
  handler: (args: any) => string | Promise<string>
}

const HOME = homedir()

function safePath(p: string): string {
  return p ? resolve(p) : HOME
}

function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`
}

const IGNORE = new Set(['node_modules', '.git', 'dist', 'dist-electron', 'release', '.frontend-build', '__pycache__', '.venv', 'venv'])

function listDir(path: string, maxItems = 200): string {
  const target = safePath(path)
  if (!existsSync(target)) return `目录不存在: ${target}`
  const st = statSync(target)
  if (!st.isDirectory()) return `不是目录: ${target}`
  const entries = readdirSync(target).filter(e => !e.startsWith('.') || e === '.')
  let items: string[] = []
  try {
    items = entries.map(e => {
      const p = join(target, e)
      let isDir = false
      let size = 0
      let mt = 0
      try { isDir = statSync(p).isDirectory(); size = statSync(p).size; mt = statSync(p).mtimeMs } catch { /* ignore */ }
      const prefix = isDir ? '📁' : '📄'
      const sizeStr = isDir ? '' : `  ${fmtSize(size)}`
      const timeStr = mt ? `  ${new Date(mt).toISOString().slice(0, 19).replace('T', ' ')}` : ''
      return `${prefix} ${e}${sizeStr}${timeStr}`
    }).sort((a, b) => {
      const ad = a.startsWith('📁') ? 0 : 1
      const bd = b.startsWith('📁') ? 0 : 1
      return ad - bd || a.localeCompare(b)
    })
  } catch { /* ignore */ }
  const dir = entries.filter(e => { try { return statSync(join(target, e)).isDirectory() } catch { return false } })
  const files = entries.filter(e => { try { return !statSync(join(target, e)).isDirectory() } catch { return false } })
  const total = dir.length + files.length
  let out = `目录 ${target} (${total} 项):\n`
  out += items.slice(0, maxItems).map(s => '  ' + s).join('\n')
  if (total > maxItems) out += `\n  …还有 ${total - maxItems} 项未显示`
  return out
}

function walkSearch(root: string, matcher: (rel: string, abs: string) => boolean, depth: number, maxDepth: number, maxResults: number, out: string[]): void {
  if (out.length >= maxResults || depth > maxDepth) return
  let entries: string[] = []
  try { entries = readdirSync(root) } catch { return }
  for (const e of entries) {
    if (out.length >= maxResults) return
    if (IGNORE.has(e)) continue
    const p = join(root, e)
    let isDir = false
    try { isDir = statSync(p).isDirectory() } catch { continue }
    if (isDir) {
      walkSearch(p, matcher, depth + 1, maxDepth, maxResults, out)
    } else if (matcher(e, p)) {
      out.push(p)
    }
  }
}

function findFiles(args: { path?: string; pattern?: string; name?: string; ext?: string; maxDepth?: number; maxResults?: number }): string {
  const root = safePath(args.path)
  if (!existsSync(root)) return `目录不存在: ${root}`
  const maxDepth = args.maxDepth ?? 5
  const maxResults = args.maxResults ?? 50
  const lower = (args.pattern || args.name || '').toLowerCase()
  const ext = args.ext ? (args.ext.startsWith('.') ? args.ext.toLowerCase() : '.' + args.ext.toLowerCase()) : ''
  const out: string[] = []
  const matcher = (name: string) => {
    const n = name.toLowerCase()
    if (ext && !n.endsWith(ext)) return false
    if (lower && !n.includes(lower)) return false
    return true
  }
  walkSearch(root, matcher, 0, maxDepth, maxResults, out)
  if (!out.length) return `在 ${root} 下没有匹配的文件`
  return `找到 ${out.length} 个文件:\n` + out.map(p => '  ' + p).join('\n') + (out.length >= maxResults ? `\n…已达上限 ${maxResults} 条` : '')
}

function readFile(args: { path: string; start?: number; limit?: number }): string {
  const target = safePath(args.path)
  if (!existsSync(target)) return `文件不存在: ${target}`
  const st = statSync(target)
  if (st.isDirectory()) return `这是目录,请用 list_dir 列出内容: ${target}`
  if (st.size > 5 * 1024 * 1024) return `文件过大 (${fmtSize(st.size)}),请用 start/limit 分段读取`
  let content = ''
  try {
    content = readFileSync(target, 'utf-8')
  } catch {
    return `读取失败(可能是二进制文件): ${target}`
  }
  const lines = content.split('\n')
  const start = Math.max(0, args.start ?? 0)
  const limit = args.limit ?? lines.length
  const slice = lines.slice(start, start + limit)
  const head = `文件 ${target} (${lines.length} 行, ${fmtSize(st.size)})\n`
  let body = slice.map((l, i) => `${String(start + i + 1).padStart(4)} | ${l}`).join('\n')
  if (start + limit < lines.length) body += `\n…共 ${lines.length} 行,已显示 ${start + 1}–${Math.min(start + limit, lines.length)}`
  return head + body
}

function writeFile(args: { path: string; content: string; append?: boolean }): string {
  if (!args.path || args.content === undefined) return '需要 path 和 content'
  const target = resolve(args.path)
  mkdirSync(join(target, '..'), { recursive: true })
  writeFileSync(target, args.content, { flag: args.append ? 'a' : 'w', encoding: 'utf-8' })
  return `已${args.append ? '追加' : '写入'} ${target} (${fmtSize(Buffer.byteLength(args.content))})`
}

function deletePath(args: { path: string; recursive?: boolean }): string {
  const target = resolve(args.path)
  if (!existsSync(target)) return `路径不存在: ${target}`
  const st = statSync(target)
  if (st.isDirectory() && !args.recursive) return `这是目录,如需删除请加 recursive: true`
  rmSync(target, { recursive: true, force: true })
  return `已删除 ${target}`
}

function fileInfo(args: { path: string }): string {
  const target = safePath(args.path)
  if (!existsSync(target)) return `路径不存在: ${target}`
  const st = statSync(target)
  return JSON.stringify({
    path: target,
    name: basename(target),
    type: st.isDirectory() ? 'directory' : 'file',
    size: st.size,
    sizeHuman: fmtSize(st.size),
    createdAt: new Date(st.birthtimeMs || st.ctimeMs).toISOString(),
    modifiedAt: new Date(st.mtimeMs).toISOString(),
  }, null, 2)
}

function runCommand(args: { command: string; cwd?: string; timeoutMs?: number }): Promise<string> {
  const cmd = args.command
  if (!cmd) return Promise.resolve('需要 command')
  const cwd = args.cwd ? resolve(args.cwd) : HOME
  const timeoutMs = args.timeoutMs ?? 60000
  return new Promise(resolve => {
    exec(cmd, {
      cwd,
      timeout: timeoutMs,
      maxBuffer: 10 * 1024 * 1024,
      windowsHide: true,
    }, (err, stdout, stderr) => {
      const out = (stdout || '').trim()
      const errOut = (stderr || '').trim()
      if (err) {
        const msg = `${err.message || String(err)}`.slice(0, 500)
        resolve(`命令执行失败(${errOut ? errOut.split('\n')[0] : msg}):\n${out}\n${errOut}`.trim())
        return
      }
      resolve(`${out}${out && errOut ? '\n' : ''}${errOut}`.trim() || '(命令执行成功,无输出)')
    })
  })
}

function systemInfo(_args: any): string {
  const mem = totalmem()
  const disk = (() => {
    try {
      const { execSync } = require('child_process')
      if (process.platform === 'win32') {
        const out = execSync('wmic logicaldisk get caption,freespace,size', { encoding: 'utf-8' })
        return out.trim().split('\n').slice(1).map(l => l.trim()).filter(Boolean).join('; ')
      }
      const out = execSync('df -h --output=target,size,used,avail 2>/dev/null || df -h', { encoding: 'utf-8' })
      return out.trim().split('\n').slice(1).slice(0, 4).join('; ')
    } catch {
      return 'N/A'
    }
  })()
  return JSON.stringify({
    hostname: hostname(),
    platform,
    release,
    arch: process.arch,
    node: process.version,
    cpus: cpus().length,
    cpuModel: cpus()[0]?.model?.trim(),
    memoryTotal: mem,
    memoryTotalHuman: fmtSize(mem),
    memoryFree: freemem(),
    memoryFreeHuman: fmtSize(freemem()),
    disk: disk.replace(/\s+/g, ' '),
    home: HOME,
    cwd: process.cwd(),
  }, null, 2)
}

export const localTools: LocalToolDef[] = [
  {
    name: 'read_file',
    description: '读取本地文本文件内容,支持按行范围分段读取',
    inputSchema: {
      type: 'object',
      properties: {
        path: { type: 'string', description: '文件绝对路径' },
        start: { type: 'number', description: '起始行号(从 0 开始),可选' },
        limit: { type: 'number', description: '读取行数,可选' },
      },
      required: ['path'],
    },
    handler: (args: any) => readFile(args || {}),
  },
  {
    name: 'list_dir',
    description: '列出本地目录内容,显示子目录与文件大小/修改时间',
    inputSchema: {
      type: 'object',
      properties: {
        path: { type: 'string', description: '目录绝对路径,缺省为用户主目录' },
        maxItems: { type: 'number', description: '最多显示条数,默认 200' },
      },
    },
    handler: (args: any) => listDir(args?.path, args?.maxItems || 200),
  },
  {
    name: 'find_files',
    description: '在本地目录中按文件名/扩展名搜索文件',
    inputSchema: {
      type: 'object',
      properties: {
        path: { type: 'string', description: '搜索根目录,缺省为用户主目录' },
        pattern: { type: 'string', description: '文件名关键词(大小写不敏感)' },
        ext: { type: 'string', description: '扩展名过滤,如 md 或 .md' },
        maxDepth: { type: 'number', description: '最大深度,默认 5' },
        maxResults: { type: 'number', description: '最多返回条数,默认 50' },
      },
    },
    handler: (args: any) => findFiles(args || {}),
  },
  {
    name: 'get_file_info',
    description: '获取本地文件或目录的元信息(大小/类型/时间)',
    inputSchema: {
      type: 'object',
      properties: {
        path: { type: 'string', description: '文件或目录绝对路径' },
      },
      required: ['path'],
    },
    handler: (args: any) => fileInfo(args || {}),
  },
  {
    name: 'write_file',
    description: '写入或追加本地文本文件(自动创建父目录)',
    inputSchema: {
      type: 'object',
      properties: {
        path: { type: 'string', description: '目标文件绝对路径' },
        content: { type: 'string', description: '要写入的内容' },
        append: { type: 'boolean', description: 'true 表示追加,默认覆盖' },
      },
      required: ['path', 'content'],
    },
    handler: (args: any) => writeFile(args || {}),
  },
  {
    name: 'delete_path',
    description: '删除本地文件或目录(目录需 recursive: true)',
    inputSchema: {
      type: 'object',
      properties: {
        path: { type: 'string', description: '要删除的路径' },
        recursive: { type: 'boolean', description: '删除目录时需为 true' },
      },
      required: ['path'],
    },
    handler: (args: any) => deletePath(args || {}),
  },
  {
    name: 'get_system_info',
    description: '获取本机系统信息(CPU/内存/磁盘/系统版本)',
    inputSchema: { type: 'object', properties: {} },
    handler: (args: any) => systemInfo(args || {}),
  },
  {
    name: 'run_command',
    description: '在本地终端执行 shell 命令并返回输出(Windows 使用 cmd,支持 cwd 与超时)',
    inputSchema: {
      type: 'object',
      properties: {
        command: { type: 'string', description: '要执行的命令,如 dir C:\\Users\\me 或 type file.txt' },
        cwd: { type: 'string', description: '工作目录,缺省为用户主目录' },
        timeoutMs: { type: 'number', description: '超时毫秒,默认 60000' },
      },
      required: ['command'],
    },
    handler: (args: any) => runCommand(args || {}),
  },
]

export function listLocalTools(): { name: string; description: string; inputSchema: any }[] {
  return localTools.map(t => ({ name: t.name, description: t.description, inputSchema: t.inputSchema }))
}

export async function callLocalTool(name: string, args: any): Promise<string> {
  const tool = localTools.find(t => t.name === name)
  if (!tool) return `未知本地工具: ${name}`
  try {
    return await tool.handler(args || {})
  } catch (e: any) {
    return `本地工具 ${name} 执行出错: ${e?.message || e}`
  }
}
