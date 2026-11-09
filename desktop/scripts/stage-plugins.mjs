import { createRequire } from 'module'
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync } from 'fs'
import { builtinModules } from 'module'
import { dirname, join, resolve } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const projectDir = resolve(__dirname, '..')
const pluginsDir = join(projectDir, 'plugins')
const outDir = join(projectDir, 'plugin-bundle')

// Only the AI assistant ships with the app. Every other plugin is distributed
// through the web plugin marketplace and installed on demand.
const BUNDLED_PLUGINS = new Set(['assistant'])

const builtins = new Set([
  ...builtinModules,
  ...builtinModules.map(name => `node:${name}`),
])

function walkFiles(dir, out = []) {
  if (!existsSync(dir)) return out
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) walkFiles(path, out)
    else if (/\.(js|cjs|mjs)$/.test(entry.name)) out.push(path)
  }
  return out
}

function rootPackageName(spec) {
  if (spec.startsWith('@')) return spec.split('/').slice(0, 2).join('/')
  return spec.split('/')[0]
}

function collectExternalRequires(pluginDir) {
  const found = new Set()
  const re = /require\(\s*['"]([^'"]+)['"]\s*\)/g
  for (const file of walkFiles(join(pluginDir, 'dist'))) {
    const source = readFileSync(file, 'utf-8')
    let match
    while ((match = re.exec(source))) {
      const spec = match[1]
      if (!spec || spec.startsWith('.') || spec.startsWith('/')) continue
      if (spec.startsWith('node:') || builtins.has(spec)) continue
      if (spec === 'electron' || spec === 'original-fs') continue
      found.add(rootPackageName(spec))
    }
  }
  return found
}

function findPackageRoot(start) {
  let current = start
  while (current !== dirname(current)) {
    if (existsSync(join(current, 'package.json'))) return current
    current = dirname(current)
  }
  return null
}

function copyPackage(pluginId, name, fromRoots, outNodeModules, seen) {
  if (seen.has(name)) return
  seen.add(name)

  let resolved = null
  for (const base of fromRoots) {
    try {
      const req = createRequire(join(base, 'package.json'))
      resolved = findPackageRoot(req.resolve(name))
      if (resolved) break
    } catch {
      // try next root
    }
  }
  if (!resolved) {
    console.warn(`  [warn] ${pluginId}: runtime dependency "${name}" not found`)
    return
  }

  const dest = join(outNodeModules, name)
  mkdirSync(dirname(dest), { recursive: true })
  cpSync(resolved, dest, {
    recursive: true,
    dereference: true,
    filter: source => !source.includes('/node_modules/') && !source.includes('/.bin/'),
  })

  const pkgFile = join(resolved, 'package.json')
  if (!existsSync(pkgFile)) return
  const pkg = JSON.parse(readFileSync(pkgFile, 'utf-8'))
  for (const dep of Object.keys(pkg.dependencies || {})) {
    copyPackage(pluginId, dep, fromRoots, outNodeModules, seen)
  }
}

function directorySize(dir) {
  let total = 0
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    total += entry.isDirectory() ? directorySize(path) : statSync(path).size
  }
  return total
}

function stagePlugin(entryName) {
  const pluginDir = join(pluginsDir, entryName)
  const manifestPath = join(pluginDir, 'manifest.json')
  if (!existsSync(manifestPath)) return false

  const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8'))
  const id = manifest.id || entryName
  const target = join(outDir, id)
  console.log(`[stage] ${id}`)
  mkdirSync(target, { recursive: true })

  cpSync(manifestPath, join(target, 'manifest.json'))
  if (existsSync(join(pluginDir, 'package.json'))) {
    cpSync(join(pluginDir, 'package.json'), join(target, 'package.json'))
  }
  if (existsSync(join(pluginDir, 'dist'))) {
    cpSync(join(pluginDir, 'dist'), join(target, 'dist'), { recursive: true })
  }
  if (existsSync(join(pluginDir, 'frontend'))) {
    cpSync(join(pluginDir, 'frontend'), join(target, 'frontend'), { recursive: true })
  }

  const requires = collectExternalRequires(pluginDir)
  if (requires.size) {
    const outNodeModules = join(target, 'node_modules')
    mkdirSync(outNodeModules, { recursive: true })
    const seen = new Set()
    for (const name of requires) {
      copyPackage(id, name, [pluginDir, projectDir], outNodeModules, seen)
    }
    console.log(`  [deps] ${[...requires].join(', ')}`)
  }
  return true
}

rmSync(outDir, { recursive: true, force: true })
mkdirSync(outDir, { recursive: true })

let count = 0
for (const entry of readdirSync(pluginsDir, { withFileTypes: true })) {
  if (!entry.isDirectory() || entry.name.startsWith('.')) continue
  if (!BUNDLED_PLUGINS.has(entry.name)) continue
  if (stagePlugin(entry.name)) count++
}

const size = directorySize(outDir)
console.log(`\nStaged ${count} plugin(s) into ${outDir} (${(size / 1024 / 1024).toFixed(1)} MB)`)
