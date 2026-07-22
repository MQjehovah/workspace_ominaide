<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import type { PluginInfo, PluginPanel, PanelData, PanelItem } from '../../shared/types'

const pluginList = ref<PluginInfo[]>([])
const panels = ref<PluginPanel[]>([])
const panelDataMap = ref<Record<string, PanelData>>({})
const isLoading = ref(false)
const showUserMenu = ref(false)
const notifCount = ref(0)
const notifs = ref<any[]>([])
let notifTimer: any = null

async function loadPlugins() {
  isLoading.value = true
  try {
    pluginList.value = await window.mqbox?.plugin.list() || []
    panels.value = await window.mqbox?.plugin.getPanels() || []
    for (const panel of panels.value) {
      await loadPanelData(panel.pluginId)
    }
  } catch {}
  isLoading.value = false
}

async function loadPanelData(pluginId: string) {
  try {
    const data = await window.mqbox?.plugin.getPanelData(pluginId)
    if (data) panelDataMap.value[pluginId] = data
  } catch {}
}

function openPluginPage(pluginId: string) {
  window.mqbox?.window.openPluginWindow(pluginId)
}

function openSearch() { window.mqbox?.window.openSearch() }
function openManager() { showUserMenu.value = false; window.mqbox?.window.openPluginManager() }
function handleClose() { window.mqbox?.window.hide() }

async function logout() {
  await window.mqbox?.config.set('token', '')
  await window.mqbox?.config.set('refresh_token', '')
  window.mqbox?.window.openMain()
}

async function executeCommand(pluginId: string, command: string, args?: unknown) {
  if (command === 'openPage') {
    openPluginPage(pluginId)
    return
  }
  await window.mqbox?.plugin.execute(pluginId, command, args || {})
  await loadPanelData(pluginId)
}

function handleItemClick(pluginId: string, item: PanelItem) {
  if (item.action) {
    executeCommand(pluginId, item.action, item.actionArgs)
  }
}

async function handleSwitch(pluginId: string, sw: any, newVal: boolean) {
  await executeCommand(pluginId, sw.command, sw.commandArgs)
  await loadPanelData(pluginId)
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

const defaultIcon: Record<string, string> = {
  assistant: '💬', calculator: '🔢', 'clipboard-history': '📋', files: '📁', notes: '📝',
  player: '🎵', 'quick-notes': '⚡', remote: '🖥️', rss: '📡', schedule: '📅',
  screenshot: '📸', todo: '✅', notifications: '🔔', everything: '🔍',
}

onMounted(() => {
  loadPlugins()
  fetchNotifCount()
  notifTimer = setInterval(fetchNotifCount, 15000)
  window.mqbox?.plugin?.onUpdated(() => loadPlugins())
  window.mqbox?.clipboard?.onUpdated(() => loadPlugins())
  window.mqbox?.player?.onUpdated(() => loadPlugins())
  window.mqbox?.todo?.onUpdated(() => loadPlugins())
})

onUnmounted(() => { if (notifTimer) clearInterval(notifTimer) })
</script>

<template>
  <div class="main-panel">
    <div class="title-bar">
      <span class="title-text">OmniAide</span>
      <div class="title-actions">
        <button class="title-btn" @click="handleClose">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </button>
      </div>
    </div>

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

    <div class="panels-area">
      <div v-if="isLoading" class="loading-state">加载中...</div>
      <div v-else class="panels-list">
        <template v-for="panel in panels" :key="panel.id">
          <div v-if="panelDataMap[panel.pluginId]" class="panel-card">

            <!-- Header: icon + title/subtitle + arrow -->
            <div class="panel-hd">
              <span class="panel-icon">{{ defaultIcon[panel.pluginId] || '🔌' }}</span>
              <div class="panel-hd-text">
                <span class="panel-title">{{ panelDataMap[panel.pluginId].title }}</span>
                <span v-if="panelDataMap[panel.pluginId].subtitle" class="panel-subtitle">{{ panelDataMap[panel.pluginId].subtitle }}</span>
              </div>
              <button class="panel-arrow" @click.stop="openPluginPage(panel.pluginId)">›</button>
            </div>

            <!-- Description text -->
            <div v-if="panelDataMap[panel.pluginId].description" class="panel-desc">
              {{ panelDataMap[panel.pluginId].description }}
            </div>

            <!-- Action items (two-line: title + subtitle) -->
            <div v-if="panelDataMap[panel.pluginId].items?.length" class="panel-items">
              <div
                v-for="(item, idx) in panelDataMap[panel.pluginId].items!"
                :key="idx"
                class="panel-item"
                :class="{ clickable: !!item.action }"
                @click="handleItemClick(panel.pluginId, item)"
              >
                <span class="pi-title">{{ item.title }}</span>
                <span v-if="item.subtitle" class="pi-subtitle">{{ item.subtitle }}</span>
              </div>
            </div>

            <!-- Switches -->
            <div v-if="panelDataMap[panel.pluginId].switches?.length" class="panel-switches">
              <div
                v-for="(sw, idx) in panelDataMap[panel.pluginId].switches!"
                :key="idx"
                class="panel-switch-row"
              >
                <span class="ps-label">{{ sw.label }}</span>
                <label class="switch-toggle">
                  <input
                    type="checkbox"
                    :checked="sw.value"
                    @change="handleSwitch(panel.pluginId, sw, ($event.target as HTMLInputElement).checked)"
                  >
                  <span class="switch-slider"></span>
                </label>
              </div>
            </div>

            <!-- Buttons -->
            <div v-if="panelDataMap[panel.pluginId].buttons?.length" class="panel-buttons">
              <button
                v-for="(btn, idx) in panelDataMap[panel.pluginId].buttons!"
                :key="idx"
                class="panel-btn"
                @click.stop="executeCommand(panel.pluginId, btn.command)"
              >{{ btn.label }}</button>
            </div>

          </div>
        </template>
      </div>
    </div>

    <div class="resize-handle"></div>
  </div>
</template>

<style scoped>
.bell-btn { position:relative; width:32px;height:32px;border:none;border-radius:6px;background:transparent;color:#868e96;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.bell-btn:hover { background:#f1f3f5;color:#495057; }
.bell-dot { position:absolute;top:1px;right:2px;width:16px;height:14px;border-radius:7px;background:#e91e63;color:#fff;font-size:10px;line-height:14px;text-align:center;font-weight:700; }
.notif-item { padding:8px 12px;cursor:pointer;border-bottom:1px solid #f5f5f5;min-width:220px; }
.notif-item:hover { background:#f8f9fa; }
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
.user-menu { position:absolute; top:56px; left:12px; width:160px; background:#fff; border-radius:10px; box-shadow:0 4px 16px rgba(0,0,0,0.15); border:1px solid #e0e0e0; padding:4px 0; z-index:50; }
.menu-item { width:100%; display:flex; align-items:center; gap:8px; padding:8px 12px; font-size:13px; color:#333; background:none; border:none; cursor:pointer; }
.menu-item:hover { background:#f5f5f5; }
.menu-item.danger { color:#E53935; }
.menu-item.danger svg { color:#E53935; }
.panels-area { flex:1; min-height:0; overflow-y:auto; padding:8px 12px; scrollbar-width:none; }
.panels-area::-webkit-scrollbar { display:none; }
.panels-list { display:flex; flex-direction:column; gap:8px; }
.loading-state { display:flex; align-items:center; justify-content:center; height:100px; color:#666; font-size:14px; }

/* Panel Card */
.panel-card { background:#f8f9fa; border-radius:8px; overflow:hidden; }

/* Header: icon + text + arrow */
.panel-hd { display:flex; align-items:center; gap:10px; padding:10px 12px; }
.panel-icon { width:32px; height:32px; border-radius:8px; background:#eef0f4; display:flex; align-items:center; justify-content:center; font-size:16px; flex-shrink:0; }
.panel-hd-text { flex:1; min-width:0; display:flex; flex-direction:column; gap:1px; }
.panel-title { font-size:14px; font-weight:700; color:#1a1a1a; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.panel-subtitle { font-size:11px; color:#909399; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.panel-arrow { width:24px; height:24px; border:none; border-radius:12px; background:transparent; color:#909399; font-size:18px; line-height:24px; text-align:center; cursor:pointer; flex-shrink:0; display:flex; align-items:center; justify-content:center; }
.panel-arrow:hover { background:#e0e0e0; color:#333; }

/* Description */
.panel-desc { padding:0 12px 10px; font-size:11px; color:#909399; line-height:1.5; }

/* Action Items (two-line) */
.panel-items { padding:0 0 4px; border-top:1px solid #e8e8e8; }
.panel-item { display:flex; flex-direction:column; gap:1px; padding:7px 12px; }
.panel-item.clickable { cursor:pointer; }
.panel-item.clickable:hover { background:#e3e5e8; }
.pi-title { font-size:12px; font-weight:500; color:#333; }
.pi-subtitle { font-size:10px; color:#909399; }

/* Switches */
.panel-switches { border-top:1px solid #e8e8e8; padding:4px 12px; }
.panel-switch-row { display:flex; align-items:center; justify-content:space-between; padding:6px 0; }
.ps-label { font-size:12px; color:#333; }
.switch-toggle { position:relative; width:36px; height:20px; flex-shrink:0; }
.switch-toggle input { opacity:0; width:0; height:0; }
.switch-slider { position:absolute; inset:0; background:#ccc; border-radius:10px; cursor:pointer; transition:background .2s; }
.switch-slider::before { content:''; position:absolute; left:2px; top:2px; width:16px; height:16px; border-radius:8px; background:#fff; transition:transform .2s; }
.switch-toggle input:checked + .switch-slider { background:#0078D4; }
.switch-toggle input:checked + .switch-slider::before { transform:translateX(16px); }

/* Buttons */
.panel-buttons { display:flex; gap:6px; padding:8px 12px; border-top:1px solid #e8e8e8; }
.panel-btn { flex:1; padding:6px 0; font-size:12px; border-radius:6px; border:1px solid #d0d0d0; background:#fff; color:#333; cursor:pointer; text-align:center; }
.panel-btn:hover { background:#ebebeb; color:#1a1a1a; }

.resize-handle { position:absolute; right:0; bottom:0; width:16px; height:16px; cursor:se-resize; -webkit-app-region:no-drag; }
</style>
