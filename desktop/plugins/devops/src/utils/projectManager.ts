import { existsSync, readdirSync, readFileSync, statSync } from 'fs'
import { join, resolve } from 'path'

export interface ProjectInfo {
  name: string
  path: string
  type: 'node' | 'python' | 'dotnet' | 'rust' | 'go' | 'other'
  lastModified: number
  hasGit: boolean
  hasReadme: boolean
  description: string
}

export function scanProjects(rootDirs: string[]): ProjectInfo[] {
  const results: ProjectInfo[] = []
  const seen = new Set<string>()

  for (const dir of rootDirs) {
    if (!existsSync(dir)) continue
    try {
      const items = readdirSync(dir)
      for (const item of items) {
        const fullPath = join(dir, item)
        if (!statSync(fullPath).isDirectory()) continue
        if (item.startsWith('.') || item === 'node_modules') continue

        const project = analyzeProject(fullPath)
        if (project && !seen.has(fullPath)) {
          seen.add(fullPath)
          results.push(project)
        }
      }
    } catch {}
  }

  results.sort((a, b) => b.lastModified - a.lastModified)
  return results
}

export function analyzeProject(dir: string): ProjectInfo | null {
  try {
    const hasGit = existsSync(join(dir, '.git'))
    const hasReadme = existsSync(join(dir, 'README.md')) || existsSync(join(dir, 'readme.md'))

    let type: ProjectInfo['type'] = 'other'
    let description = ''

    if (existsSync(join(dir, 'package.json'))) {
      type = 'node'
      try {
        const pkg = JSON.parse(readFileSync(join(dir, 'package.json'), 'utf-8'))
        description = pkg.description || ''
      } catch {}
    } else if (existsSync(join(dir, 'requirements.txt')) || existsSync(join(dir, 'setup.py')) || existsSync(join(dir, 'pyproject.toml'))) {
      type = 'python'
    } else if (existsSync(join(dir, '*.sln')) || readdirSync(dir).some(f => f.endsWith('.csproj'))) {
      type = 'dotnet'
    } else if (existsSync(join(dir, 'Cargo.toml'))) {
      type = 'rust'
    } else if (existsSync(join(dir, 'go.mod'))) {
      type = 'go'
    }

    if (!hasGit && type === 'other') return null

    const name = resolve(dir).split(/[/\\]/).pop() || 'unknown'
    return { name, path: resolve(dir), type, lastModified: statSync(dir).mtimeMs, hasGit, hasReadme, description }

  } catch { return null }
}

export function findWorkspaceDirs(): string[] {
  const dirs: string[] = []
  const candidates = [
    process.env.USERPROFILE && join(process.env.USERPROFILE, 'workspace'),
    process.env.USERPROFILE && join(process.env.USERPROFILE, 'projects'),
    process.env.USERPROFILE && join(process.env.USERPROFILE, 'code'),
    process.env.HOME && join(process.env.HOME, 'workspace'),
    process.env.HOME && join(process.env.HOME, 'projects'),
    process.env.HOME && join(process.env.HOME, 'code'),
    'C:\\workspace', 'C:\\projects', 'C:\\code',
    'D:\\workspace', 'D:\\projects', 'D:\\code',
  ]
  for (const c of candidates) {
    if (c && existsSync(c)) dirs.push(c)
  }
  return [...new Set(dirs)]
}

export function openInFileManager(dir: string) {
  const { exec } = require('child_process')
  exec(`explorer "${dir.replace(/\//g, '\\')}"`)
}

export function openInVSCode(dir: string) {
  const { exec } = require('child_process')
  exec(`code "${dir}"`)
}
