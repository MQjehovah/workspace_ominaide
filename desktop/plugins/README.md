# OmniAide 插件开发指南

插件是 `plugins/<id>/` 目录，包含 `manifest.json` 与 `main`（默认 `dist/index.js`）。
主进程侧的插件运行在独立子进程中，通过 `PluginContext` 访问宿主能力；带 `frontend/index.html`
的插件还可以拥有自己的页面窗口。

```jsonc
// manifest.json
{
  "id": "demo",
  "name": "omniaide-demo",
  "displayName": "演示插件",
  "version": "1.0.0",
  "permissions": ["storage", "notification", "shell"],
  "main": "dist/index.js"
}
```

`permissions` 会被真正校验。权限模型见下文，声明后仍需用户授权敏感项。

```ts
export default {
  async activate(context) {
    context.registerCommand('getPanelData', async () => ({ title: '演示插件' }))
  },
  deactivate() {},
}
```

## 权限模型

插件能做的事情由 `permissions` 声明，宿主在**每一次桥接调用**前校验（包括
`context.signal('...')`，它本质上就是一次原始 RPC）。未声明的权限无法调用。

| 权限 | 风险 | 说明 |
| --- | --- | --- |
| `storage` | 普通 | 插件私有本地存储 |
| `notification` | 普通 | 系统通知 |
| `menu` / `tray` / `palette` | 普通 | 右键菜单 / 托盘菜单 / 命令面板 |
| `clipboard:write` | 普通 | 写入剪贴板 |
| `files:read` | 普通 | 通过文件选择框读文件 |
| `shell:open` | 普通 | 打开链接或文件 |
| `api` | 敏感 | 以用户身份访问 OmniAide 后端 |
| `channel` | 敏感 | 后端 WebSocket 通道 |
| `clipboard:read` | 敏感 | 读取剪贴板内容 |
| `selection` | 敏感 | 读取其他应用中选中的文本 |
| `screenshot` | 敏感 | 截屏与截图历史 |
| `events` | 敏感 | 接收剪贴板/文件/电源/网络/显示器/空闲/前台应用事件 |
| `actions` | 敏感 | 注册通用动作（可接收选中文本、文件、图片） |
| `deeplink` | 普通 | 注册 omniaide:// 外部深链 |
| `schedule` | 普通 | 在应用运行时执行定时任务 |
| `shortcut` | 敏感 | 注册全局快捷键 |
| `files:write` | 敏感 | 修改/删除本地文件 |
| `shell:exec` | 高危 | 执行任意命令 |
| `pty` | 高危 | 打开终端会话 |
| `remote` | 高危 | 远程控制（屏幕/键鼠） |
| `config` | 高危 | 读取应用配置（可能含登录令牌） |

规则：

- 普通权限在安装时自动通过；敏感/高危权限会弹窗确认，拒绝则取消安装。
- 运行中插件调用**未声明**的敏感/高危能力时会单独询问一次，不会静默放行。
- 用户可以在「插件管理 → 权限」里随时收回或重新授予，立即生效。
- 权限系统上线前已安装的插件会被标记为「历史插件」，未声明的能力首次使用时自动授权并记录审计日志，可在权限面板复核。
- 开发模式（未打包）和随应用内置的插件视为可信，声明即授权。
- 旧权限名 `clipboard` / `shell` / `files` 会自动展开为新权限，无需改代码，但新插件建议直接用细粒度名称。

## 事件与定时任务

### 系统事件

```ts
// 剪贴板变化
const offClipboard = context.on('clipboard', ({ text }) => {
  console.log('copied:', text)
})

// 文件变化（目录或文件）
context.on('file', ({ path, type }) => {
  // type: 'add' | 'change' | 'unlink'
}, { path: '~/Downloads' })

// 电源 / 网络 / 显示器 / 空闲
context.on('power', ({ type }) => {})          // suspend, resume, lock-screen, ...
context.on('network', ({ online }) => {})
context.on('display', ({ type, display }) => {})
context.on('idle', ({ idle, seconds }) => {}, { thresholdSeconds: 300 })
context.on('app-changed', ({ name, title }) => {})   // 前台应用/窗口切换
const active = await context.getActiveWindow()       // 立即获取当前前台应用

// 自定义事件（插件之间）
context.on('my-event', (payload) => {})
context.emit('my-event', { hello: 'world' })

offClipboard() // 退订
```

需要 `events` 权限（敏感）。文件监听只在应用运行期间有效；macOS/Windows 支持递归，Linux 为单层目录。

### 定时任务

```ts
context.schedule({ id: 'morning', cron: '0 9 * * *' }, async () => {
  // 每天 9:00
})

context.schedule({ id: 'ping', every: '30s' }, () => {})
context.schedule({ id: 'once', at: '2026-11-14T09:00:00+08:00' }, () => {})

context.unschedule('ping')
```

- 需要 `schedule` 权限
- 支持五段 cron（分 时 日 月 周，不支持秒）、`every`（`30s`/`5m`/`1h`/`1d`）和一次性 `at`
- 每个插件最多 50 个任务；应用退出后不会后台执行，重启插件时会重新注册
- 回调参数为 `{ id }`

### 通知 2.0

```ts
context.notification.show({
  title: '构建完成',
  body: '用时 42s',
  silent: false,
  command: 'openBuild',                     // 点击通知执行插件命令
  actions: [                                // macOS 通知按钮
    { id: 'done', title: '标记完成', command: 'markDone' },
  ],
  deepLink: 'https://mqgeek.com/ominaide/', // 点击时用浏览器打开
})

context.on('notification-click', () => {})   // 未提供 command 时触发
context.on('notification-action', ({ actionId }) => {})
```

通知按插件限频（800ms 内只发一条），避免刷屏。

## 通用动作（Universal Actions）

一个动作可以同时出现在划词浮条、文件管理、截图编辑器和深链中，宿主会按输入类型和条件过滤。

```ts
context.registerAction({
  id: 'summarize',
  title: '总结这段内容',
  description: '支持选中文本和文件',
  icon: '✨',
  accepts: ['text', 'url', 'file'],
  when: {
    app: ['Finder', 'Code'],     // 仅在指定应用前台时出现
    ext: ['md', 'txt', 'pdf'],   // 文件动作的扩展名
  },
  command: 'onAction',           // 通过 registerCommand 注册
  arguments: [                   // 可选：执行前弹表单
    { name: 'tone', label: '语气', type: 'select', options: [
      { label: '简洁', value: 'short' }, { label: '详细', value: 'long' },
    ], default: 'short' },
  ],
})

context.registerCommand('onAction', async (ctx) => {
  // ctx: { type, text?, url?, image?, files?, app?, source }
  // files 元素: { name, path?, remoteId?, mime?, size? }
  return { message: '已完成' }   // 浮条/文件弹窗会显示 message
})
```

当前入口：

- **划词浮条**：`accepts` 包含 `text` / `url`
- **文件管理**：文件行或预览里的「⚡ 动作」，传入 `files`（远程文件带 `remoteId`）
- **截图编辑器**：工具栏「⚡」，传入 `image`（PNG Data URL）

返回 `{ replace }` / `{ copy }` / `{ message }` 时，划词浮条会按同样规则处理。

## 懒启动

插件默认随应用启动。需要减少开机进程时，在 manifest 中声明：

```json
{
  "activation": "lazy",
  "search": true
}
```

- `activation: "lazy"`：启动时不运行，面板显示「按需启动」，点击启动、打开页面或执行命令时再启动
- `search: true`：打开全局搜索时提前启动，确保搜索结果不缺失
- 托盘/划词/通用动作只有插件启动后才可用；需要常驻的采集类插件不要设为 lazy

## 前台应用与兜底搜索

```ts
context.on('app-changed', ({ name, title }) => {})
const active = await context.getActiveWindow()

context.registerSearchProvider({
  keyword: '',
  name: '我的兜底',
  fallback: true,             // 普通搜索无结果时才运行
  onSearch: async (query) => [],
})
```

`app-changed` / `getActiveWindow` 需要 `events` 权限；macOS 需要辅助功能权限才能读取窗口标题。

## 深链

注册后可通过系统打开 `omniaide://plugin/<pluginId>/<path>?a=b`：

```ts
context.registerDeepLink({
  path: 'new-note',
  command: 'handleDeepLink',
  description: '从浏览器新建笔记',
})

context.registerCommand('handleDeepLink', async ({ path, query, url }) => {})
```

也支持直接触发通用动作：

```text
omniaide://action/action%3Aplugin-id%3Aaction-id?type=text&text=hello
```

深链只在安装版生效（开发模式不会注册系统协议）。

## 面板（主窗口卡片）

`getPanelData` 返回主面板卡片内容。除 `items` / `switches` / `buttons` 外，现在还支持三种富内容块，
不需要单独做页面：

```ts
return {
  title: '系统监控',
  subtitle: '实时状态',
  progress: [
    { label: 'CPU', value: 42, max: 100, tone: 'default', hint: '4 核' },
  ],
  charts: [
    { label: 'CPU 趋势', type: 'line', labels: ['1', '', '', '4'], values: [12, 20, 35, 42] },
    // type: 'bar' 时按柱状图渲染
  ],
  forms: [
    {
      fields: [
        { key: 'text', label: '文本', type: 'textarea', placeholder: '输入内容' },
        {
          key: 'target',
          label: '目标',
          type: 'select',
          value: 'zh',
          options: [{ label: '中文', value: 'zh' }, { label: 'English', value: 'en' }],
        },
        { key: 'remember', label: '记住', type: 'switch', value: true },
      ],
      submitLabel: '提交',
      command: 'submitForm', // 字段值会作为 args 传入
    },
  ],
}
```

表单提交时会调用 `command`，参数是 `{ ...commandArgs, ...当前字段值 }`。

## 上下文菜单

在插件进程里弹出原生菜单，返回被点击项的 `id`（取消为 `null`）：

```ts
const id = await context.showContextMenu([
  { id: 'open', label: '打开' },
  { id: 'copy', label: '复制链接' },
  { type: 'separator' },
  { id: 'delete', label: '删除' },
])
if (id === 'delete') await context.signal('shell:openPath', path)
```

支持 `type: 'checkbox'`、`enabled`、`submenu`。

## 应用坞（Tray）菜单

把插件命令挂到系统托盘菜单，宿主会按插件自动分组：

```ts
context.setTrayItems([
  { id: 'open', label: '打开翻译', command: 'open' },
  { id: 'translate-clipboard', label: '翻译剪贴板', command: 'translateClipboard' },
])
```

重复调用会整体替换该插件的菜单项；菜单项点击时执行 `command`，`args` 可选。

## 全局搜索 / 命令面板

注册后，命令会出现在全局搜索（`Ctrl+Space`）的结果最上方，也可按标题/关键词过滤：

```ts
context.registerPaletteItem({
  id: 'search',
  title: '搜索笔记',
  subtitle: '先输入关键词',
  icon: '🔍',
  keywords: ['note', '笔记'],
  command: 'searchNotes',
  arguments: [
    { name: 'query', label: '关键词', type: 'text', required: true },
    { name: 'scope', label: '范围', type: 'select', options: [
      { label: '全部', value: 'all' }, { label: '最近', value: 'recent' },
    ], default: 'all' },
  ],
})
```

## 划词动作（系统级选中文本）

用户在任意应用里选中文字后按 `Ctrl+Shift+D`，会出现划词浮条，列出所有插件注册的动作：

```ts
context.registerSelectionAction({
  id: 'translate-replace',
  title: '翻译并替换',
  description: '自动识别中英文，结果替换选中文本',
  icon: '🌐',
  command: 'translateSelection',
  args: { mode: 'replace' },
})

context.registerCommand('translateSelection', async ({ text, mode }) => {
  const translated = await doTranslate(text)
  if (mode === 'copy') return { copy: translated }        // 写入剪贴板并关闭浮条
  return { replace: translated }                          // 粘贴回原应用（会恢复剪贴板）
})
```

动作返回值约定：

| 返回 | 行为 |
| --- | --- |
| `{ replace: string }` | 替换原应用中选中的文本（需要辅助功能权限） |
| `{ copy: string }` | 复制到剪贴板 |
| `{ message: string }` | 浮条内展示提示，保持打开 |
| 无 / 其它 | 直接关闭浮条 |

划词需要 macOS「辅助功能」权限：宿主在首次触发时会提示并打开系统设置。
读取选中文本的方式是模拟 `Cmd+C` 后读取剪贴板，完成后会恢复原剪贴板内容。

## 其它常用能力

- `context.api.*`：后端代理（自动附带登录 token、401 自动刷新）
- `context.storage.get/set`：插件私有 JSON 存储
- `context.notification.show(title, body)`
- `context.signal('...')`：调用宿主桥接能力，如 `clipboard:writeText`、`cli:...`
- `context.registerSearchProvider({ keyword, name, onSearch })`：接入全局搜索语法
- `context.registerCommand(name, handler)` + `context.openPage(id)`
- `context.log(level, message)`：写入插件日志

## 日志与生命周期

插件进程由宿主托管，崩溃后会自动重启（1s / 2s / 4s / 8s / 16s，最多 5 次）。
连续崩溃 5 次会停止自动重启并标记为「已崩溃」，可在「插件管理 → 已安装」里手动重启。

- `context.log(level, message)` 写入 `plugins.log`
- 子进程的 `stderr` 会自动记录到日志
- 启停、重启、崩溃、退出码都会记录为 `system` / `error` 日志
- 插件管理页点 📄 可以直接查看日志、只看错误/警告、复制或打开日志文件

日志文件位置：

- 安装版：`~/Library/Application Support/omniaide-desktop/logs/plugins.log`（Windows 为 `%APPDATA%/omniaide-desktop/logs`）
- 开发版：`desktop/logs/plugins.log`

## 构建与分发

```bash
cd desktop
node scripts/build-plugins.mjs     # 构建所有 plugins/*/dist
node scripts/stage-plugins.mjs     # 仅 assistant 进入安装包，其余走插件市场
```

插件市场通过后端 `/api/plugins/marketplace` 分发，桌面端「插件管理 → 插件市场」安装/升级。
