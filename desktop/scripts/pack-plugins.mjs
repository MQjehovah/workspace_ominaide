import { readdirSync, existsSync, readFileSync, writeFileSync, rmSync, mkdirSync, cpSync } from 'fs'
import { join, dirname, resolve } from 'path'
import { fileURLToPath } from 'url'
import { execSync } from 'child_process'

const __dirname = dirname(fileURLToPath(import.meta.url))
const pluginsDir = resolve(__dirname, '..', 'plugins')
const outDir = resolve(__dirname, '..', 'plugin-packages')

function ensurePluginBuilt(name) {
  const pluginDir = join(pluginsDir, name)
  const distDir = join(pluginDir, 'dist')
  const frontendDir = join(pluginDir, 'frontend')

  // Build plugin code if not built
  if (!existsSync(join(distDir, 'index.js'))) {
    console.log(`  [build] building plugin code...`)
    const pkgPath = join(pluginDir, 'package.json')
    if (existsSync(pkgPath)) {
      const nodeModules = join(pluginDir, 'node_modules')
      if (!existsSync(nodeModules)) {
        execSync('npm install', { cwd: pluginDir, stdio: 'pipe', timeout: 120000 })
      }
      execSync('npm run build', { cwd: pluginDir, stdio: 'pipe', timeout: 120000 })
    }
  }

  // Build frontend if not built
  if (!existsSync(join(frontendDir, 'index.html'))) {
    console.log(`  [build] building frontend...`)
    execSync(`node "${join(__dirname, 'build-frontends.mjs')}"`, { stdio: 'pipe', timeout: 120000 })
  }

  if (!existsSync(join(distDir, 'index.js'))) {
    throw new Error(`Plugin ${name}: dist/index.js not found after build`)
  }
  // frontend is optional (backend-only plugins like activity have no frontend)
}

function copyRuntimeDeps(pluginDir, tmpDir, pkg) {
  const deps = pkg?.dependencies || {}
  const names = Object.keys(deps).filter(Boolean)
  if (!names.length) return

  const srcNm = join(pluginDir, 'node_modules')
  if (!existsSync(srcNm)) return

  const dstNm = join(tmpDir, 'node_modules')
  let count = 0
  for (const dep of names) {
    const src = join(srcNm, dep)
    if (!existsSync(src)) {
      console.warn(`  [warn] runtime dep "${dep}" not found in plugin node_modules`)
      continue
    }
    // scoped packages live under node_modules/@scope/name
    const dst = join(dstNm, dep)
    cpSync(src, dst, { recursive: true })
    count++
  }
  if (count) console.log(`  [deps] bundled ${count} runtime dependencies`)
}

function packPlugin(name) {
  const pluginDir = join(pluginsDir, name)
  const manifestPath = join(pluginDir, 'manifest.json')
  if (!existsSync(manifestPath)) {
    console.log(`  [skip] no manifest.json`)
    return
  }

  const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8'))
  const id = manifest.id || name
  const version = manifest.version || '1.0.0'

  console.log(`  packing ${id}@${version}...`)

  const tmpDir = join(outDir, `.tmp-${id}`)
  if (existsSync(tmpDir)) rmSync(tmpDir, { recursive: true })
  mkdirSync(tmpDir, { recursive: true })

  // Copy required files
  cpSync(join(pluginDir, 'manifest.json'), join(tmpDir, 'manifest.json'))
  cpSync(join(pluginDir, 'dist'), join(tmpDir, 'dist'), { recursive: true })
  // frontend is optional (backend-only plugins have none)
  const frontendDir = join(pluginDir, 'frontend')
  if (existsSync(frontendDir)) {
    cpSync(frontendDir, join(tmpDir, 'frontend'), { recursive: true })
  }

  // Optional: package.json
  const pkgPath = join(pluginDir, 'package.json')
  let pkg = null
  if (existsSync(pkgPath)) {
    pkg = JSON.parse(readFileSync(pkgPath, 'utf-8'))
    cpSync(pkgPath, join(tmpDir, 'package.json'))
  }

  // Bundle runtime dependencies (from `dependencies`) so the plugin works in the
  // packaged app without relying on the host's node_modules (e.g. protobufjs, ws).
  copyRuntimeDeps(pluginDir, tmpDir, pkg)

  // Create zip
  const zipName = `${id}-${version}.zip`
  const zipPath = join(outDir, zipName)
  if (existsSync(zipPath)) rmSync(zipPath)

  const { platform } = process
  if (platform === 'win32') {
    execSync(`powershell -Command "Compress-Archive -Path '${tmpDir}\\*' -DestinationPath '${zipPath}' -Force"`, { stdio: 'pipe' })
  } else {
    execSync(`cd "${tmpDir}" && zip -r "${zipPath}" .`, { stdio: 'pipe' })
  }

  rmSync(tmpDir, { recursive: true })

  const size = (readFileSync(zipPath).length / 1024).toFixed(1)
  console.log(`  [ok] ${zipName} (${size} KB)`)
}

async function main() {
  console.log('Packing plugins for marketplace upload...\n')

  if (!existsSync(outDir)) mkdirSync(outDir, { recursive: true })

  const entries = readdirSync(pluginsDir, { withFileTypes: true })
  let count = 0

  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name.startsWith('.')) continue
    if (entry.name === 'node_modules') continue

    const pluginDir = join(pluginsDir, entry.name)
    const manifestPath = join(pluginDir, 'manifest.json')
    if (!existsSync(manifestPath)) continue

    process.stdout.write(`[${entry.name}] `)

    try {
      ensurePluginBuilt(entry.name)
      packPlugin(entry.name)
      count++
    } catch (e) {
      console.error(`  [err] ${e.message}`)
    }
  }

  console.log(`\nDone. ${count} plugins packed to ${outDir}`)
}

main().catch(console.error)
