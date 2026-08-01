<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import type { PluginInfo, PluginPanel, PanelData, PanelItem } from '../../shared/types'
import PanelCard from './PanelCard.vue'
import { parseBackendDate } from '../utils/date'

const pluginList = ref<PluginInfo[]>([])
const panels = ref<PluginPanel[]>([])
const panelDataMap = ref<Record<string, PanelData>>({})
const isLoading = ref(false)
const showUserMenu = ref(false)
const showNotifPage = ref(false)
const showNotifDropdown = ref(false)
const notifCount = ref(0)
const notifs = ref<any[]>([])
const allNotifs = ref<any[]>([])
let notifTimer: any = null

async function toggleNotifDropdown() {
  showNotifDropdown.value = !showNotifDropdown.value
  if (showNotifDropdown.value) fetchNotifs()
}

async function loadPlugins() {
  isLoading.value = true
  try {
    pluginList.value = await window.mqbox?.plugin.list() || []
    panels.value = await window.mqbox?.plugin.getPanels() || []
    for (const panel of panels.value) {
      await loadPanelData(panel.pluginId)
    }
    // Register per-plugin panel update listeners
    panels.value.forEach(p => {
      window.mqbox?.plugin?.onPanelUpdated?.(p.pluginId, () => loadPanelData(p.pluginId))
    })
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

async function fetchNotifs() {
  try { const r = await window.mqbox?.api.get('/notifications?unread=true&limit=5'); notifs.value = r || [] } catch {}
}
async function fetchNotifCount() {
  try { const r = await window.mqbox?.api.get('/notifications/unread-count'); notifCount.value = r?.count || 0 } catch {}
}
async function markRead(n: any) {
  try {
    await window.mqbox?.api.put(`/notifications/${n.id}/read`)
    n.read = true
    n._justRead = true
    notifCount.value = Math.max(0, notifCount.value - 1)
    if (n._feedbackTimer) clearTimeout(n._feedbackTimer)
    n._feedbackTimer = setTimeout(() => { n._justRead = false }, 1500)
  } catch (e: any) {
    console.error('[panel] mark read failed:', e?.message || e)
  }
}
async function openNotifPage() {
  showNotifPage.value = true
  try { const r = await window.mqbox?.api.get('/notifications?limit=100'); allNotifs.value = r || [] } catch {}
}
async function markAllRead() {
  try {
    await window.mqbox?.api.put('/notifications/read-all')
    allNotifs.value.forEach(n => n.read = true)
    notifCount.value = 0
  } catch {}
}
function closeNotifPage() { showNotifPage.value = false }
function onDocClick(e: MouseEvent) {
  const wrap = document.querySelector('.notif-wrap')
  if (wrap && wrap.contains(e.target as Node)) return
  showNotifDropdown.value = false
}
function fmt(iso: string) {
  if (!iso) return ''
  const d = parseBackendDate(iso)
  if (isNaN(d.getTime())) return ''
  const now = new Date(); const diff = now.getTime() - d.getTime()
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
  document.addEventListener('mousedown', onDocClick)
})

onUnmounted(() => {
  if (notifTimer) clearInterval(notifTimer)
  document.removeEventListener('mousedown', onDocClick)
})
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
      <div class="notif-wrap" @click.stop>
        <button class="bell-btn" @click="toggleNotifDropdown"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg><span v-if="notifCount > 0" class="bell-dot">{{ notifCount }}</span></button>

        <div v-if="showNotifDropdown" class="notif-dropdown">
          <div v-if="notifs.length === 0" class="notif-empty">暂无通知</div>
          <div v-for="n in notifs.slice(0,5)" :key="n.id" class="notif-item" :class="{ unread: !n.read }" @click="markRead(n)">
            <div class="notif-item-ic">
              <span v-if="!n.read" class="notif-dot"></span>
              <span v-else class="notif-check">✓</span>
            </div>
            <div class="notif-item-ct">
              <div class="notif-item-title">{{ n.title }}</div>
              <div class="notif-item-time">{{ fmt(n.created_at) }}</div>
            </div>
          </div>
          <div class="notif-all" @click="showNotifDropdown = false; openNotifPage()">查看全部 ›</div>
        </div>
      </div>

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
      <div v-if="showNotifPage" class="notif-page">
        <div class="notif-page-hd">
          <span class="notif-page-title">通知</span>
          <button class="notif-page-btn" @click="markAllRead">全部已读</button>
          <button class="notif-close-btn" @click="closeNotifPage">×</button>
        </div>
        <div v-if="allNotifs.length === 0" class="loading-state" style="padding:40px">暂无通知</div>
        <div v-for="n in allNotifs" :key="n.id" class="notif-list-item" :class="{ unread: !n.read, 'just-read': n._justRead }" @click="markRead(n)">
          <div class="notif-ic">
            <span v-if="!n.read" class="notif-dot"></span>
            <span v-else class="notif-check">✓</span>
          </div>
          <div class="notif-ct">
            <div class="notif-title">{{ n.title }}</div>
            <div v-if="n.body" class="notif-body">{{ n.body }}</div>
            <div class="notif-time">{{ fmt(n.created_at) }}</div>
          </div>
        </div>
      </div>

      <template v-else>
        <div v-if="isLoading" class="loading-state">加载中...</div>
        <div v-else class="panels-list">
          <template v-for="panel in panels" :key="panel.id">
            <PanelCard
              v-if="panelDataMap[panel.pluginId]"
              :plugin-id="panel.pluginId"
              :data="panelDataMap[panel.pluginId]!"
              :has-page="!!panel.hasPage"
              @execute="(cmd: string, args?: unknown) => executeCommand(panel.pluginId, cmd, args)"
              @open-page="openPluginPage(panel.pluginId)"
            />
          </template>
        </div>
      </template>
    </div>

    <div class="resize-handle"></div>
  </div>
</template>

<style scoped>
.bell-btn { position:relative; width:32px;height:32px;border:none;border-radius:50%;background:transparent;color:#8a94a8;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:3px 3px 6px rgba(163,177,198,0.5),-3px -3px 6px rgba(255,255,255,0.75); }
.bell-btn:hover { color:#4f46e5; }
.bell-btn:active { box-shadow:inset 3px 3px 6px rgba(163,177,198,0.55),inset -3px -3px 6px rgba(255,255,255,0.8); }
.bell-dot { position:absolute;top:-2px;right:-2px;width:16px;height:14px;border-radius:7px;background:linear-gradient(145deg,#ff5f6d,#e91e63);color:#fff;font-size:10px;line-height:14px;text-align:center;font-weight:700;box-shadow:0 2px 4px rgba(233,30,99,0.4); }
.main-panel { width:300px; height:600px; border-radius:18px; background:#e4e9f0; box-shadow:10px 10px 20px rgba(163,177,198,0.55),-10px -10px 20px rgba(255,255,255,0.75),inset 1px 1px 2px rgba(255,255,255,0.6); border:none; display:flex; flex-direction:column; position:relative; overflow:hidden; }
.title-bar { height:34px; background:transparent; display:flex; align-items:center; justify-content:space-between; padding:0 14px; -webkit-app-region:drag; }
.title-text { font-size:13px; color:#6b7280; font-weight:600; letter-spacing:0.5px; }
.title-actions { display:flex; gap:8px; -webkit-app-region:no-drag; }
.title-btn { width:26px; height:26px; border-radius:13px; background:#e4e9f0; border:none; display:flex; align-items:center; justify-content:center; cursor:pointer; color:#6b7280; box-shadow:3px 3px 6px rgba(163,177,198,0.5),-3px -3px 6px rgba(255,255,255,0.75); }
.title-btn:hover { background:#f0f3f8; color:#e11d48; }
.title-btn:active { box-shadow:inset 3px 3px 6px rgba(163,177,198,0.55),inset -3px -3px 6px rgba(255,255,255,0.8); }
.user-area { height:60px; display:flex; align-items:center; gap:12px; padding:0 16px; position:relative; margin:4px 0; }
.user-avatar { width:42px; height:42px; border-radius:21px; background:linear-gradient(145deg,#5b6ee1,#4f46e5); display:flex; align-items:center; justify-content:center; cursor:pointer; box-shadow:4px 4px 8px rgba(79,70,229,0.35),-2px -2px 6px rgba(255,255,255,0.6); }
.user-avatar span { color:#fff; font-size:17px; font-weight:600; }
.user-info { flex:1; cursor:pointer; }
.user-name { font-size:14px; color:#3a4256; font-weight:700; display:block; letter-spacing:0.2px; }
.user-status { display:flex; align-items:center; gap:4px; }
.status-dot { width:8px; height:8px; border-radius:4px; background:#34d399; box-shadow:0 0 4px rgba(52,211,153,0.6); }
.user-status span { font-size:12px; color:#34d399; }
.user-menu { position:absolute; top:60px; left:12px; width:160px; background:#e4e9f0; border-radius:12px; box-shadow:6px 6px 14px rgba(163,177,198,0.55),-6px -6px 14px rgba(255,255,255,0.8); padding:6px; z-index:50; }
.menu-item { width:100%; display:flex; align-items:center; gap:8px; padding:9px 10px; font-size:13px; color:#4a5268; background:none; border:none; cursor:pointer; border-radius:8px; }
.menu-item:hover { background:#f0f3f8; color:#4f46e5; }
.menu-item.danger { color:#e11d48; }
.menu-item.danger svg { color:#e11d48; }
.panels-area { flex:1; min-height:0; overflow-y:auto; padding:10px 14px; scrollbar-width:none; }
.panels-area::-webkit-scrollbar { display:none; }
.panels-list { display:flex; flex-direction:column; gap:12px; }
.loading-state { display:flex; align-items:center; justify-content:center; height:100px; color:#8a94a8; font-size:14px; }

/* Panel Card (generic fallback styles kept for safety) */
.panel-card { background:#e4e9f0; border-radius:14px; overflow:hidden; box-shadow:7px 7px 14px rgba(163,177,198,0.55),-7px -7px 14px rgba(255,255,255,0.75); }
.panel-hd { display:flex; align-items:center; gap:10px; padding:12px 14px; }
.panel-icon { width:36px; height:36px; border-radius:12px; background:#e4e9f0; display:flex; align-items:center; justify-content:center; font-size:17px; flex-shrink:0; box-shadow:inset 3px 3px 6px rgba(163,177,198,0.55),inset -3px -3px 6px rgba(255,255,255,0.8); }
.panel-hd-text { flex:1; min-width:0; display:flex; flex-direction:column; gap:1px; }
.panel-title { font-size:14px; font-weight:700; color:#3a4256; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.panel-subtitle { font-size:11px; color:#8a94a8; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.panel-arrow { width:26px; height:26px; border:none; border-radius:13px; background:#e4e9f0; color:#8a94a8; font-size:18px; line-height:26px; text-align:center; cursor:pointer; flex-shrink:0; display:flex; align-items:center; justify-content:center; box-shadow:3px 3px 6px rgba(163,177,198,0.5),-3px -3px 6px rgba(255,255,255,0.75); }
.panel-arrow:hover { background:#f0f3f8; color:#4a5268; }
.panel-desc { padding:0 16px 10px; font-size:11px; color:#8a94a8; line-height:1.5; }
.panel-items { padding:0 10px 10px; display:flex; flex-direction:column; gap:4px; }
.panel-item { display:flex; flex-direction:column; gap:1px; padding:7px 10px; border-radius:9px; }
.panel-item.clickable { cursor:pointer; }
.panel-item.clickable:hover { box-shadow:inset 3px 3px 6px rgba(163,177,198,0.4),inset -3px -3px 6px rgba(255,255,255,0.7); }
.pi-title { font-size:12px; font-weight:500; color:#4a5268; }
.pi-subtitle { font-size:10px; color:#8a94a8; }
.panel-switches { padding:2px 16px 6px; }
.panel-switch-row { display:flex; align-items:center; justify-content:space-between; padding:6px 0; }
.ps-label { font-size:12px; color:#4a5268; }
.switch-toggle { position:relative; width:40px; height:22px; flex-shrink:0; }
.switch-toggle input { opacity:0; width:0; height:0; }
.switch-slider { position:absolute; inset:0; background:#e4e9f0; border-radius:11px; cursor:pointer; transition:background .2s; box-shadow:inset 2px 2px 4px rgba(163,177,198,0.55),inset -2px -2px 4px rgba(255,255,255,0.8); }
.switch-slider::before { content:''; position:absolute; left:3px; top:3px; width:16px; height:16px; border-radius:8px; background:#f5f7fa; transition:transform .2s; box-shadow:2px 2px 4px rgba(163,177,198,0.6); }
.switch-toggle input:checked + .switch-slider { background:linear-gradient(145deg,#5b6ee1,#4f46e5); }
.switch-toggle input:checked + .switch-slider::before { transform:translateX(18px); background:#fff; }
.panel-buttons { display:flex; gap:8px; padding:6px 14px 12px; }
.panel-btn { flex:1; padding:8px 0; font-size:12px; font-weight:600; border-radius:10px; border:none; background:#e4e9f0; color:#4a5268; cursor:pointer; text-align:center; box-shadow:4px 4px 8px rgba(163,177,198,0.55),-4px -4px 8px rgba(255,255,255,0.8); }
.panel-btn:hover { background:#f0f3f8; color:#4f46e5; }
.panel-btn:active { box-shadow:inset 4px 4px 8px rgba(163,177,198,0.6),inset -4px -4px 8px rgba(255,255,255,0.8); }

.resize-handle { position:absolute; right:0; bottom:0; width:16px; height:16px; cursor:se-resize; -webkit-app-region:no-drag; }
.notif-page { height:100%; overflow-y:auto; scrollbar-width:none; }
.notif-page::-webkit-scrollbar { display:none; }
.notif-page-hd { display:flex; align-items:center; gap:8px; padding:12px 16px; border-bottom:1px solid rgba(163,177,198,0.25); position:sticky; top:0; background:#e4e9f0; z-index:1; }
.notif-page-title { font-size:15px; font-weight:600; flex:1; color:#3a4256; }
.notif-page-btn { height:30px;padding:0 12px;border:none;border-radius:15px;background:#e4e9f0;color:#4a5268;font-size:12px;cursor:pointer;box-shadow:3px 3px 6px rgba(163,177,198,0.5),-3px -3px 6px rgba(255,255,255,0.75); }
.notif-page-btn:hover { background:#f0f3f8; }
.notif-page-btn:active { box-shadow:inset 3px 3px 6px rgba(163,177,198,0.55),inset -3px -3px 6px rgba(255,255,255,0.8); }
.notif-close-btn { width:28px;height:28px;border:none;border-radius:50%;background:transparent;font-size:18px;cursor:pointer;color:#8a94a8;display:flex;align-items:center;justify-content:center; }
.notif-close-btn:hover { background:#ffe4e6;color:#e11d48; }
.notif-list-item { display:flex; align-items:flex-start; gap:10px; padding:12px 16px; cursor:pointer; transition:background 0.12s; border-bottom:1px solid rgba(163,177,198,0.15); }
.notif-list-item:hover { background:#f0f3f8; }
.notif-list-item:active { background:#e8ecf3; }
.notif-list-item.unread { background:rgba(79,70,229,0.07); }
.notif-list-item.unread:hover { background:rgba(79,70,229,0.12); }
.notif-list-item.just-read { background:#eef7ee; }
.notif-ic { width:16px; height:16px; flex-shrink:0; margin-top:1px; display:flex; align-items:center; justify-content:center; }
.notif-dot { width:8px; height:8px; border-radius:4px; background:#4f46e5; box-shadow:0 0 4px rgba(79,70,229,0.5); }
.notif-check { color:#34d399; font-size:13px; font-weight:700; }
.notif-ct { flex:1; min-width:0; }
.notif-list-item .notif-title { font-size:13px;font-weight:500;color:#3a4256; }
.notif-list-item .notif-body { font-size:12px;color:#6b7280;margin-top:3px; white-space:pre-wrap; word-break:break-word; }
.notif-list-item .notif-time { font-size:10px;color:#8a94a8;margin-top:4px; }

/* Custom neumorphic notification dropdown */
.notif-wrap { flex-shrink: 0; }
.notif-dropdown {
  position: absolute; top: 48px; right: 10px; width: 250px; z-index: 60;
  background: #e4e9f0; border-radius: 14px; padding: 6px;
  box-shadow:
    8px 8px 16px rgba(163, 177, 198, 0.6),
    -8px -8px 16px rgba(255, 255, 255, 0.85),
    inset 1px 1px 2px rgba(255, 255, 255, 0.6);
}
.notif-dropdown .notif-empty { padding: 16px; text-align: center; color: #8a94a8; font-size: 12px; }
.notif-dropdown .notif-item {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 8px 10px; border-radius: 9px; cursor: pointer;
  transition: box-shadow 0.12s, background 0.12s;
}
.notif-dropdown .notif-item:hover {
  box-shadow:
    inset 3px 3px 6px rgba(163, 177, 198, 0.4),
    inset -3px -3px 6px rgba(255, 255, 255, 0.7);
}
.notif-dropdown .notif-item.unread { background: rgba(79, 70, 229, 0.07); }
.notif-item-ic { width: 14px; height: 14px; flex-shrink: 0; margin-top: 2px; display: flex; align-items: center; justify-content: center; }
.notif-item-ct { flex: 1; min-width: 0; }
.notif-item-title { font-size: 12px; font-weight: 500; color: #3a4256; white-space: normal; line-height: 1.4; word-break: break-word; }
.notif-item-time { font-size: 10px; color: #8a94a8; margin-top: 3px; }
.notif-all {
  margin-top: 4px; padding: 8px 10px; text-align: center; border-radius: 9px;
  font-size: 12px; color: #4f46e5; cursor: pointer;
  box-shadow:
    3px 3px 6px rgba(163, 177, 198, 0.5),
    -3px -3px 6px rgba(255, 255, 255, 0.75);
}
.notif-all:hover { color: #4338ca; }
.notif-all:active {
  box-shadow:
    inset 3px 3px 6px rgba(163, 177, 198, 0.55),
    inset -3px -3px 6px rgba(255, 255, 255, 0.8);
}
</style>
