<template>
  <div class="page-wrapper">
    <div class="page-header"><h2>仪表盘</h2></div>

    <el-row :gutter="16" style="margin-bottom:16px">
      <el-col :span="6" v-for="s in stats" :key="s.label">
        <div class="stat-card">
          <div class="stat-value">{{ s.value }}</div>
          <div class="stat-label">{{ s.label }}</div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="16">
        <div class="page-card">
          <div class="page-card-body">
            <h3 style="font-size:14px;font-weight:600;color:#1a1a2e;margin:0 0 12px">最近活动</h3>
            <el-table :data="events" stripe size="small" v-loading="eventsLoading">
              <el-table-column prop="event_type" label="类型" width="110" />
              <el-table-column prop="summary" label="内容" min-width="200" />
              <el-table-column prop="created_at" label="时间" width="170" />
            </el-table>
            <p v-if="!eventsLoading && events.length === 0" style="text-align:center;color:#909399;padding:20px">暂无活动记录</p>
          </div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="page-card" style="margin-bottom:16px">
          <div class="page-card-body">
            <h3 style="font-size:14px;font-weight:600;color:#1a1a2e;margin:0 0 12px">系统状态</h3>
            <div class="info-row"><span class="info-label">后端</span><span>{{ healthTitle }}</span></div>
            <div class="info-row"><span class="info-label">版本</span><span>{{ serverVersion || '-' }}</span></div>
            <div class="info-row"><span class="info-label">状态</span><el-tag :type="connected ? 'success' : 'danger'" size="small">{{ connected ? '正常' : '离线' }}</el-tag></div>
            <div class="info-row"><span class="info-label">数据节点</span><span>{{ new Intl.DateTimeFormat('zh-CN').format(new Date()) }}</span></div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import client from '@/api/client'

const stats = ref([{ label: '用户数', value: '...' }, { label: '文件数', value: '...' }, { label: '工作区', value: '...' }, { label: '事件数', value: '...' }])
const events = ref<any[]>([])
const eventsLoading = ref(true)
const connected = ref(false)
const serverVersion = ref('')
const healthTitle = ref('...')

async function fetchStats() {
  try {
    const [users, files, ws, ev] = await Promise.all([
      client.get('/auth/users').then(r => r.data.length || r.data.length).catch(() => '?'),
      client.get('/files?page_size=1').then(r => r.data.total ?? r.data.length ?? '?').catch(() => '?'),
      Promise.resolve(0).catch(() => '?'),
      client.get('/events?limit=0').then(r => Array.isArray(r.data) ? r.data.length : '?').catch(() => '?'),
    ])
    stats.value = [
      { label: '用户数', value: String(users) },
      { label: '文件数', value: String(files) },
      { label: '工作区', value: String(ws) },
      { label: '事件数', value: String(ev) },
    ]
  } catch { /* keep defaults */ }
}

async function fetchEvents() {
  eventsLoading.value = true
  try {
    const r = await client.get('/events?limit=10')
    events.value = r.data || []
  } catch { events.value = [] }
  finally { eventsLoading.value = false }
}

async function checkHealth() {
  try {
    const r = await client.get('/health')
    connected.value = true
    serverVersion.value = r.data?.version || ''
  } catch { connected.value = false }
}

onMounted(() => {
  fetchStats()
  fetchEvents()
  checkHealth()
})
</script>

<style scoped>
.stat-card { background:#fff; border-radius:10px; border:1px solid var(--color-border); padding:20px; text-align:center; }
.stat-value { font-size:28px; font-weight:700; color:#1a1a2e; }
.stat-label { font-size:12px; color:#909399; margin-top:4px; }
.info-row { display:flex; justify-content:space-between; align-items:center; padding:6px 0; font-size:13px; border-bottom:1px solid #f5f5f5; }
.info-row:last-child { border-bottom:none; }
.info-label { color:#909399; }
</style>
