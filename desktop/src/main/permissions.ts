/**
 * Plugin permission catalogue.
 *
 * Every capability a plugin can reach goes through a named bridge method in
 * host.ts. The mapping below is the single source of truth used to enforce a
 * plugin's declared/approved permissions, including for `context.signal()`
 * calls which are just raw bridge RPCs.
 */

export type PermissionRisk = 'normal' | 'sensitive' | 'dangerous'

export type PermissionId =
  | 'storage'
  | 'notification'
  | 'api'
  | 'config'
  | 'channel'
  | 'clipboard:read'
  | 'clipboard:write'
  | 'files:read'
  | 'files:write'
  | 'shell:open'
  | 'shell:exec'
  | 'pty'
  | 'screenshot'
  | 'remote'
  | 'selection'
  | 'events'
  | 'schedule'
  | 'shortcut'
  | 'menu'
  | 'tray'
  | 'palette'
  | 'windows'

export interface PermissionInfo {
  id: PermissionId
  label: string
  description: string
  risk: PermissionRisk
}

export const PERMISSIONS: Record<PermissionId, PermissionInfo> = {
  storage: {
    id: 'storage',
    label: '本地存储',
    description: '在本机保存插件自己的数据（配置、历史记录等）',
    risk: 'normal',
  },
  notification: {
    id: 'notification',
    label: '系统通知',
    description: '发送桌面通知',
    risk: 'normal',
  },
  api: {
    id: 'api',
    label: '访问 OmniAide 后端',
    description: '以你的账号身份读写后端数据（待办、笔记、邮件、会议等）',
    risk: 'sensitive',
  },
  config: {
    id: 'config',
    label: '读取应用配置',
    description: '读取应用配置，可能包含登录令牌等敏感信息',
    risk: 'dangerous',
  },
  channel: {
    id: 'channel',
    label: '后端长连接',
    description: '订阅/发送后端 WebSocket 通道消息',
    risk: 'sensitive',
  },
  'clipboard:read': {
    id: 'clipboard:read',
    label: '读取剪贴板',
    description: '读取你复制到剪贴板的文字',
    risk: 'sensitive',
  },
  'clipboard:write': {
    id: 'clipboard:write',
    label: '写入剪贴板',
    description: '替换剪贴板内容',
    risk: 'normal',
  },
  'files:read': {
    id: 'files:read',
    label: '读取文件',
    description: '通过文件选择框读取本地文件/目录',
    risk: 'normal',
  },
  'files:write': {
    id: 'files:write',
    label: '写入文件',
    description: '修改或删除本地文件',
    risk: 'sensitive',
  },
  'shell:open': {
    id: 'shell:open',
    label: '打开链接/文件',
    description: '用系统默认应用打开网址或文件',
    risk: 'normal',
  },
  'shell:exec': {
    id: 'shell:exec',
    label: '执行系统命令',
    description: '启动任意程序或脚本（高危）',
    risk: 'dangerous',
  },
  pty: {
    id: 'pty',
    label: '终端会话',
    description: '启动交互式终端并执行命令（高危）',
    risk: 'dangerous',
  },
  screenshot: {
    id: 'screenshot',
    label: '截屏',
    description: '截取屏幕内容、读取截图历史',
    risk: 'sensitive',
  },
  remote: {
    id: 'remote',
    label: '远程控制',
    description: '共享屏幕、键鼠与剪贴板（高危）',
    risk: 'dangerous',
  },
  selection: {
    id: 'selection',
    label: '读取选中文本',
    description: '读取你在其他应用中选中的文字',
    risk: 'sensitive',
  },
  events: {
    id: 'events',
    label: '接收系统事件',
    description: '订阅剪贴板、文件变化、电源、网络、显示器与空闲状态',
    risk: 'sensitive',
  },
  schedule: {
    id: 'schedule',
    label: '定时任务',
    description: '在应用运行时按间隔或 cron 定时执行任务',
    risk: 'normal',
  },
  shortcut: {
    id: 'shortcut',
    label: '全局快捷键',
    description: '注册系统级快捷键',
    risk: 'sensitive',
  },
  menu: {
    id: 'menu',
    label: '右键菜单',
    description: '弹出原生上下文菜单',
    risk: 'normal',
  },
  tray: {
    id: 'tray',
    label: '托盘菜单',
    description: '向系统托盘菜单添加命令',
    risk: 'normal',
  },
  palette: {
    id: 'palette',
    label: '命令面板',
    description: '向全局搜索/命令面板添加命令',
    risk: 'normal',
  },
  windows: {
    id: 'windows',
    label: '创建窗口',
    description: '创建和控制插件窗口',
    risk: 'normal',
  },
}

/** Older, coarser permission names kept working through expansion. */
const ALIASES: Record<string, PermissionId[]> = {
  clipboard: ['clipboard:read', 'clipboard:write'],
  shell: ['shell:open'],
  files: ['files:read'],
}

const ALL_IDS = new Set<string>(Object.keys(PERMISSIONS))

export function expandPermissions(list: string[] | undefined): PermissionId[] {
  const out = new Set<PermissionId>()
  for (const raw of list || []) {
    const name = String(raw || '').trim()
    if (!name) continue
    for (const id of ALIASES[name] || []) out.add(id)
    if (ALL_IDS.has(name)) out.add(name as PermissionId)
  }
  return [...out]
}

export function permissionInfo(id: PermissionId): PermissionInfo {
  return PERMISSIONS[id]
}

export function riskOf(id: PermissionId): PermissionRisk {
  return PERMISSIONS[id]?.risk || 'normal'
}

export function isHighRisk(id: PermissionId): boolean {
  const risk = riskOf(id)
  return risk === 'sensitive' || risk === 'dangerous'
}

/**
 * Bridge RPC method -> required permissions. An empty list means the method is
 * safe for any plugin (UI refresh, logging, opening its own page, etc.).
 */
const BRIDGE_PERMISSIONS: Record<string, PermissionId[]> = {
  'api:get': ['api'],
  'api:post': ['api'],
  'api:put': ['api'],
  'api:delete': ['api'],
  'channel:subscribe': ['channel'],
  'channel:unsubscribe': ['channel'],
  'channel:send': ['channel'],
  'channel:status': ['channel'],
  'config:get': ['config'],
  'storage:get': ['storage'],
  'storage:set': ['storage'],
  'notification:show': ['notification'],
  'screenshot:start': ['screenshot'],
  'screenshot:capture-fullscreen': ['screenshot'],
  'screenshot:show-editor': ['screenshot'],
  'screenshot:get-history': ['screenshot'],
  'screenshot:clear-history': ['screenshot'],
  'screenshot:delete-history': ['screenshot'],
  'remote:get-sources': ['remote'],
  'remote:screen-size': ['remote'],
  'remote:get-all-displays': ['remote'],
  'remote:open-connection': ['remote'],
  'remote:ws-connect': ['remote'],
  'remote:ws-send': ['remote'],
  'remote:ws-disconnect': ['remote'],
  'remote:inject-input': ['remote'],
  'remote:power': ['remote'],
  'dialog:showOpenDialog': ['files:read'],
  'shell:openPath': ['shell:open'],
  'shell:openExternal': ['shell:open'],
  'shell:showItemInFolder': ['shell:open'],
  'shell:exec': ['shell:exec'],
  'pty:create': ['pty'],
  'pty:write': ['pty'],
  'pty:read': ['pty'],
  'pty:kill': ['pty'],
  'clipboard:readText': ['clipboard:read'],
  'clipboard:writeText': ['clipboard:write'],
  'globalShortcut:register': ['shortcut'],
  'globalShortcut:unregister': ['shortcut'],
  'globalShortcut:unregisterAll': ['shortcut'],
  'menu:show': ['menu'],
  'tray:set': ['tray'],
  'palette:register': ['palette'],
  'selection:register': ['selection'],
  'event:subscribe': ['events'],
  'event:unsubscribe': ['events'],
  'event:emit': ['events'],
  'schedule:register': ['schedule'],
  'schedule:unregister': ['schedule'],
  'schedule:list': ['schedule'],
  'BrowserWindow:create': ['windows'],
  'BrowserWindow:loadURL': ['windows'],
  'BrowserWindow:show': ['windows'],
  'BrowserWindow:focus': ['windows'],
  'BrowserWindow:hide': ['windows'],
  'BrowserWindow:close': ['windows'],
  'BrowserWindow:setAlwaysOnTop': ['windows'],
  'BrowserWindow:setSkipTaskbar': ['windows'],
  // Intentionally unrestricted:
  // log:write, openPage, panel:updated
}

export function requiredPermissionsForBridge(method: string): PermissionId[] {
  return BRIDGE_PERMISSIONS[method] || []
}

const RISK_LABEL: Record<PermissionRisk, string> = {
  normal: '普通',
  sensitive: '敏感',
  dangerous: '高危',
}

export function describePermissions(ids: PermissionId[]): string {
  const order: PermissionRisk[] = ['dangerous', 'sensitive', 'normal']
  const sorted = [...new Set(ids)].sort(
    (a, b) => order.indexOf(riskOf(a)) - order.indexOf(riskOf(b)),
  )
  return sorted
    .map((id) => `• ${PERMISSIONS[id].label}（${RISK_LABEL[riskOf(id)]}）— ${PERMISSIONS[id].description}`)
    .join('\n')
}

export function riskSummary(ids: PermissionId[]): PermissionRisk {
  if (ids.some((id) => riskOf(id) === 'dangerous')) return 'dangerous'
  if (ids.some((id) => riskOf(id) === 'sensitive')) return 'sensitive'
  return 'normal'
}

export const RISK_TEXT = RISK_LABEL
