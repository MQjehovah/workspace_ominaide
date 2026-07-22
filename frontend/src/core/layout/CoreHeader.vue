<template>
  <div class="header">
    <div class="header-left">
      <button class="toggle-btn" @click="$emit('toggle-sidebar')">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
      </button>
      <span class="breadcrumb">{{ route.name }}</span>
    </div>
    <div class="header-right">
      <el-dropdown trigger="click" @visible-change="fetchNotifications">
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
                <div class="notif-time">{{ formatTime(n.created_at) }}</div>
              </div>
            </div>
            <el-dropdown-item v-if="unreadCount > 0" divided @click="markAllRead" style="text-align:center;color:#409EFF;font-size:12px">
              全部标记已读
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-dropdown v-if="auth.user" trigger="click">
        <div class="user-info">
          <el-avatar :size="28">{{ auth.user.username[0]?.toUpperCase() }}</el-avatar>
          <span class="user-name">{{ auth.user.username }}</span>
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
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Setting, SwitchButton, Bell } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import client from '@/api/client'

defineEmits<{ 'toggle-sidebar': [] }>()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const notifications = ref<any[]>([])
const unreadCount = ref(0)
let pollTimer: any = null

async function fetchNotifications() {
  try {
    const r = await client.get('/notifications?unread=true&limit=10')
    notifications.value = r.data || []
  } catch { /* ignore */ }
}
async function fetchUnreadCount() {
  try { const r = await client.get('/notifications/unread-count'); unreadCount.value = r.data.count || 0 } catch { /* ignore */ }
}
async function markRead(n: any) {
  try { await client.put(`/notifications/${n.id}/read`); n.read = true; unreadCount.value = Math.max(0, unreadCount.value - 1) } catch { /* ignore */ }
}
async function markAllRead() {
  try { await client.put('/notifications/read-all'); notifications.value.forEach(n => n.read = true); unreadCount.value = 0 } catch { /* ignore */ }
}
function formatTime(iso: string) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}
onMounted(() => { fetchUnreadCount(); pollTimer = setInterval(fetchUnreadCount, 15000) })
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
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
.notif-time { font-size:11px;color:#909399;margin-top:2px; }
</style>
