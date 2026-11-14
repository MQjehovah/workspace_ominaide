import * as http from 'http'
import { execFile } from 'child_process'
import { basename } from 'path'
import type { PluginModule, PluginContext } from '../../../src/shared/types'

const EVERYTHING_PORT = 26983
const TIMEOUT = 3000

interface FileHit {
  name: string
  path: string
  extension: string
}

function withExtension(hit: Omit<FileHit, 'extension'>): FileHit {
  const name = hit.name || basename(hit.path)
  const extension = name.includes('.') ? name.split('.').pop() || '' : ''
  return { ...hit, name, extension }
}

// ---- Windows: Everything HTTP API -------------------------------------
function searchEverything(query: string, maxResults = 20): Promise<FileHit[]> {
  return new Promise((resolve) => {
    const url = `http://127.0.0.1:${EVERYTHING_PORT}/?search=${encodeURIComponent(query)}&json=1&path_column=1&count=${maxResults}`
    const req = http.get(url, { timeout: TIMEOUT }, (res) => {
      let data = ''
      res.on('data', (chunk: string) => { data += chunk })
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data)
          const results = parsed.results || []
          resolve(results.slice(0, maxResults).map((item: any) => {
            let fullPath = ''
            let name = ''
            if (Array.isArray(item)) {
              name = item[0] || ''
              const dir = item[1] || ''
              fullPath = dir && name ? `${dir}\\${name}` : name
            } else if (typeof item === 'object') {
              name = item.name || ''
              fullPath = item.path || name
            }
            return withExtension({ name, path: fullPath })
          }))
        } catch { resolve([]) }
      })
    })
    req.on('error', () => resolve([]))
    req.on('timeout', () => { req.destroy(); resolve([]) })
  })
}

// ---- macOS / Linux: Spotlight / locate / fd ---------------------------
function runCommand(command: string, args: string[], timeout = 3500): Promise<string> {
  return new Promise((resolve) => {
    execFile(command, args, { timeout, maxBuffer: 2 * 1024 * 1024 }, (err, stdout) => {
      resolve(err ? '' : String(stdout || ''))
    })
  })
}

async function searchMac(query: string, maxResults = 20): Promise<FileHit[]> {
  // This mdfind build does not support -limit; cap the output ourselves.
  const out = await runCommand('mdfind', ['-name', query])
  return out.split('\n')
    .map(line => line.trim())
    .filter(Boolean)
    .slice(0, maxResults)
    .map(path => withExtension({ name: basename(path), path }))
}

async function searchLinux(query: string, maxResults = 20): Promise<FileHit[]> {
  let out = await runCommand('fd', ['--max-results', String(maxResults), '--type', 'f', query])
  if (!out) {
    out = await runCommand('locate', ['-l', String(maxResults), query])
  }
  return out.split('\n')
    .map(line => line.trim())
    .filter(Boolean)
    .slice(0, maxResults)
    .map(path => withExtension({ name: basename(path), path }))
}

function searchLocal(query: string, maxResults = 20): Promise<FileHit[]> {
  if (process.platform === 'darwin') return searchMac(query, maxResults)
  if (process.platform === 'linux') return searchLinux(query, maxResults)
  return searchEverything(query, maxResults)
}

function platformLabel(): string {
  if (process.platform === 'darwin') return 'Spotlight 本地搜索'
  if (process.platform === 'linux') return '本地文件搜索'
  return 'Everything 文件搜索'
}

export default {
  async activate(context: PluginContext) {
    context.registerCommand('getPanelData', async () => ({
      title: '全局搜索',
      subtitle: platformLabel(),
      description: '直接输入关键词搜索电脑上的任何文件',
    }))

    context.registerCommand('open', async (args: any) => {
      if (args?.path && context.shell) {
        await context.shell.openPath(args.path)
      }
    })

    context.registerSearchProvider({
      keyword: '',
      name: '本地搜索',
      priority: 100,
      onSearch: async (query: string) => {
        if (!query) return []
        const files = await searchLocal(query)
        return files.map(file => ({
          type: 'file',
          title: file.name,
          subtitle: file.path,
          icon: 'file',
          action: 'open',
          actionArgs: { path: file.path },
          pluginId: 'everything',
        }))
      },
    })
  },
  deactivate() {},
} as PluginModule
