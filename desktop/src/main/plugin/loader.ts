import { readdirSync, existsSync, readFileSync } from 'fs'
import { join } from 'path'
import { app } from 'electron'
import type { PluginManifest, PluginInfo } from '../../shared/types'

function findPluginDirs(): string[] {
  const searchPaths = [
    join(__dirname, '../../../plugins'),       // dev
    join(__dirname, '../../plugins'),          // dev alt
    join(app.getPath('userData'), 'plugins'),  // production
  ]
  const dirs: string[] = []
  for (const base of searchPaths) {
    if (!existsSync(base)) continue
    for (const entry of readdirSync(base, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        const pluginDir = join(base, entry.name)
        if (existsSync(join(pluginDir, 'package.json'))) {
          dirs.push(pluginDir)
        }
      }
    }
  }
  return [...new Set(dirs)]
}

export function loadPlugins(): Map<string, PluginInfo> {
  const plugins = new Map<string, PluginInfo>()
  for (const dir of findPluginDirs()) {
    try {
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
        builtin: mqbox.builtin !== false,
        main: pkg.main || 'dist/index.js',
      }
      plugins.set(manifest.id, { id: manifest.id, manifest, path: dir, enabled: true })
    } catch (e) {
      console.error(`Failed to load plugin from ${dir}:`, e)
    }
  }
  return plugins
}
