<template>
  <div class="page-wrapper notifications-page">
    <div class="page-header notif-header">
      <div>
        <h2>通知</h2>
        <p class="sub">{{ unreadCount }} 条未读 · 共 {{ notifications.length }} 条</p>
      </div>
      <div class="header-actions">
        <el-radio-group v-model="filter" size="small" @change="load">
          <el-radio-button label="all">全部</el-radio-button>
          <el-radio-button label="unread">未读</el-radio-button>
        </el-radio-group>
        <el-button :icon="Refresh" @click="load">刷新</el-button>
        <el-button type="primary" :disabled="unreadCount === 0" @click="markAllRead">全部已读</el-button>
      </div>
    </div>

    <div v-loading="loading" class="page-card">
      <div v-if="notifications.length === 0" class="empty">
        <el-icon :size="30"><Bell /></el-icon>
        <p>暂无通知</p>
      </div>
      <div
        v-for="n in notifications"
        :key="n.id"
        class="notif-row"
        :class="{ unread: !n.read }"
        @click="openNotification(n)"
      >
        <span class="dot" v-if="!n.read"></span>
        <div class="notif-main">
          <div class="notif-title">{{ n.title }}</div>
          <div v-if="n.body" class="notif-body">{{ n.body }}</div>
          <div v-if="n.actions?.length" class="notif-actions" @click.stop>
            <el-button
              v-for="a in n.actions"
              :key="a.key"
              size="small"
              :type="a.kind === 'complete_todo' ? 'primary' : 'default'"
              @click="runAction(n, a)"
            >{{ a.label }}</el-button>
          </div>
          <div class="notif-meta">{{ formatTime(n.created_at) }}</div>
        </div>
        <el-tag v-if="!n.read" size="small" type="warning">未读</el-tag>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Bell, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import client from '@/api/client'
import { formatBackendDate } from '@/utils/date'

const router = useRouter()
const notifications = ref<any[]>([])
const unreadCount = ref(0)
const filter = ref<'all' | 'unread'>('all')
const loading = ref(false)

function formatTime(value: string) {
  return value ? formatBackendDate(value) : ''
}

async function load() {
  loading.value = true
  try {
    const params: Record<string, any> = { limit: 100 }
    if (filter.value === 'unread') params.unread = true
    const [list, count] = await Promise.all([
      client.get('/notifications', { params }),
      client.get('/notifications/unread-count'),
    ])
    notifications.value = Array.isArray(list.data) ? list.data : []
    unreadCount.value = Number(count.data?.count || 0)
  } finally {
    loading.value = false
  }
}

async function openNotification(n: any) {
  if (!n.read) {
    try {
      await client.put(`/notifications/${n.id}/read`)
      n.read = true
      unreadCount.value = Math.max(0, unreadCount.value - 1)
      window.dispatchEvent(new CustomEvent('omniaide:notification'))
    } catch { /* ignore */ }
  }
  if (n.link) {
    if (/^https?:\/\//.test(n.link)) window.open(n.link, '_blank')
    else router.push(n.link)
  }
}

async function runAction(n: any, action: any) {
  try {
    const { data } = await client.post(`/notifications/${n.id}/action`, { action: action.key })
    if (data?.todo_id) ElMessage.success('已完成待办')
    else if (data?.scheduled_at) ElMessage.success('已稍后提醒')
    else if (data?.link) {
      if (/^https?:\/\//.test(data.link)) window.open(data.link, '_blank')
      else router.push(data.link)
    }
    window.dispatchEvent(new CustomEvent('omniaide:notification'))
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  }
}

async function markAllRead() {
  await client.put('/notifications/read-all')
  unreadCount.value = 0
  window.dispatchEvent(new CustomEvent('omniaide:notification'))
  await load()
}

onMounted(load)
</script>

<style scoped>
.notifications-page { max-width: 900px; margin: 0 auto; }
.notif-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.notif-header .sub { margin: 4px 0 0; font-size: 12px; color: #909399; }
.header-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 60px 0; color: #b0b5bd; }
.empty p { margin: 0; font-size: 13px; }
.notif-row {
  display: flex; align-items: flex-start; gap: 10px; padding: 14px 18px;
  border-bottom: 1px solid #f0f2f5; cursor: pointer; transition: background .15s;
}
.notif-row:last-child { border-bottom: none; }
.notif-row:hover { background: #f7f9fc; }
.notif-row.unread { background: #f5f9ff; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #409eff; margin-top: 7px; flex-shrink: 0; }
.notif-main { flex: 1; min-width: 0; }
.notif-title { font-size: 14px; font-weight: 600; color: #2c3550; }
.notif-body { font-size: 13px; color: #606266; margin-top: 4px; word-break: break-word; }
.notif-actions { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
.notif-meta { font-size: 11px; color: #a0a4ad; margin-top: 6px; }
@media (max-width: 600px) {
  .notif-header { flex-direction: column; align-items: stretch; }
  .header-actions { justify-content: flex-start; }
  .notif-row { padding: 12px 14px; }
}
</style>
