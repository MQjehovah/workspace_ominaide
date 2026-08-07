import { app, dialog } from 'electron'
import { existsSync, readFileSync, writeFileSync, mkdirSync, rmSync, readdirSync, cpSync, statSync, createWriteStream } from 'fs'
import { join, basename } from 'path'
import axios from 'axios'

export interface SkillInfo {
  id: string
  name: string
  description: string
  enabled: boolean
  instructions: string
  updatedAt: number
}

const dir = () => join(app.getPath('userData'), 'skills')

function parseSkill(folderId: string): SkillInfo | null {
  const file = join(dir(), folderId, 'SKILL.md')
  if (!existsSync(file)) return null
  try {
    const raw = readFileSync(file, 'utf-8').replace(/^\uFEFF/, '')
    let name = folderId
    let description = ''
    let enabled = true
    let instructions = raw
    const m = raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/)
    if (m) {
      const front = m[1]
      instructions = m[2] || ''
      const get = (k: string) => front.match(new RegExp(`^\\s*${k}\\s*:\\s*(.+)$`, 'm'))?.[1]?.trim()
      name = get('name') || folderId
      description = get('description') || ''
      enabled = (get('enabled') || 'true') !== 'false'
    }
    let updatedAt = 0
    try { updatedAt = statSync(file).mtimeMs } catch { /* ignore */ }
    return { id: folderId, name, description, enabled, instructions: instructions.trim(), updatedAt }
  } catch {
    return null
  }
}

function slugify(s: string): string {
  return s.toLowerCase().replace(/[^\w\u4e00-\u9fa5-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'skill-' + Date.now()
}

function frontmatter(name: string, description: string, enabled: boolean): string {
  return `---\nname: ${name}\ndescription: ${description || ''}\nenabled: ${enabled}\n---\n\n`
}

export function listSkills(): SkillInfo[] {
  const d = dir()
  if (!existsSync(d)) return []
  const out: SkillInfo[] = []
  for (const entry of readdirSync(d)) {
    const p = join(d, entry)
    if (!statSync(p).isDirectory()) continue
    const skill = parseSkill(entry)
    if (skill) out.push(skill)
  }
  return out
}

export function createSkill(data: { name: string; description?: string; instructions?: string }): SkillInfo {
  const id = slugify(data.name)
  const d = join(dir(), id)
  mkdirSync(d, { recursive: true })
  const content = frontmatter(data.name, data.description || '', true) + (data.instructions || '')
  writeFileSync(join(d, 'SKILL.md'), content, 'utf-8')
  const skill = parseSkill(id)!
  return skill
}

export function updateSkill(id: string, patch: { name?: string; description?: string; instructions?: string; enabled?: boolean }): SkillInfo {
  const existing = parseSkill(id)
  if (!existing) throw new Error('技能不存在')
  const content = frontmatter(patch.name ?? existing.name, patch.description ?? existing.description, patch.enabled ?? existing.enabled)
    + (patch.instructions !== undefined ? patch.instructions : existing.instructions)
  writeFileSync(join(dir(), id, 'SKILL.md'), content, 'utf-8')
  const skill = parseSkill(id)!
  return skill
}

export function toggleSkill(id: string, enabled: boolean): SkillInfo {
  return updateSkill(id, { enabled })
}

export function deleteSkill(id: string) {
  rmSync(join(dir(), id), { recursive: true, force: true })
}

export async function installSkillFromFolder(folderPath: string): Promise<SkillInfo> {
  const skillFile = join(folderPath, 'SKILL.md')
  if (!existsSync(skillFile)) throw new Error('所选文件夹中没有 SKILL.md')
  const id = slugify(basename(folderPath))
  const dest = join(dir(), id)
  if (existsSync(dest)) rmSync(dest, { recursive: true, force: true })
  mkdirSync(dir(), { recursive: true })
  cpSync(folderPath, dest, { recursive: true })
  const skill = parseSkill(id)
  if (!skill) throw new Error('技能格式无效')
  return skill
}

async function extractZip(zipPath: string, dest: string) {
  mkdirSync(dest, { recursive: true })
  const { execSync } = require('child_process')
  if (process.platform === 'win32') {
    execSync(`powershell -Command "Expand-Archive -Path '${zipPath}' -DestinationPath '${dest}' -Force"`, { stdio: 'pipe' })
  } else {
    execSync(`unzip -o "${zipPath}" -d "${dest}"`, { stdio: 'ignore' })
  }
}

function isGitHubUrl(url: string): boolean {
  return /^https:\/\/github\.com\//i.test(url) || /^https:\/\/www\.github\.com\//i.test(url)
}

function normalizeGitHubUrl(url: string): string {
  const clean = url.replace(/\/+$/, '')
  const m = clean.match(/github\.com\/([^\/]+)\/([^\/]+)(?:\/(.*))?/i)
  if (!m) throw new Error('无法解析 GitHub URL')
  const owner = m[1]
  const repo = m[2]
  let branch = 'main'
  let subPath = ''
  if (m[3]) {
    const rest = m[3]
    if (/^tree\//i.test(rest)) {
      const seg = rest.slice(5).split('/')
      branch = seg[0]
      subPath = seg.slice(1).join('/')
    } else if (/^archive\/refs\/heads\/.*\.zip$/i.test(rest)) {
      return `https://codeload.github.com/${owner}/${repo}/zip/refs/heads/${rest.match(/archive\/refs\/heads\/(.*)\.zip/i)![1]}`
    } else if (/^blob\//i.test(rest)) {
      const seg = rest.slice(5).split('/')
      branch = seg[0]
      subPath = seg.slice(1).join('/')
    }
  }
  return `https://codeload.github.com/${owner}/${repo}/zip/refs/heads/${branch}`
}

function findSkillDirs(dir: string): string[] {
  const out: string[] = []
  const walk = (d: string) => {
    let entries: string[] = []
    try { entries = readdirSync(d) } catch { return }
    for (const e of entries) {
      const p = join(d, e)
      let isDir = false
      try { isDir = statSync(p).isDirectory() } catch { continue }
      if (isDir) {
        if (existsSync(join(p, 'SKILL.md'))) out.push(p)
        walk(p)
      }
    }
  }
  walk(dir)
  return out
}

export async function installSkillFromUrl(url: string): Promise<SkillInfo> {
  const tmp = join(app.getPath('temp'), 'omniaide-skill-dl')
  if (existsSync(tmp)) rmSync(tmp, { recursive: true, force: true })
  mkdirSync(tmp, { recursive: true })
  const zipPath = join(tmp, 'skill.zip')
  const downloadUrl = isGitHubUrl(url) ? normalizeGitHubUrl(url) : url
  const res = await axios.get(downloadUrl, { responseType: 'arraybuffer', timeout: 60000, maxRedirects: 5 })
  const { writeFileSync: wf } = require('fs')
  wf(zipPath, Buffer.from(res.data))
  const extractDir = join(tmp, 'out')
  await extractZip(zipPath, extractDir)
  // find SKILL.md recursively (root or any depth)
  const skillDirs = findSkillDirs(extractDir)
  if (existsSync(join(extractDir, 'SKILL.md'))) skillDirs.unshift(extractDir)
  if (!skillDirs.length) throw new Error('ZIP 中没有找到 SKILL.md 技能')
  // prefer the deepest (most specific) skill dir
  const skillDir = skillDirs.sort((a, b) => b.split(/[\\/]/).length - a.split(/[\\/]/).length)[0]
  const id = slugify(basename(skillDir))
  const dest = join(dir(), id)
  if (existsSync(dest)) rmSync(dest, { recursive: true, force: true })
  mkdirSync(dir(), { recursive: true })
  cpSync(skillDir, dest, { recursive: true })
  const skill = parseSkill(id)
  rmSync(tmp, { recursive: true, force: true })
  if (!skill) throw new Error('技能格式无效')
  return skill
}

export async function pickSkillFolder(): Promise<string | null> {
  const result = await dialog.showOpenDialog({ properties: ['openDirectory', 'createDirectory'], title: '选择包含 SKILL.md 的文件夹' })
  return result.canceled || !result.filePaths[0] ? null : result.filePaths[0]
}

export function getEnabledInstructions(limit = 12000): string {
  const out: string[] = []
  let total = 0
  for (const s of listSkills()) {
    if (!s.enabled || !s.instructions) continue
    const block = `## 技能: ${s.name}\n${s.description ? `(描述: ${s.description})\n` : ''}${s.instructions}`
    if (total + block.length > limit) break
    out.push(block)
    total += block.length
  }
  return out.join('\n\n')
}

export function initSkillsManager() {
  mkdirSync(dir(), { recursive: true })
}
