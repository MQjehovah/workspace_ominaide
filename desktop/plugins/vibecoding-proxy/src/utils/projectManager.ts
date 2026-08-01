import { existsSync, readdirSync, readFileSync, statSync, mkdirSync, writeFileSync } from 'fs'
import { join, resolve } from 'path'
import { execSync } from 'child_process'

export interface ProjectInfo {
  name: string
  path: string
  type: 'node' | 'python' | 'dotnet' | 'rust' | 'go' | 'other'
  lastModified: number
  description: string
  acpPort?: number
  addedAt?: number
}

let projects: ProjectInfo[] = []
let storagePath = ''

export function initStorage(basePath: string) {
  storagePath = join(basePath, 'vibecoding-proxy-projects.json')
  try {
    const data = readFileSync(storagePath, 'utf-8')
    projects = JSON.parse(data)
  } catch { projects = [] }
}

function save() {
  try {
    mkdirSync(resolve(storagePath, '..'), { recursive: true })
    writeFileSync(storagePath, JSON.stringify(projects, null, 2))
  } catch {}
}

export function getProjects(): ProjectInfo[] {
  return [...projects]
}

export function addProject(dir: string): ProjectInfo | null {
  const resolved = resolve(dir)
  if (projects.find(p => p.path === resolved)) return null
  const p = analyzeProject(resolved)
  if (!p) return null
  p.addedAt = Date.now()
  projects.push(p)
  save()
  return p
}

export function removeProject(path: string): boolean {
  const idx = projects.findIndex(p => p.path === path)
  if (idx === -1) return false
  projects.splice(idx, 1)
  save()
  return true
}

export function scanForProjects(rootDirs: string[]): ProjectInfo[] {
  const found: ProjectInfo[] = []
  const seen = new Set(projects.map(p => p.path))

  for (const dir of rootDirs) {
    if (!existsSync(dir)) continue
    try {
      scanDirForGit(dir, found, seen, 2)
    } catch {}
  }

  // Merge with existing (keep ACP port assignments)
  for (const f of found) {
    const existing = projects.find(p => p.path === f.path)
    if (existing) {
      f.acpPort = existing.acpPort
      f.addedAt = existing.addedAt
    }
  }

  const merged = [...found]
  // Add existing projects not found by scan
  for (const p of projects) {
    if (!merged.find(m => m.path === p.path)) {
      merged.push(p)
    }
  }

  projects = merged
  save()
  return projects
}

function scanDirForGit(dir: string, results: ProjectInfo[], seen: Set<string>, depth: number) {
  if (depth < 0) return
  try {
    const entries = readdirSync(dir)
    if (entries.includes('.git')) {
      if (!seen.has(dir)) {
        seen.add(dir)
        const p = analyzeProject(dir)
        if (p) results.push(p)
      }
      return // Don't recurse into git repos (they might have submodules)
    }
    for (const entry of entries) {
      if (entry.startsWith('.') || entry === 'node_modules') continue
      const full = join(dir, entry)
      if (statSync(full).isDirectory()) {
        scanDirForGit(full, results, seen, depth - 1)
      }
    }
  } catch {}
}

export function suggestScanDirs(): string[] {
  const dirs: string[] = []
  const home = process.env.USERPROFILE || process.env.HOME || ''
  const candidates = [
    home && join(home, 'workspace'),
    home && join(home, 'projects'),
    home && join(home, 'code'),
    home && join(home, 'dev'),
    home && join(home, 'src'),
    home && join(home, 'Desktop'),
    home && join(home, '文档'),
    'C:\\workspace', 'C:\\projects', 'C:\\code', 'C:\\dev', 'C:\\src',
    'D:\\workspace', 'D:\\projects', 'D:\\code', 'D:\\dev', 'D:\\src',
    'E:\\workspace', 'E:\\projects', 'E:\\code',
  ]
  for (const c of candidates) {
    if (c && existsSync(c)) dirs.push(c)
  }
  // Always include home directory as fallback
  if (home && !dirs.includes(home)) dirs.push(home)
  return [...new Set(dirs)]
}

export function analyzeProject(dir: string): ProjectInfo | null {
  try {
    const name = resolve(dir).split(/[/\\]/).pop() || 'unknown'
    let type: ProjectInfo['type'] = 'other'
    let description = ''

    if (existsSync(join(dir, 'package.json'))) {
      type = 'node'
      try {
        const pkg = JSON.parse(readFileSync(join(dir, 'package.json'), 'utf-8'))
        description = pkg.description || ''
      } catch {}
    } else if (existsSync(join(dir, 'pyproject.toml')) || existsSync(join(dir, 'requirements.txt'))) {
      type = 'python'
    } else if (existsSync(join(dir, 'Cargo.toml'))) { type = 'rust'
    } else if (existsSync(join(dir, 'go.mod'))) { type = 'go'
    }

    return { name, path: resolve(dir), type, lastModified: statSync(dir).mtimeMs, description }
  } catch { return null }
}

export function openInFileManager(dir: string) {
  const { exec } = require('child_process')
  exec(`explorer "${dir.replace(/\//g, '\\')}"`)
}

export function openInVSCode(dir: string) {
  const { exec } = require('child_process')
  exec(`code "${dir}"`)
}
