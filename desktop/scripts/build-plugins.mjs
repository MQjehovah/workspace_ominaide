import { execSync } from 'child_process'
import { readdirSync, existsSync, readFileSync, rmSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const pluginsDir = join(__dirname, '..', 'plugins')

const entries = readdirSync(pluginsDir, { withFileTypes: true })
for (const entry of entries) {
  if (!entry.isDirectory() || entry.name.startsWith('.')) continue

  const pluginDir = join(pluginsDir, entry.name)
  const pkgPath = join(pluginDir, 'package.json')
  if (!existsSync(pkgPath)) continue

  const pkg = JSON.parse(readFileSync(pkgPath, 'utf-8'))
  if (!pkg.scripts?.build && !existsSync(join(pluginDir, 'vite.config.ts'))) continue

  // Force rebuild: delete old dist
  const distDir = join(pluginDir, 'dist')
  if (existsSync(distDir)) rmSync(distDir, { recursive: true })

  console.log(`[BUILD] ${entry.name}`)
  const nodeModules = join(pluginDir, 'node_modules')
  if (!existsSync(nodeModules)) {
    execSync('npm install', { cwd: pluginDir, stdio: 'inherit', timeout: 120000 })
  }
  execSync('npm run build', { cwd: pluginDir, stdio: 'inherit', timeout: 120000 })
}
