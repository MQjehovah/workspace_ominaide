import { readdirSync, existsSync, writeFileSync, mkdirSync, rmSync, readFileSync } from 'fs'
import { join, dirname, resolve } from 'path'
import { fileURLToPath } from 'url'
import { build } from 'vite'
import vue from '@vitejs/plugin-vue'

const __dirname = dirname(fileURLToPath(import.meta.url))
const pluginsDir = resolve(__dirname, '..', 'plugins')

const pagePlugins = [
  'assistant', 'calculator', 'clipboard-history', 'files', 'notes',
  'notifications', 'player', 'quick-notes', 'remote', 'rss',
  'schedule', 'screenshot', 'todo',
]
const noPagePlugins = ['everything']

async function buildPluginFrontend(name) {
  const pluginDir = resolve(pluginsDir, name)
  const srcDir = resolve(pluginDir, 'src')
  const pagePath = resolve(srcDir, 'Page.vue')
  const frontendDir = resolve(pluginDir, 'frontend')

  if (!existsSync(pagePath)) {
    console.log(`  [skip] ${name}: no Page.vue`)
    return
  }

  // Clean previous frontend
  if (existsSync(frontendDir)) {
    rmSync(frontendDir, { recursive: true })
  }

  // Create temporary build directory inside the plugin
  const buildDir = resolve(pluginDir, '.frontend-build')
  if (existsSync(buildDir)) rmSync(buildDir, { recursive: true })
  mkdirSync(buildDir, { recursive: true })

  // Template files from plugin's own directory
  writeFileSync(resolve(buildDir, 'index.html'), readFileSync(resolve(pluginDir, 'index.html'), 'utf-8'), 'utf-8')
  writeFileSync(resolve(buildDir, 'plugin-app.ts'), readFileSync(resolve(pluginDir, 'plugin-app.ts'), 'utf-8'), 'utf-8')
  const entryContent = `import Page from '../src/Page.vue'
import { mountPlugin } from './plugin-app'
mountPlugin(Page, '${name}')
`
  writeFileSync(resolve(buildDir, 'entry.ts'), entryContent, 'utf-8')

  try {
    await build({
      root: buildDir,
      plugins: [vue()],
      base: './',
      build: {
        outDir: frontendDir,
        emptyOutDir: true,
      },
    })
    console.log(`  [ok] ${name}: frontend built (${getDirSize(frontendDir)} KB)`)
  } catch (e) {
    console.error(`  [err] ${name}: ${e.message}`)
  } finally {
    if (existsSync(buildDir)) rmSync(buildDir, { recursive: true })
  }
}

function getDirSize(dir) {
  let size = 0
  function walk(d) {
    for (const entry of readdirSync(d, { withFileTypes: true })) {
      const p = join(d, entry.name)
      if (entry.isDirectory()) walk(p)
      else size += readFileSync(p).length
    }
  }
  walk(dir)
  return Math.round(size / 1024)
}

async function main() {
  console.log('Building plugin frontends...\n')

  for (const name of pagePlugins) {
    process.stdout.write(`[${name}] `)
    await buildPluginFrontend(name)
  }

  // Minimal frontend for plugins without Page.vue
  for (const name of noPagePlugins) {
    const pluginDir = resolve(pluginsDir, name)
    const frontendDir = resolve(pluginDir, 'frontend')
    if (!existsSync(frontendDir)) {
      mkdirSync(frontendDir, { recursive: true })
      const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>${name}</title></head>
<body style="display:flex;align-items:center;justify-content:center;height:100vh;margin:0;font-family:sans-serif;color:#909399;background:#f5f5f5">
<div style="text-align:center"><h1>${name}</h1><p>无前端界面</p></div>
</body></html>`
      writeFileSync(resolve(frontendDir, 'index.html'), html, 'utf-8')
      process.stdout.write(`[${name}] minimal frontend\n`)
    }
  }

  console.log('\nDone.')
}

main().catch(console.error)
