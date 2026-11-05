<template>
  <div class="header">
    <div class="header-left">
      <button class="icon-btn" @click="$emit('toggle-sidebar')">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
      </button>
      <div class="crumb">
        <span class="crumb-dot"></span>
        <span class="breadcrumb">{{ route.meta.title || route.name }}</span>
      </div>
    </div>
    <div class="header-right">
      <GlobalSearch />
      <el-dropdown trigger="click" @visible-change="onBellVisible">
        <el-badge :value="unreadCount" :hidden="unreadCount === 0" class="bell-badge">
          <button class="icon-btn">
            <el-icon><Bell /></el-icon>
          </button>
        </el-badge>
        <template #dropdown>
          <el-dropdown-menu class="notification-menu">
            <div class="notif-head">
              <span class="notif-head-title">通知</span>
              <button v-if="unreadCount > 0" class="notif-clear" @click.stop="markAllRead">全部已读</button>
            </div>
            <div v-if="notifications.length === 0" class="notif-empty">暂无通知</div>
            <div v-for="n in notifications" :key="n.id" class="notif-item" :class="{ unread: !n.read }" @click="markRead(n)">
              <div class="notif-dot" v-if="!n.read"></div>
              <div class="notif-body">
                <div class="notif-title">{{ n.title }}</div>
                <div v-if="n.body" class="notif-text">{{ n.body }}</div>
                <div class="notif-time">{{ formatTime(n.created_at) }}</div>
              </div>
            </div>
            <div v-if="notifications.length" class="notif-all" @click="router.push('/notifications')">查看全部通知</div>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <div class="header-divider"></div>
      <el-dropdown v-if="auth.user" trigger="click">
        <div class="user-info">
          <el-avatar :size="28">{{ displayName[0]?.toUpperCase() }}</el-avatar>
          <span class="user-name">{{ displayName }}</span>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="router.push('/settings')">
              <el-icon><Setting /></el-icon>设置
            </el-dropdown-item>
            <el-dropdown-item divided @click="auth.logout(); router.push('/login')" style="color:#f56c6c">
              <el-icon><SwitchButton /></el-icon>退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Setting, SwitchButton, Bell } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import client from '@/api/client'
import { parseBackendDate } from '@/utils/date'
import GlobalSearch from './GlobalSearch.vue'

defineEmits<{ 'toggle-sidebar': [] }>()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const displayName = computed(() => auth.user?.username || auth.user?.email || '用户')

const notifications = ref<any[]>([])
const unreadCount = ref(0)
let ws: WebSocket | null = null
let reconnectTimer: any = null
let disposed = false
let retry = 0

function connectWebSocket() {
  const token = localStorage.getItem('token')
  if (!token || disposed) return
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const base = import.meta.env.BASE_URL.replace(/\/$/, '')
  ws = new WebSocket(`${proto}://${window.location.host}${base}/ws/host?role=viewer&token=${encodeURIComponent(token)}`)
  ws.onopen = () => { retry = 0 }
  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      if (data?.channel === 'notifications' || data?.type === 'new_notification') {
        fetchUnreadCount()
        fetchNotifications()
        window.dispatchEvent(new CustomEvent('omniaide:notification'))
      }
      if (data?.channel === 'chat' && data?.type === 'chat_reply') {
        window.dispatchEvent(new CustomEvent('omniaide:chat-reply', { detail: data }))
      }
      if (data?.type === 'approval_required') {
        window.dispatchEvent(new CustomEvent('omniaide:approval'))
      }
    } catch { /* ignore */ }
  }
  ws.onclose = () => {
    ws = null
    if (disposed) return
    retry = Math.min(retry + 1, 6)
    const delay = Math.min(30000, 1000 * 2 ** (retry - 1))
    reconnectTimer = setTimeout(connectWebSocket, delay)
  }
  ws.onerror = () => ws?.close()
}

async function fetchNotifications() {
  try {
    const r = await client.get('/notifications?limit=10')
    notifications.value = r.data || []
  } catch { /* ignore */ }
}
function onBellVisible(visible: boolean) {
  if (visible) fetchNotifications()
}
async function fetchUnreadCount() {
  try { const r = await client.get('/notifications/unread-count'); unreadCount.value = r.data.count || 0 } catch { /* ignore */ }
}
async function markRead(n: any) {
  if (!n.read) {
    try {
      await client.put(`/notifications/${n.id}/read`)
      n.read = true
      unreadCount.value = Math.max(0, unreadCount.value - 1)
    } catch { /* ignore */ }
  }
  if (n.link) {
    if (/^https?:\/\//.test(n.link)) window.open(n.link, '_blank')
    else router.push(n.link)
  }
}
async function markAllRead() {
  try {
    await client.put('/notifications/read-all')
    notifications.value.forEach(n => n.read = true)
    unreadCount.value = 0
  } catch { /* ignore */ }
}
function formatTime(iso: string) {
  if (!iso) return ''
  const d = parseBackendDate(iso)
  if (isNaN(d.getTime())) return ''
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}
onMounted(() => { fetchUnreadCount(); fetchNotifications(); connectWebSocket() })
onUnmounted(() => {
  disposed = true
  if (reconnectTimer) clearTimeout(reconnectTimer)
  if (ws) ws.close()
  ws = null
})
</script>

<style scoped>
.header {
  height: var(--header-height);
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 20px; flex-shrink: 0;
  background: rgba(255, 255, 255, .78);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border-bottom: 1px solid rgba(231, 235, 243, .9);
  position: relative; z-index: 10;
}
.header-left { display: flex; align-items: center; gap: 10px; min-width: 0; }
.icon-btn {
  width: 34px; height: 34px; border: none; border-radius: 9px;
  background: transparent; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  color: #64748b; font-size: 17px;
  transition: background .15s, color .15s;
}
.icon-btn:hover { background: #eef1f8; color: #334155; }
.crumb { display: flex; align-items: center; gap: 8px; min-width: 0; }
.crumb-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: linear-gradient(135deg, #6366f1, #a855f7);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, .12);
  flex-shrink: 0;
}
.breadcrumb {
  font-size: 14px; font-weight: 600; color: #1f2937;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.header-right { display: flex; align-items: center; gap: 6px; }
.header-divider { width: 1px; height: 20px; background: #e5e9f2; margin: 0 6px; }

.user-info {
  display: flex; align-items: center; gap: 8px; cursor: pointer;
  padding: 4px 8px; border-radius: 9px; transition: background .15s;
}
.user-info:hover { background: #eef1f8; }
.user-info :deep(.el-avatar) {
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  font-size: 12px;
}
.user-name { font-size: 13px; color: #334155; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.bell-badge { margin-right: 2px; }
.bell-badge :deep(.el-badge__content) { border: none; }

.notification-menu { width: min(330px, calc(100vw - 28px)); max-height: 420px; overflow-y: auto; padding: 6px 0 0; }
.notif-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 16px 10px; border-bottom: 1px solid #f1f4f9;
}
.notif-head-title { font-size: 13px; font-weight: 600; color: #1f2937; }
.notif-clear {
  border: none; background: transparent; cursor: pointer;
  font-size: 12px; color: var(--brand-500); padding: 2px 4px;
}
.notif-clear:hover { color: var(--brand-600); }
.notif-empty { text-align: center; padding: 26px 0; color: #94a3b8; font-size: 12px; }
.notif-item {
  display: flex; align-items: flex-start; gap: 9px;
  padding: 11px 16px; cursor: pointer;
  border-bottom: 1px solid #f5f7fb;
  transition: background .15s;
}
.notif-item:hover { background: #f8faff; }
.notif-item.unread { background: #f5f7ff; }
.notif-item.unread:hover { background: #eef2ff; }
.notif-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--brand-500); flex-shrink: 0; margin-top: 6px; }
.notif-body { flex: 1; min-width: 0; }
.notif-title { font-size: 13px; color: #1f2937; font-weight: 500; }
.notif-text {
  font-size: 12px; color: #64748b; margin-top: 3px; line-height: 1.45;
  overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
}
.notif-time { font-size: 11px; color: #9aa5b8; margin-top: 4px; }
.notif-all {
  text-align: center; padding: 10px; font-size: 12px; color: var(--brand-500);
  cursor: pointer; border-top: 1px solid #f1f4f9;
}
.notif-all:hover { background: #f8faff; }

@media (max-width: 768px) {
  .header { padding: 0 12px; }
  .header-right { gap: 2px; }
  .header-divider { display: none; }
  .breadcrumb { max-width: 120px; }
  .user-name { display: none; }
  .header-right :deep(.global-search) { display: none; }
  .bell-badge { margin-right: 0; }
}
</style>
