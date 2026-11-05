<template>
  <div class="header">
    <div class="header-left">
      <button class="toggle-btn" @click="$emit('toggle-sidebar')">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
      </button>
      <span class="breadcrumb">{{ route.name }}</span>
    </div>
    <div class="header-right">
      <GlobalSearch />
      <el-dropdown trigger="click" @visible-change="onBellVisible">
        <el-badge :value="unreadCount" :hidden="unreadCount === 0" class="bell-badge">
          <button class="bell-btn">
            <el-icon><Bell /></el-icon>
          </button>
        </el-badge>
        <template #dropdown>
          <el-dropdown-menu class="notification-menu">
            <div v-if="notifications.length === 0" style="text-align:center;padding:20px;color:#909399;font-size:12px">暂无通知</div>
            <div v-for="n in notifications" :key="n.id" class="notif-item" :class="{ unread: !n.read }" @click="markRead(n)">
              <div class="notif-dot" v-if="!n.read"></div>
              <div class="notif-body">
                <div class="notif-title">{{ n.title }}</div>
                <div v-if="n.body" class="notif-text">{{ n.body }}</div>
                <div class="notif-time">{{ formatTime(n.created_at) }}</div>
              </div>
            </div>
            <div v-if="notifications.length" class="notif-all" @click="router.push('/notifications')">查看全部通知</div>
            <el-dropdown-item v-if="unreadCount > 0" divided @click="markAllRead" style="text-align:center;color:#409EFF;font-size:12px">
              全部标记已读
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
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
.header { height: var(--header-height); display: flex; align-items: center; justify-content: space-between; padding: 0 20px; background: #fff; border-bottom: 1px solid var(--color-border); flex-shrink: 0; }
.header-left { display: flex; align-items: center; gap: 12px; }
.toggle-btn { width: 36px; height: 36px; border: none; border-radius: 8px; background: transparent; cursor: pointer; display: flex; align-items: center; justify-content: center; color: #666; }
.toggle-btn:hover { background: #f5f5f5; color: #333; }
.breadcrumb { font-size: 14px; font-weight: 500; color: #1a1a2e; }
.header-right { display: flex; align-items: center; gap: 12px; }
.user-info { display: flex; align-items: center; gap: 8px; cursor: pointer; padding: 4px 8px; border-radius: 8px; }
.user-info:hover { background: #f5f5f5; }
.user-name { font-size: 13px; color: #333; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bell-badge { margin-right:8px; }
.bell-btn { width:36px;height:36px;border:none;border-radius:8px;background:transparent;cursor:pointer;display:flex;align-items:center;justify-content:center;color:#666;font-size:18px; }
.bell-btn:hover { background:#f5f5f5;color:#333; }
.notification-menu { width:320px; max-height:400px; overflow-y:auto; }
.notif-item { display:flex; align-items:flex-start; gap:8px; padding:10px 14px; cursor:pointer; border-bottom:1px solid #f5f5f5; }
.notif-item:hover { background:#f8f9fa; }
.notif-item.unread { background:#f0f7ff; }
.notif-dot { width:8px;height:8px;border-radius:50%;background:#409EFF;flex-shrink:0;margin-top:5px; }
.notif-body { flex:1;min-width:0; }
.notif-title { font-size:13px;color:#333; }
.notif-text { font-size:12px;color:#606266;margin-top:2px;line-height:1.4;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical; }
.notif-all { text-align:center;padding:8px;font-size:12px;color:#409EFF;cursor:pointer;border-top:1px solid #f5f5f5; }
.notif-all:hover { background:#f8f9fa; }
.notif-time { font-size:11px;color:#909399;margin-top:2px; }
@media (max-width: 768px) {
  .header { padding: 0 12px; }
  .header-right { gap: 6px; }
  .breadcrumb { max-width: 110px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .user-name { display: none; }
  .header-right :deep(.global-search) { display: none; }
  .bell-badge { margin-right: 0; }
}
</style>
