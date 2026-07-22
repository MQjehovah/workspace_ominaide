<script setup lang="ts">
import { ref, onMounted, onUnmounted, defineAsyncComponent } from 'vue'

const pluginComponents: Record<string, any> = {
  'assistant': defineAsyncComponent(() => import('@plugins/assistant/src/Panel.vue')),
  'calculator': defineAsyncComponent(() => import('@plugins/calculator/src/Panel.vue')),
  'clipboard-history': defineAsyncComponent(() => import('@plugins/clipboard-history/src/Panel.vue')),
  'files': defineAsyncComponent(() => import('@plugins/files/src/Panel.vue')),
  'notes': defineAsyncComponent(() => import('@plugins/notes/src/Panel.vue')),
  'player': defineAsyncComponent(() => import('@plugins/player/src/Panel.vue')),
  'quick-notes': defineAsyncComponent(() => import('@plugins/quick-notes/src/Panel.vue')),
  'remote': defineAsyncComponent(() => import('@plugins/remote/src/Panel.vue')),
  'rss': defineAsyncComponent(() => import('@plugins/rss/src/Panel.vue')),
  'schedule': defineAsyncComponent(() => import('@plugins/schedule/src/Panel.vue')),
  'screenshot': defineAsyncComponent(() => import('@plugins/screenshot/src/Panel.vue')),
  'todo': defineAsyncComponent(() => import('@plugins/todo/src/Panel.vue')),
}

const pluginList = ref<any[]>([])
const panels = ref<any[]>([])
const isLoading = ref(false)
const panelData = ref<Record<string, any>>({})
const showUserMenu = ref(false)
const notifCount = ref(0)
const notifs = ref<any[]>([])
let notifTimer: any = null

const pluginColors: Record<string, string> = {
  screenshot: '#28A745', 'quick-notes': '#DC3545', 'clipboard-history': '#0078D4',
  todo: '#FF9800', player: '#E91E63', calculator: '#666', files: '#2196F3', notes: '#FF9800',
}

async function loadPlugins() {
  isLoading.value = true
  try {
    pluginList.value = await window.mqbox?.plugin.list() || []
    panels.value = await window.mqbox?.plugin.getPanels() || []
    for (const panel of panels.value) {
      try {
        const data = await window.mqbox?.plugin.execute(panel.pluginId, 'getPanelData', {})
        if (data !== undefined && data !== null) panelData.value[panel.pluginId] = data
      } catch {}
    }
  } catch {}
  isLoading.value = false
}

function getComponent(pluginId: string) { return pluginComponents[pluginId] || null }

function openPluginPage(pluginId: string) { window.mqbox?.window.openPage(pluginId) }
function openSearch() { window.mqbox?.window.openSearch() }
function openManager() { showUserMenu.value = false; window.mqbox?.window.openPluginManager() }
function handleClose() { window.mqbox?.window.hide() }

async function logout() {
  await window.mqbox?.config.set('token', '')
  await window.mqbox?.config.set('refresh_token', '')
  window.mqbox?.window.openMain()
}

async function executeCommand(pluginId: string, command: string, args?: unknown) {
  const result = await window.mqbox?.plugin.execute(pluginId, command, args || {})
  panelData.value[pluginId] = await window.mqbox?.plugin.execute(pluginId, 'getPanelData', {})
  return result
}

async function refreshPanel(pluginId: string) {
  panelData.value[pluginId] = await window.mqbox?.plugin.execute(pluginId, 'getPanelData', {})
}

async function fetchNotifs() {
  try { const r = await window.mqbox?.api.get('/notifications?unread=true&limit=5'); notifs.value = r || [] } catch {}
}
async function fetchNotifCount() {
  try { const r = await window.mqbox?.api.get('/notifications/unread-count'); notifCount.value = r?.count || 0 } catch {}
}
async function markRead(n: any) {
  try { await window.mqbox?.api.put(`/notifications/${n.id}/read`); n.read = true; notifCount.value = Math.max(0, notifCount.value - 1) } catch {}
}
function openNotifPage() { window.mqbox?.window.openPage('notifications') }
function fmt(iso: string) {
  if (!iso) return ''; const d = new Date(iso); const now = new Date(); const diff = now.getTime() - d.getTime()
  if (diff < 60000) return '刚刚'; if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前'
  if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前'
  return (d.getMonth()+1)+'/'+d.getDate()+' '+d.getHours()+':'+String(d.getMinutes()).padStart(2,'0')
}

onMounted(() => {
  loadPlugins()
  fetchNotifCount()
  notifTimer = setInterval(fetchNotifCount, 15000)
  window.mqbox?.clipboard?.onUpdated(() => refreshPanel('clipboard-history'))
  window.mqbox?.player?.onUpdated(() => refreshPanel('player'))
  window.mqbox?.todo?.onUpdated(() => refreshPanel('todo'))
  window.mqbox?.plugin?.onUpdated(() => loadPlugins())
})

onUnmounted(() => { if (notifTimer) clearInterval(notifTimer) })
</script>

<template>
  <div class="main-panel">
    <!-- Title Bar -->
    <div class="title-bar">
      <span class="title-text">OmniAide</span>
      <div class="title-actions">
        <button class="title-btn" @click="handleClose">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </button>
      </div>
    </div>

    <!-- User Area -->
    <div class="user-area">
      <div class="user-avatar" @click="showUserMenu = !showUserMenu">
        <span>U</span>
      </div>
      <div class="user-info" @click="showUserMenu = !showUserMenu">
        <span class="user-name">OmniAide</span>
        <div class="user-status">
          <div class="status-dot"></div>
          <span>在线</span>
        </div>
      </div>
      <el-dropdown trigger="click" @visible-change="fetchNotifs">
        <button class="bell-btn"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg><span v-if="notifCount > 0" class="bell-dot">{{ notifCount }}</span></button>
        <template #dropdown>
          <el-dropdown-menu>
            <div v-for="n in notifs.slice(0,5)" :key="n.id" class="notif-item" @click="markRead(n)">
              <div style="font-size:12px;font-weight:500;color:#333;white-space:normal">{{ n.title }}</div>
              <div style="font-size:10px;color:#909399">{{ fmt(n.created_at) }}</div>
            </div>
            <el-dropdown-item divided @click="openNotifPage">查看全部</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <!-- User Menu -->
      <div v-if="showUserMenu" class="user-menu" @click.stop>
        <button class="menu-item" @click="showUserMenu = false; openSearch()">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg> 搜索
        </button>
        <button class="menu-item" @click="openManager()">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg> 管理
        </button>
        <button class="menu-item danger" @click="showUserMenu = false; logout()">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" x2="9" y1="12" y2="12"/></svg> 退出登录
        </button>
      </div>
    </div>

    <!-- Plugin Panels -->
    <div class="panels-area">
      <div v-if="isLoading" class="loading-state">加载中...</div>
      <div v-else class="panels-list">
        <template v-for="panel in panels" :key="panel.id">
          <component
            v-if="getComponent(panel.pluginId) && panelData[panel.pluginId]"
            :is="getComponent(panel.pluginId)"
            :data="panelData[panel.pluginId]"
            :execute="(cmd: string, args?: any) => executeCommand(panel.pluginId, cmd, args)"
            :open-page="() => openPluginPage(panel.pluginId)"
            :refresh="() => refreshPanel(panel.pluginId)"
          />
        </template>
      </div>
    </div>

    <!-- Resize Handle -->
    <div class="resize-handle"></div>
  </div>
</template>

<style scoped>
.bell-btn { position:relative; width:32px;height:32px;border:none;border-radius:6px;background:transparent;color:#868e96;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.bell-btn:hover { background:#f1f3f5;color:#495057; }
.bell-dot { position:absolute;top:1px;right:2px;width:16px;height:14px;border-radius:7px;background:#e91e63;color:#fff;font-size:10px;line-height:14px;text-align:center;font-weight:700; }
.notif-item { padding:8px 12px;cursor:pointer;border-bottom:1px solid #f5f5f5;min-width:220px; }
.notif-item:hover { background:#f8f9fa; }
</style>

<style scoped>
.main-panel { width:300px; height:600px; border-radius:12px; background:#fff; box-shadow:0 4px 20px rgba(0,0,0,0.18); border:1px solid #e0e0e0; display:flex; flex-direction:column; position:relative; overflow:hidden; }

.title-bar { height:32px; background:#f5f5f5; display:flex; align-items:center; justify-content:space-between; padding:0 12px; border-bottom:1px solid #e0e0e0; -webkit-app-region:drag; }
.title-text { font-size:13px; color:#666; font-weight:500; }
.title-actions { display:flex; gap:8px; -webkit-app-region:no-drag; }
.title-btn { width:24px; height:24px; border-radius:12px; background:#fff; border:1px solid #e0e0e0; display:flex; align-items:center; justify-content:center; cursor:pointer; color:#666; }
.title-btn:hover { background:#ebebeb; }

.user-area { height:56px; display:flex; align-items:center; gap:12px; padding:0 16px; position:relative; }
.user-avatar { width:40px; height:40px; border-radius:20px; background:#0078D4; display:flex; align-items:center; justify-content:center; cursor:pointer; }
.user-avatar span { color:#fff; font-size:16px; font-weight:600; }
.user-info { flex:1; cursor:pointer; }
.user-name { font-size:14px; color:#1e1e1e; font-weight:600; display:block; }
.user-status { display:flex; align-items:center; gap:4px; }
.status-dot { width:8px; height:8px; border-radius:4px; background:#28A745; }
.user-status span { font-size:12px; color:#28A745; }
.settings-btn { width:32px; height:32px; display:flex; align-items:center; justify-content:center; border-radius:6px; background:transparent; cursor:pointer; color:#666; border:none; }
.settings-btn:hover { background:#f5f5f5; }

.user-menu { position:absolute; top:56px; left:12px; width:160px; background:#fff; border-radius:10px; box-shadow:0 4px 16px rgba(0,0,0,0.15); border:1px solid #e0e0e0; padding:4px 0; z-index:50; }
.menu-item { width:100%; display:flex; align-items:center; gap:8px; padding:8px 12px; font-size:13px; color:#333; background:none; border:none; cursor:pointer; }
.menu-item:hover { background:#f5f5f5; }
.menu-item.danger { color:#E53935; }
.menu-item.danger svg { color:#E53935; }
.menu-divider { height:1px; background:#e0e0e0; margin:0 8px; }

.panels-area { flex:1; min-height:0; overflow-y:auto; padding:8px 12px; scrollbar-width:none; }
.panels-area::-webkit-scrollbar { display:none; }
.panels-list { display:flex; flex-direction:column; gap:6px; }
.loading-state { display:flex; align-items:center; justify-content:center; height:100px; color:#666; font-size:14px; }

.resize-handle { position:absolute; right:0; bottom:0; width:16px; height:16px; cursor:se-resize; -webkit-app-region:no-drag; }
</style>
