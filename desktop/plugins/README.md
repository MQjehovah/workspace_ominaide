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

`permissions` 会被真正校验：`storage` / `notification` / `shell` / `screenshot` / `remote` / `clipboard`
只有声明后才可用。

```ts
export default {
  async activate(context) {
    context.registerCommand('getPanelData', async () => ({ title: '演示插件' }))
  },
  deactivate() {},
}
```

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
  id: 'open',
  title: '翻译助手',
  subtitle: '打开翻译面板',
  icon: '🌐',
  keywords: ['translate', '翻译'],
  command: 'open',
  args: { from: 'palette' },
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

## 构建与分发

```bash
cd desktop
node scripts/build-plugins.mjs     # 构建所有 plugins/*/dist
node scripts/stage-plugins.mjs     # 仅 assistant 进入安装包，其余走插件市场
```

插件市场通过后端 `/api/plugins/marketplace` 分发，桌面端「插件管理 → 插件市场」安装/升级。
