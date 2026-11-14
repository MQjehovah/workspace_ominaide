<template>
  <div class="overlay">
    <div class="card">
      <div class="card-hd">
        <div class="tabs">
          <button :class="{ active: tab === 'plugins' }" @click="tab = 'plugins'">已安装</button>
          <button :class="{ active: tab === 'marketplace' }" @click="tab = 'marketplace'; loadMarketplace()">插件市场</button>
          <button :class="{ active: tab === 'shortcuts' }" @click="tab = 'shortcuts'">快捷键</button>
        </div>
        <span v-if="appVersion" class="app-ver">v{{ appVersion }}</span>
        <button class="close-btn" @click="close">✕</button>
      </div>

      <div v-if="tab === 'plugins'" class="card-body">
        <div class="privacy-banner">
          <div>
            <div class="privacy-title">隐私与采集</div>
            <div class="privacy-desc">
              关闭开关会立即停止对应插件的后台进程。标记「会读取本地数据」的插件如下；
              剪贴板、前台窗口、邮件内容只在你启用时读取。
            </div>
          </div>
          <button class="privacy-pause" @click="pauseCollection">暂停全部采集</button>
        </div>
        <div v-for="p in plugins" :key="p.id" class="plugin-item">
          <div class="plugin-icon" :style="{ background: getColor(p.id) + '20' }">
            <div class="plugin-dot" :style="{ background: statusColor(p.id) }"></div>
          </div>
          <div class="plugin-info">
            <span class="plugin-name">
              {{ p.manifest?.displayName || p.id }}
              <span class="plugin-ver">v{{ p.manifest?.version || p.version || '—' }}</span>
              <span v-if="privacyNote(p.id)" class="privacy-tag" :title="privacyNote(p.id)">会读取本地数据</span>
            </span>
            <span class="plugin-desc">{{ p.manifest?.description || '' }}</span>
            <span class="plugin-status" :style="{ color: statusColor(p.id) }" :title="statusTitle(p.id)">
              {{ statusText(p.id) }}
            </span>
            <span class="plugin-perms" :class="{ danger: permHasDangerous(p.id), pending: permPendingCount(p.id) > 0 }">
              {{ permSummary(p.id) }}
            </span>
            <span v-if="privacyNote(p.id)" class="privacy-note">{{ privacyNote(p.id) }}</span>
          </div>
          <div class="plugin-actions">
            <button class="cfg-btn" title="权限" @click="openPermissions(p)">🛡</button>
            <button class="cfg-btn" title="查看日志" @click="openLogs(p)">📄</button>
            <button v-if="p.enabled" class="cfg-btn" title="重启插件" @click="restartPlugin(p)">↻</button>
            <button class="cfg-btn" title="配置" @click="openConfig(p)">⚙</button>
            <button v-if="!p.manifest?.builtin" class="uninstall-btn" title="卸载" @click="uninstallPlugin(p)">🗑</button>
            <label class="switch"><input type="checkbox" :checked="p.enabled" @change="togglePlugin(p)" /><span class="slider"></span></label>
          </div>
        </div>
        <button class="import-btn" @click="importPlugin">+ 导入插件</button>
      </div>

      <div v-if="tab === 'marketplace'" class="card-body">
        <div v-if="marketplaceLoading" style="text-align:center;padding:40px;color:#999">加载中...</div>
        <div v-else-if="marketplacePlugins.length === 0" style="text-align:center;padding:40px;color:#999">
          暂无可用插件<br>
          <span style="font-size:12px">请先在后端构建并上传插件</span>
        </div>
        <div v-for="p in marketplacePlugins" :key="p.id" class="plugin-item">
          <div class="plugin-icon" :style="{ background: getColor(p.id) + '20' }">
            <div class="plugin-dot" :style="{ background: isInstalled(p.id) ? '#28A745' : '#ccc' }"></div>
          </div>
          <div class="plugin-info">
            <span class="plugin-name">
              {{ p.displayName }}
              <span class="plugin-ver market">最新 v{{ p.version }}</span>
              <span v-if="installedVersion(p.id)" class="plugin-ver current">当前 v{{ installedVersion(p.id) }}</span>
            </span>
            <span class="plugin-desc">{{ p.description }}</span>
            <span class="plugin-perms">{{ marketPermSummary(p) }}</span>
          </div>
          <div class="plugin-actions">
            <button v-if="installingId === p.id" class="key-badge" disabled style="color:#999">安装中...</button>
            <button v-else-if="isInstalled(p.id) && hasUpdate(p)" class="key-badge install-btn" @click="installFromMarket(p)">更新到 v{{ p.version }}</button>
            <button v-else-if="isInstalled(p.id)" class="key-badge" disabled style="color:#28A745;border-color:#28A745">已安装</button>
            <button v-else class="key-badge install-btn" @click="installFromMarket(p)">安装</button>
          </div>
        </div>
        <div v-if="marketplaceError" style="text-align:center;padding:12px;color:#DC3545;font-size:12px">{{ marketplaceError }}</div>
      </div>

      <div v-if="tab === 'shortcuts'" class="card-body">
        <div class="section-title">系统快捷键</div>
        <div v-for="s in builtinShortcuts" :key="s.key" class="shortcut-item">
          <span>{{ s.label }}</span>
          <button class="key-badge" @click="recordBuiltin(s)">{{ editingBuiltin === s.key ? '按下快捷键...' : s.accelerator }}</button>
        </div>
        <div class="section-title" style="margin-top:16px">插件快捷键</div>
        <div v-for="(s, i) in customShortcuts" :key="i" class="shortcut-item">
          <div class="shortcut-info">
            <span class="shortcut-cmd">{{ s.pluginId }}: {{ s.command }}</span>
            <span v-if="s.label" class="shortcut-label">{{ s.label }}</span>
          </div>
          <button class="key-badge" @click="removeShortcut(s.accelerator)">✕ {{ s.accelerator }}</button>
        </div>
        <div v-if="showAddForm" class="add-form">
          <select v-model="newBinding.pluginId">
            <option value="">选择插件</option>
            <option v-for="p in plugins" :key="p.id" :value="p.id">{{ p.manifest?.displayName || p.id }}</option>
          </select>
          <select v-model="newBinding.command">
            <option value="">选择命令</option>
            <option v-for="c in getCommands(newBinding.pluginId)" :key="c" :value="c">{{ c }}</option>
          </select>
          <button class="key-badge record-btn" @click="recording = true; recordTarget = 'custom'">
            {{ recording && recordTarget === 'custom' ? '按下快捷键...' : (newBinding.accelerator || '点击设置快捷键') }}
          </button>
          <button class="btn primary sm" @click="saveShortcut">添加</button>
        </div>
        <button v-else class="add-btn" @click="showAddForm = true">+ 添加快捷键</button>
      </div>
    </div>

    <div v-if="logOpen" class="log-drawer">
      <div class="log-hd">
        <span class="log-title">{{ logPluginName }} · 日志</span>
        <span class="log-count">{{ filteredLogs.length }} 行</span>
        <label class="log-filter">
          <input v-model="logErrorsOnly" type="checkbox" /> 只看错误/警告
        </label>
        <button class="log-btn" @click="refreshLogs">刷新</button>
        <button class="log-btn" @click="copyLogs">复制</button>
        <button class="log-btn" @click="openLogFile">打开文件</button>
        <button class="log-close" @click="closeLogs">✕</button>
      </div>
      <div ref="logBody" class="log-body">
        <div v-if="!filteredLogs.length" class="log-empty">暂无日志</div>
        <div v-for="(l, i) in filteredLogs" :key="i" class="log-line" :class="'lv-' + l.level">
          <span class="log-time">{{ fmtLogTime(l.time) }}</span>
          <span class="log-level">{{ l.level.toUpperCase() }}</span>
          <span class="log-msg">{{ l.message }}</span>
        </div>
      </div>
      <div class="log-foot">
        日志文件：plugins.log · 自动刷新中 · 错误和崩溃信息会记录在这里
      </div>
    </div>

    <div v-if="permOpen" class="perm-drawer">
      <div class="perm-hd">
        <span class="perm-title">{{ permPluginName }} · 权限</span>
        <button class="log-btn" @click="restartFromPerm">重启插件</button>
        <button class="log-close" @click="permOpen = false">✕</button>
      </div>
      <div class="perm-body">
        <div v-if="permState?.legacy" class="perm-note">
          历史插件：升级前已安装，未声明的能力会在首次使用时自动授权。建议复核下面的权限。
        </div>
        <div v-else-if="permPendingCount(permPluginId) > 0" class="perm-note warn">
          有 {{ permPendingCount(permPluginId) }} 项敏感权限未授权，相关功能可能不可用。
        </div>
        <div v-if="!currentPerms.length" class="perm-empty">此插件未声明任何权限</div>
        <div v-for="perm in currentPerms" :key="perm" class="perm-row">
          <div class="perm-main">
            <div class="perm-name">
              {{ permLabel(perm) }}
              <span class="risk-chip" :class="permRisk(perm)">{{ permRiskText(perm) }}</span>
              <span v-if="permGranted(perm) && !permState?.declared?.includes(perm)" class="risk-chip extra">运行时授权</span>
            </div>
            <div class="perm-desc">{{ permDesc(perm) }}</div>
          </div>
          <label class="switch">
            <input type="checkbox" :checked="permGranted(perm)" @change="togglePermission(perm, ($event.target as HTMLInputElement).checked)" />
            <span class="slider"></span>
          </label>
        </div>
      </div>
      <div class="perm-foot">
        权限变更立即生效。正在运行的功能可能需要重启插件才能完全恢复。
      </div>
    </div>

    <PluginConfig v-if="configPluginId" :plugin-id="configPluginId" @close="configPluginId = ''" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, onMounted, onUnmounted } from 'vue'
import PluginConfig from './PluginConfig.vue'

const tab = ref('plugins')
const plugins = ref<any[]>([])
const marketplacePlugins = ref<any[]>([])
const marketplaceLoading = ref(false)
const marketplaceError = ref('')
const installingId = ref('')
const appVersion = ref('')
const builtinShortcuts = ref<any[]>([])
const customShortcuts = ref<any[]>([])
const showAddForm = ref(false)
const recording = ref(false)
const recordTarget = ref('')
const editingBuiltin = ref('')
const newBinding = ref<any>({ pluginId: '', command: '', accelerator: '' })
const configPluginId = ref('')
const statuses = ref<Record<string, any>>({})
const now = ref(Date.now())
const logOpen = ref(false)
const logPluginId = ref('')
const logPluginName = ref('')
const logEntries = ref<any[]>([])
const logErrorsOnly = ref(false)
const logBody = ref<HTMLElement | null>(null)
let logTimer: any = null
let statusTimer: any = null
let clockTimer: any = null

const permOpen = ref(false)
const permPluginId = ref('')
const permPluginName = ref('')
const permCatalog = ref<any[]>([])
const permStates = ref<Record<string, any>>({})

const pluginColors: Record<string, string> = { screenshot: '#28A745', 'clipboard-history': '#0078D4', todo: '#FF9800', player: '#E91E63', files: '#2196F3', notes: '#FF9800', calculator: '#9C27B0', everything: '#666', activity: '#8b5cf6', translator: '#0ea5e9', sysmonitor: '#10b981', pomodoro: '#ef4444' }
function getColor(id: string) { return pluginColors[id] || '#666' }

async function load() {
  plugins.value = await window.mqbox.plugin.listAll()
  builtinShortcuts.value = await window.mqbox.shortcut.getBuiltin()
  customShortcuts.value = await window.mqbox.shortcut.list()
  await Promise.all([loadStatuses(), loadPermissions()])
}

async function loadPermissions() {
  try {
    const result = await window.mqbox.plugin.permissions()
    permCatalog.value = result?.catalog || []
    const map: Record<string, any> = {}
    for (const state of result?.states || []) map[state.pluginId] = state
    permStates.value = map
  } catch {}
}

function permStateOf(id: string): any {
  return permStates.value[id] || null
}

function permCatalogEntry(id: string): any {
  return permCatalog.value.find(p => p.id === id) || null
}

function permLabel(id: string): string {
  return permCatalogEntry(id)?.label || id
}

function permDesc(id: string): string {
  return permCatalogEntry(id)?.description || ''
}

function permRisk(id: string): string {
  return permCatalogEntry(id)?.risk || 'normal'
}

function permRiskText(id: string): string {
  const risk = permRisk(id)
  return risk === 'dangerous' ? '高危' : risk === 'sensitive' ? '敏感' : '普通'
}

const RISK_ORDER: Record<string, number> = { dangerous: 0, sensitive: 1, normal: 2 }

function permListOf(id: string): string[] {
  const state = permStateOf(id)
  if (!state) return []
  return [...new Set([...(state.declared || []), ...(state.granted || [])])]
    .sort((a, b) => RISK_ORDER[permRisk(a)] - RISK_ORDER[permRisk(b)])
}

function permGranted(id: string): boolean {
  return !!permStateOf(permPluginId.value)?.granted?.includes(id)
}

function permPendingCount(pluginId: string): number {
  return permStateOf(pluginId)?.pending?.length || 0
}

function permHasDangerous(pluginId: string): boolean {
  return (permListOf(pluginId) || []).some(p => permRisk(p) === 'dangerous')
}

function permSummary(pluginId: string): string {
  const state = permStateOf(pluginId)
  if (!state) return ''
  const total = permListOf(pluginId).length
  if (!total) return '无需权限'
  const pending = permPendingCount(pluginId)
  const dangerous = permHasDangerous(pluginId) ? ' · 含高危' : ''
  return `${total} 项权限${dangerous}${pending ? ` · ${pending} 项待授权` : ''}`
}

function marketPermSummary(p: any): string {
  const ids = Array.isArray(p.permissions) ? p.permissions : []
  if (!ids.length) return '无需特殊权限'
  const risks = ids.map((id: string) => permRisk(id))
  const dangerous = risks.includes('dangerous') ? ' · 含高危' : risks.includes('sensitive') ? ' · 含敏感' : ''
  return `需要 ${ids.length} 项权限${dangerous}`
}

function openPermissions(p: any) {
  permPluginId.value = p.id
  permPluginName.value = p.manifest?.displayName || p.id
  permOpen.value = true
}

const currentPerms = computed(() => permListOf(permPluginId.value))
const permState = computed(() => permStateOf(permPluginId.value))

async function togglePermission(permission: string, enabled: boolean) {
  const result = await window.mqbox.plugin.setPermission(permPluginId.value, permission, enabled)
  if (!result?.success) alert(result?.error || '权限修改失败')
  await loadPermissions()
}

async function restartFromPerm() {
  const result = await window.mqbox.plugin.restart(permPluginId.value)
  if (!result?.success) alert(result?.error || '重启失败')
  await Promise.all([loadStatuses(), loadPermissions()])
}

async function loadStatuses() {
  try {
    const list = await window.mqbox.plugin.statuses()
    const map: Record<string, any> = {}
    for (const item of list) map[item.id] = item
    statuses.value = map
  } catch {}
}

function statusOf(id: string): any {
  return statuses.value[id] || null
}

function statusColor(id: string): string {
  const state = statusOf(id)?.state
  if (state === 'running') return '#28A745'
  if (state === 'crashed') return '#DC3545'
  if (state === 'restarting') return '#FF9800'
  if (state === 'starting') return '#0078D4'
  if (state === 'lazy') return '#8a94a8'
  return '#c0c4cc'
}

function formatUptime(startedAt?: number): string {
  if (!startedAt) return ''
  const seconds = Math.max(0, Math.floor((now.value - startedAt) / 1000))
  if (seconds < 60) return ` · ${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return ` · ${minutes}m`
  return ` · ${Math.floor(minutes / 60)}h${minutes % 60}m`
}

function statusText(id: string): string {
  const st = statusOf(id)
  if (!st) return ''
  switch (st.state) {
    case 'running':
      return `运行中${st.pid ? ` · pid ${st.pid}` : ''}${formatUptime(st.startedAt)}${st.restarts > 0 ? ` · 自动重启 ${st.restarts} 次` : ''}`
    case 'starting':
      return '启动中…'
    case 'restarting':
      return `异常退出，正在重启…${st.nextRetryAt ? '（' + Math.max(0, Math.ceil((st.nextRetryAt - now) / 1000)) + 's）' : ''}`
    case 'crashed':
      return st.restarts >= 5 ? '已崩溃 · 自动重启已停止' : '已崩溃'
    case 'stopped':
      return '已停止'
    case 'disabled':
      return '已停用'
    case 'lazy':
      return '按需启动'
    default:
      return ''
  }
}

function statusTitle(id: string): string {
  const st = statusOf(id)
  if (!st) return ''
  const parts: string[] = []
  if (st.lastExitCode !== undefined && st.lastExitCode !== null) parts.push(`退出码 ${st.lastExitCode}`)
  if (st.lastError) parts.push(st.lastError)
  if (st.nextRetryAt) parts.push(`计划重试：${new Date(st.nextRetryAt).toLocaleTimeString()}`)
  return parts.join('\n')
}

async function restartPlugin(p: any) {
  const result = await window.mqbox.plugin.restart(p.id)
  if (!result?.success) alert(result?.error || '重启失败')
  await loadStatuses()
}

async function openLogs(p: any) {
  logOpen.value = true
  logPluginId.value = p.id
  logPluginName.value = p.manifest?.displayName || p.id
  await refreshLogs()
  if (logTimer) clearInterval(logTimer)
  logTimer = setInterval(refreshLogs, 1500)
}

function closeLogs() {
  logOpen.value = false
  logPluginId.value = ''
  logEntries.value = []
  if (logTimer) clearInterval(logTimer)
  logTimer = null
}

async function refreshLogs() {
  if (!logOpen.value || !logPluginId.value) return
  const el = logBody.value
  const atBottom = !el || el.scrollHeight - el.scrollTop - el.clientHeight < 48
  try {
    logEntries.value = await window.mqbox.plugin.logs(logPluginId.value, 400)
  } catch { logEntries.value = [] }
  await nextTick()
  // Keep the user's scroll position unless they were already following the tail.
  if (atBottom && logBody.value) logBody.value.scrollTop = logBody.value.scrollHeight
}

const filteredLogs = computed(() => {
  if (!logErrorsOnly.value) return logEntries.value
  return logEntries.value.filter(l => ['error', 'fatal', 'stderr', 'warn'].includes(String(l.level).toLowerCase()))
})

function fmtLogTime(time: number): string {
  const d = new Date(time)
  const pad = (n: number, size = 2) => String(n).padStart(size, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`
}

async function copyLogs() {
  const text = filteredLogs.value
    .map(l => `[${fmtLogTime(l.time)}] [${l.level}] ${l.message}`)
    .join('\n')
  try { await window.mqbox.clipboard.writeText(text) } catch {}
}

function openLogFile() {
  window.mqbox.plugin.openLogFile()
}

function getCommands(pluginId: string): string[] {
  const cmds: Record<string, string[]> = { screenshot: ['region', 'fullscreen', 'open'], todo: ['add', 'done'], player: ['play', 'pause', 'next', 'prev'], 'clipboard-history': ['copy'], notes: ['create'], translator: ['open'], pomodoro: ['start', 'open'], sysmonitor: ['refresh'] }
  return cmds[pluginId] || ['run']
}

async function togglePlugin(p: any) {
  p.enabled = !p.enabled
  await window.mqbox.plugin.setEnabled(p.id, p.enabled)
  await loadStatuses()
}

const PRIVACY_NOTES: Record<string, string> = {
  activity: '读取前台应用与窗口标题，用于活动时间线',
  'clipboard-history': '读取剪贴板文本，仅保存在本机历史中',
  mail: '读取邮箱内容；收取与分析已由后端完成',
  remote: '被控时共享屏幕、键鼠与剪贴板',
  screenshot: '手动截图时读取屏幕画面',
  everything: '搜索本机文件名与路径',
}

function privacyNote(id: string): string {
  return PRIVACY_NOTES[id] || ''
}

async function pauseCollection() {
  const ids = ['activity', 'clipboard-history', 'mail']
  for (const id of ids) {
    const p = plugins.value.find(x => x.id === id)
    if (p?.enabled) {
      p.enabled = false
      await window.mqbox.plugin.setEnabled(id, false)
    }
  }
}

async function importPlugin() {
  const result = await window.mqbox.plugin.importPlugin()
  if (result?.success) {
    await load()
  }
}

async function loadMarketplace() {
  marketplaceLoading.value = true
  marketplaceError.value = ''
  try {
    marketplacePlugins.value = await window.mqbox.plugin.listMarketplace()
    if (marketplacePlugins.value.length === 0) {
      marketplaceError.value = '后端服务未运行或插件市场为空'
    }
  } catch { marketplacePlugins.value = []; marketplaceError.value = '无法加载插件市场' }
  marketplaceLoading.value = false
}

function isInstalled(id: string) {
  return plugins.value.some(p => p.id === id)
}

function installedVersion(id: string): string {
  const plugin = plugins.value.find(p => p.id === id)
  return plugin?.manifest?.version || plugin?.version || ''
}

function versionParts(value?: string): number[] {
  return String(value || '0').split(/[.\-+]/).map(part => parseInt(part, 10) || 0)
}

function hasUpdate(p: any): boolean {
  const installed = plugins.value.find(x => x.id === p.id)
  if (!installed) return false
  const current = versionParts(installed.manifest?.version)
  const next = versionParts(p.version)
  const size = Math.max(current.length, next.length)
  for (let i = 0; i < size; i++) {
    const a = current[i] || 0
    const b = next[i] || 0
    if (b > a) return true
    if (b < a) return false
  }
  return false
}

async function installFromMarket(p: any) {
  installingId.value = p.id
  marketplaceError.value = ''
  try {
    const result = await window.mqbox.plugin.installFromMarket(p.id)
    if (result?.success) {
      await load()
    } else {
      marketplaceError.value = result?.error || '安装失败'
    }
  } catch (e: any) {
    marketplaceError.value = e?.message || '安装失败'
  }
  installingId.value = ''
}

function openConfig(p: any) {
  configPluginId.value = p.id
}

async function uninstallPlugin(p: any) {
  if (!confirm(`确定要卸载插件 "${p.manifest?.displayName || p.id}" 吗？`)) return
  const result = await window.mqbox.plugin.uninstall(p.id)
  if (result?.success) {
    await load()
  } else {
    alert(result?.error || '卸载失败')
  }
}

window.mqbox?.plugin?.onUpdated(() => load())

async function removeShortcut(accelerator: string) {
  await window.mqbox.shortcut.remove(accelerator)
  customShortcuts.value = await window.mqbox.shortcut.list()
}

async function saveShortcut() {
  if (!newBinding.value.pluginId || !newBinding.value.command || !newBinding.value.accelerator) return
  await window.mqbox.shortcut.add(newBinding.value)
  customShortcuts.value = await window.mqbox.shortcut.list()
  showAddForm.value = false
  newBinding.value = { pluginId: '', command: '', accelerator: '' }
}

function recordBuiltin(s: any) {
  editingBuiltin.value = s.key
  recording.value = true
  recordTarget.value = 'builtin'
}

async function onKeydown(e: KeyboardEvent) {
  if (!recording.value) return
  e.preventDefault()
  const mods: string[] = []
  if (e.ctrlKey) mods.push('Ctrl')
  if (e.altKey) mods.push('Alt')
  if (e.shiftKey) mods.push('Shift')
  if (e.metaKey) mods.push('Cmd')
  const key = e.key === ' ' ? 'Space' : e.key.length === 1 ? e.key.toUpperCase() : e.key
  const acc = [...mods, key].join('+')
  if (recordTarget.value === 'builtin') {
    await window.mqbox.shortcut.updateBuiltin(editingBuiltin.value, acc)
    builtinShortcuts.value = await window.mqbox.shortcut.getBuiltin()
    editingBuiltin.value = ''
  } else {
    newBinding.value.accelerator = acc
  }
  recording.value = false
}

function close() { window.close() }

onMounted(() => {
  load()
  document.addEventListener('keydown', onKeydown)
  clockTimer = setInterval(() => { now.value = Date.now() }, 1000)
  statusTimer = setInterval(() => { loadStatuses() }, 3000)
})
onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  if (clockTimer) clearInterval(clockTimer)
  if (statusTimer) clearInterval(statusTimer)
  if (logTimer) clearInterval(logTimer)
})
</script>

<style scoped>
.overlay { height:100vh; display:flex; flex-direction:column; background:#fff; }
.card { flex:1; display:flex; flex-direction:column; overflow:hidden; position:relative; }
.card-hd { display:flex; align-items:center; padding:12px 16px; border-bottom:1px solid #e8e8e8; }
.tabs { display:flex; gap:4px; flex:1; justify-content:center;  -webkit-app-region:drag; }
.tabs button { padding:4px 16px; border-radius:6px; border:none; background:transparent; cursor:pointer; font-size:13px; color:#666; -webkit-app-region:no-drag; }
.tabs button.active { background:#e8f4fd; color:#0078D4; font-weight:500; }
.close-btn { border:none; background:transparent; cursor:pointer; color:#999; font-size:16px; -webkit-app-region:no-drag; }
.card-body { flex:1; overflow-y:auto; padding:12px 16px; }
.plugin-item { display:flex; align-items:center; gap:10px; padding:10px 0; border-bottom:1px solid #f5f5f5; }
.plugin-icon { width:32px; height:32px; border-radius:8px; display:flex; align-items:center; justify-content:center; position:relative; }
.plugin-dot { width:8px; height:8px; border-radius:4px; }
.plugin-info { flex:1; }
.plugin-name { font-size:13px; font-weight:500; display:block; }
.plugin-ver { display:inline-block; margin-left:6px; padding:0 5px; border-radius:4px; background:#eef2f7; color:#6b7280; font-size:10px; font-weight:500; line-height:16px; vertical-align:middle; }
.plugin-ver.market { background:#eaf3ff; color:#2f6fbf; }
.plugin-ver.current { background:#eefaf1; color:#1f8b4c; }
.app-ver { flex-shrink:0; margin-right:8px; font-size:11px; color:#9aa3b2; -webkit-app-region:no-drag; }
.privacy-banner { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; background:#f5f9ff; border:1px solid #d9e9ff; border-radius:10px; padding:10px 12px; margin-bottom:10px; }
.privacy-title { font-size:13px; font-weight:600; color:#1a1a2e; }
.privacy-desc { font-size:11px; color:#7a8290; line-height:1.6; margin-top:4px; }
.privacy-pause { flex-shrink:0; border:1px solid #b9d4ff; background:#fff; color:#2f6fbf; border-radius:6px; padding:5px 8px; font-size:11px; cursor:pointer; }
.privacy-pause:hover { background:#eaf3ff; }
.privacy-tag { display:inline-block; margin-left:6px; padding:1px 5px; border-radius:4px; background:#fff1f0; color:#c45656; font-size:10px; font-weight:500; }
.privacy-note { font-size:10px; color:#a0a4ad; margin-top:2px; }
.plugin-desc { font-size:11px; color:#999; }
.plugin-status { display:block; font-size:10.5px; margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.plugin-perms { display:block; font-size:10px; color:#8a94a8; margin-top:2px; }
.plugin-perms.danger { color:#c45656; }
.plugin-perms.pending { color:#b26a00; }

/* Permission drawer */
.perm-drawer { position:absolute; inset:0; background:#fff; display:flex; flex-direction:column; z-index:21; }
.perm-hd { display:flex; align-items:center; gap:8px; padding:12px 16px; border-bottom:1px solid #eceef3; }
.perm-title { flex:1; font-size:13px; font-weight:600; color:#1f2430; }
.perm-body { flex:1; overflow-y:auto; padding:12px 16px; }
.perm-note { background:#fff8e6; border:1px solid #f3dfae; color:#8a6100; font-size:11px; line-height:1.6; border-radius:8px; padding:8px 10px; margin-bottom:10px; }
.perm-note.warn { background:#fff3f2; border-color:#f5c7c3; color:#a8322a; }
.perm-empty { color:#9aa3b2; font-size:12px; text-align:center; padding:24px 0; }
.perm-row { display:flex; align-items:flex-start; gap:12px; padding:10px 0; border-bottom:1px solid #f4f5f8; }
.perm-main { flex:1; min-width:0; }
.perm-name { display:flex; align-items:center; gap:6px; font-size:12.5px; font-weight:600; color:#2f3542; }
.perm-desc { font-size:11px; color:#8a94a8; line-height:1.5; margin-top:3px; }
.risk-chip { display:inline-block; padding:1px 6px; border-radius:4px; font-size:9.5px; font-weight:600; background:#eef2f7; color:#6b7280; }
.risk-chip.sensitive { background:#fff4e5; color:#b26a00; }
.risk-chip.dangerous { background:#fdecea; color:#c0392b; }
.risk-chip.extra { background:#eaf3ff; color:#2f6fbf; }
.perm-foot { padding:8px 16px; border-top:1px solid #eceef3; font-size:10.5px; color:#9aa3b2; }

/* Log drawer */
.log-drawer { position:absolute; inset:0; background:#1e1f26; display:flex; flex-direction:column; z-index:20; }
.log-hd { display:flex; align-items:center; gap:8px; padding:10px 12px; border-bottom:1px solid #2d2f3a; color:#d8dae2; }
.log-title { font-size:12.5px; font-weight:600; flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.log-count { font-size:10.5px; color:#8b8f9e; }
.log-filter { display:flex; align-items:center; gap:4px; font-size:11px; color:#aab0c0; cursor:pointer; }
.log-btn, .log-close { border:1px solid #3a3d4a; background:#2a2c36; color:#c9cdd8; border-radius:5px; padding:3px 8px; font-size:11px; cursor:pointer; }
.log-btn:hover, .log-close:hover { background:#353846; }
.log-close { border-color:transparent; background:transparent; font-size:13px; }
.log-body { flex:1; overflow-y:auto; padding:8px 10px; font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:11px; line-height:1.55; }
.log-empty { color:#6c7080; padding:20px; text-align:center; }
.log-line { display:flex; gap:8px; padding:1px 0; color:#c3c7d1; white-space:pre-wrap; word-break:break-word; }
.log-time { color:#6f7485; flex-shrink:0; }
.log-level { flex-shrink:0; width:56px; color:#8fa1d8; }
.log-msg { flex:1; min-width:0; }
.log-line.lv-error .log-level, .log-line.lv-error .log-msg { color:#ff6b6b; }
.log-line.lv-fatal .log-level, .log-line.lv-fatal .log-msg { color:#ff4d4f; }
.log-line.lv-warn .log-level { color:#ffb454; }
.log-line.lv-stderr .log-level, .log-line.lv-stderr .log-msg { color:#c792ea; }
.log-line.lv-system .log-level { color:#63d2a5; }
.log-foot { padding:6px 12px; border-top:1px solid #2d2f3a; color:#6f7485; font-size:10px; }
.plugin-actions { display:flex; align-items:center; gap:8px; }
.cfg-btn { border:none; background:transparent; cursor:pointer; font-size:16px; color:#999; padding:2px 4px; border-radius:4px; }
.cfg-btn:hover { background:#f0f0f0; color:#333; }
.uninstall-btn { border:none; background:transparent; cursor:pointer; font-size:15px; color:#DC3545; padding:2px 4px; border-radius:4px; opacity:0.4; }
.uninstall-btn:hover { opacity:1; background:#fff0f0; }
.switch { position:relative; width:36px; height:20px; flex-shrink:0; }
.switch input { opacity:0; width:0; height:0; }
.slider { position:absolute; cursor:pointer; inset:0; background:#ddd; border-radius:20px; transition:0.2s; }
.slider::before { content:''; position:absolute; height:16px; width:16px; left:2px; bottom:2px; background:#fff; border-radius:50%; transition:0.2s; }
.switch input:checked + .slider { background:#0078D4; }
.switch input:checked + .slider::before { transform:translateX(16px); }
.import-btn { width:100%; padding:10px; border:1px dashed #d0d0d0; border-radius:8px; background:transparent; cursor:pointer; font-size:13px; color:#999; margin-top:12px; }
.import-btn:hover { border-color:#0078D4; color:#0078D4; }
.section-title { font-size:11px; font-weight:600; color:#999; text-transform:uppercase; margin-bottom:8px; }
.shortcut-item { display:flex; justify-content:space-between; align-items:center; padding:8px 0; font-size:13px; }
.shortcut-info { }
.shortcut-cmd { font-size:13px; display:block; }
.shortcut-label { font-size:11px; color:#999; }
.key-badge { padding:4px 10px; border-radius:6px; border:1px solid #e0e0e0; background:#f5f5f5; font-size:12px; cursor:pointer; font-family:monospace; }
.key-badge:hover { border-color:#0078D4; }
.record-btn { background:#fff8e1; border-color:#FF9800; color:#FF9800; }
.add-form { display:flex; flex-direction:column; gap:8px; padding:12px; background:#f8f9fa; border-radius:8px; margin-top:8px; }
.add-form select, .add-form input { padding:6px 10px; border:1px solid #e0e0e0; border-radius:6px; font-size:12px; }
.add-btn { padding:8px; border:1px dashed #e0e0e0; border-radius:8px; background:transparent; cursor:pointer; font-size:13px; color:#999; width:100%; margin-top:8px; }
.add-btn:hover { border-color:#0078D4; color:#0078D4; }
.btn { padding:6px 16px; border-radius:6px; border:1px solid #e0e0e0; background:#fff; cursor:pointer; font-size:12px; }
.btn.primary { background:#0078D4; color:#fff; border-color:#0078D4; }
.btn.sm { padding:4px 12px; font-size:11px; }
</style>
