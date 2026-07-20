import { execSync } from 'child_process'
import { existsSync, readFileSync, cpSync, rmSync, mkdirSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
import { createRequire } from 'module'

const __dirname = dirname(fileURLToPath(import.meta.url))
const desktopDir = join(__dirname, '..')
const backendMarketplaceDir = join(__dirname, '..', '..', 'backend', 'desktop_plugins')

const pluginId = process.argv[2]
if (!pluginId) {
  console.error('Usage: node build-plugin.mjs <plugin-id>')
  console.error('Example: node build-plugin.mjs todo')
  process.exit(1)
}

const pluginDir = join(desktopDir, 'plugins', pluginId)
const pkgPath = join(pluginDir, 'package.json')

if (!existsSync(pkgPath)) {
  console.error(`Plugin not found: ${pluginId}`)
  process.exit(1)
}

const pkg = JSON.parse(readFileSync(pkgPath, 'utf-8'))
console.log(`=== Building plugin: ${pkg.name} (${pluginId}) ===`)

// Build
console.log('[1/3] Installing dependencies...')
execSync('npm install', { cwd: pluginDir, stdio: 'inherit' })

console.log('[2/3] Building...')
if (pkg.scripts?.build) {
  execSync('npm run build', { cwd: pluginDir, stdio: 'inherit' })
} else {
  console.log('No build script, assuming pre-built')
}

// Package
console.log('[3/3] Packaging...')
const targetDir = join(backendMarketplaceDir, pluginId)
if (existsSync(targetDir)) rmSync(targetDir, { recursive: true })
mkdirSync(targetDir, { recursive: true })

// Copy everything except node_modules
cpSync(pluginDir, targetDir, {
  recursive: true,
  filter: (src) => !src.includes('node_modules'),
})

// Create zip using system zip or tar
const zipPath = join(targetDir, 'plugin.zip')
if (existsSync(zipPath)) rmSync(zipPath)

execSync(`tar -a -c -f "plugin.zip" -C "${targetDir}" .`, {
  cwd: targetDir, stdio: 'inherit',
  shell: true,
})

console.log(`\n=== Done: ${zipPath} ===`)
