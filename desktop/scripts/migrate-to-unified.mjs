import { readdirSync, existsSync, readFileSync, writeFileSync, mkdirSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const pluginsDir = join(__dirname, '..', 'plugins')

const nameMap = {
  'assistant': 'AI 助理',
  'calculator': '计算器',
  'clipboard-history': '剪贴板历史',
  'everything': 'Everything 搜索',
  'files': '文件管理',
  'notes': '笔记',
  'notifications': '通知',
  'player': '音乐播放器',
  'quick-notes': '快捷笔记',
  'remote': '远程控制',
  'rss': 'RSS 订阅',
  'schedule': '日程管理',
  'screenshot': '截图',
  'todo': '待办事项',
}

const iconMap = {
  'assistant': 'ChatDotSquare',
  'calculator': 'Calculator',
  'clipboard-history': 'CopyDocument',
  'everything': 'Search',
  'files': 'Folder',
  'notes': 'Document',
  'notifications': 'Bell',
  'player': 'Headset',
  'quick-notes': 'Lightning',
  'remote': 'Monitor',
  'rss': 'Rss',
  'schedule': 'Calendar',
  'screenshot': 'Camera',
  'todo': 'Check',
}

export function migratePlugin(pluginDir) {
  const name = pluginDir.split(/[\\/]/).pop()
  const pkgPath = join(pluginDir, 'package.json')
  if (!existsSync(pkgPath)) {
    console.log(`  [skip] no package.json`)
    return
  }

  const pkg = JSON.parse(readFileSync(pkgPath, 'utf-8'))
  const ns = pkg.omniaide || pkg.mqbox || {}
  const id = ns.id || name

  // Create manifest.json
  const manifest = {
    id,
    name: pkg.name || id,
    displayName: nameMap[id] || ns.displayName || pkg.displayName || id,
    description: pkg.description || '',
    version: pkg.version || '1.0.0',
    icon: iconMap[id] || ns.icon || '',
    keywords: ns.keywords || [],
    permissions: ns.permissions || [],
    builtin: false,
    main: 'dist/index.js',
  }

  writeFileSync(join(pluginDir, 'manifest.json'), JSON.stringify(manifest, null, 2), 'utf-8')
  console.log(`  [ok] manifest.json for ${id}`)

  // Create frontend placeholder if it doesn't exist
  const frontendDir = join(pluginDir, 'frontend')
  if (!existsSync(frontendDir)) {
    mkdirSync(frontendDir, { recursive: true })
    const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${manifest.displayName}</title>
  <style>
    * { margin:0; padding:0; box-sizing:border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           display:flex; align-items:center; justify-content:center;
           height:100vh; background:#f5f5f5; color:#333; }
    .container { text-align:center; }
    h1 { font-size:24px; margin-bottom:8px; }
    p { color:#909399; margin-bottom:24px; }
    .placeholder { width:120px;height:120px;background:#e0e0e0;border-radius:16px;
                   display:flex;align-items:center;justify-content:center;
                   margin:0 auto 16px; font-size:48px; }
    .btn { display:inline-block;padding:8px 20px;background:#0078D4;color:#fff;
           border:none;border-radius:8px;cursor:pointer;font-size:14px; }
    .btn:hover { background:#106ebe; }
  </style>
</head>
<body>
  <div class="container">
    <div class="placeholder">🖥️</div>
    <h1>${manifest.displayName}</h1>
    <p>${manifest.description || ''}</p>
    <p style="font-size:12px;color:#c0c4cc;">此插件的前端页面正在开发中</p>
  </div>
</body>
</html>`
    writeFileSync(join(frontendDir, 'index.html'), html, 'utf-8')
    console.log(`  [ok] frontend/index.html placeholder for ${id}`)
  } else {
    console.log(`  [skip] frontend/ already exists for ${id}`)
  }
}

// Run migration
console.log('Migrating plugins to unified format...')
const entries = readdirSync(pluginsDir, { withFileTypes: true })
let count = 0
for (const entry of entries) {
  if (entry.isDirectory()) {
    const dir = join(pluginsDir, entry.name)
    console.log(`\n[${entry.name}]`)
    try {
      migratePlugin(dir)
      count++
    } catch (e) {
      console.error(`  [err] ${e.message}`)
    }
  }
}
console.log(`\nDone. ${count} plugins migrated.`)
