import { readdirSync, existsSync, readFileSync } from 'fs'
import { join } from 'path'
import { app } from 'electron'
import type { PluginManifest, PluginInfo } from '../../shared/types'

interface PluginDir {
  path: string
  builtin: boolean
}

function findPluginDirs(): PluginDir[] {
  const dirs: PluginDir[] = []
  if (app.isPackaged) {
    // Load bundled built-ins first, then user-installed plugins so a user copy
    // with the same id overrides the bundled one.
    const roots = [
      join(process.resourcesPath, 'plugins'),
      join(app.getPath('userData'), 'plugins'),
    ]
    for (const [index, root] of roots.entries()) {
      if (!existsSync(root)) continue
      for (const entry of readdirSync(root, { withFileTypes: true })) {
        if (entry.isDirectory()) {
          const pluginDir = join(root, entry.name)
          if (existsSync(join(pluginDir, 'manifest.json')) || existsSync(join(pluginDir, 'package.json'))) {
            dirs.push({ path: pluginDir, builtin: index === 0 })
          }
        }
      }
    }
  } else {
    const devPaths = [
      join(__dirname, '../../../plugins'),   // dev
      join(__dirname, '../../plugins'),      // dev alt
    ]
    for (const base of devPaths) {
      if (!existsSync(base)) continue
      for (const entry of readdirSync(base, { withFileTypes: true })) {
        if (entry.isDirectory()) {
          const pluginDir = join(base, entry.name)
          if (existsSync(join(pluginDir, 'manifest.json')) || existsSync(join(pluginDir, 'package.json'))) {
            dirs.push({ path: pluginDir, builtin: true })
          }
        }
      }
    }
  }
  const unique = new Map<string, PluginDir>()
  for (const item of dirs) unique.set(item.path, item)
  return [...unique.values()]
}

export function loadPlugins(): Map<string, PluginInfo> {
  const plugins = new Map<string, PluginInfo>()
  for (const { path: dir, builtin } of findPluginDirs()) {
    try {
      // try unified manifest first
      const manifestPath = join(dir, 'manifest.json')
      if (existsSync(manifestPath)) {
        const m = JSON.parse(readFileSync(manifestPath, 'utf-8'))
        const manifest: PluginManifest = {
          id: m.id || m.name,
          name: m.name || m.id,
          displayName: m.displayName || m.name || m.id,
          description: m.description,
          version: m.version,
          icon: m.icon,
          keywords: m.keywords || [],
          permissions: m.permissions || [],
          builtin: builtin || m.builtin !== false,
          main: m.main || 'dist/index.js',
        }
        plugins.set(manifest.id, { id: manifest.id, manifest, path: dir, enabled: true })
        continue
      }

      // fallback to legacy package.json
      const pkg = JSON.parse(readFileSync(join(dir, 'package.json'), 'utf-8'))
      const mqbox = pkg.omniaide || pkg.mqbox || {}
      const manifest: PluginManifest = {
        id: mqbox.id || pkg.name,
        name: pkg.name,
        displayName: mqbox.displayName || pkg.displayName || pkg.name,
        description: pkg.description,
        version: pkg.version,
        icon: mqbox.icon,
        keywords: mqbox.keywords || [],
        permissions: mqbox.permissions || [],
        builtin: builtin || mqbox.builtin !== false,
        main: pkg.main || 'dist/index.js',
      }
      plugins.set(manifest.id, { id: manifest.id, manifest, path: dir, enabled: true })
    } catch (e) {
      console.error(`Failed to load plugin from ${dir}:`, e)
    }
  }
  return plugins
}
