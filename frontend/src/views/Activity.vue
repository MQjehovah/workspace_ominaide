<template>
  <div class="page-wrapper">
    <div class="page-header"><h2>活动记录</h2></div>

    <!-- Stats Cards -->
    <el-row :gutter="16" style="margin-bottom:16px">
      <el-col :span="6" v-for="s in statCards" :key="s.label">
        <div class="stat-card">
          <div class="stat-value">{{ s.value }}</div>
          <div class="stat-label">{{ s.label }}</div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-bottom:16px">
      <!-- App usage -->
      <el-col :span="12">
        <div class="page-card">
          <div class="page-card-body">
            <h3 style="font-size:14px;font-weight:600;color:#1a1a2e;margin:0 0 12px">应用使用时长</h3>
            <div v-if="stats.app_minutes?.length" class="app-bars">
              <div v-for="a in stats.app_minutes" :key="a.app" class="app-bar-row">
                <span class="app-bar-name" :title="a.app">{{ friendlyApp(a.app) }}</span>
                <div class="app-bar-track">
                  <div class="app-bar-fill" :style="{ width: barWidth(a.minutes) + '%' }"></div>
                </div>
                <span class="app-bar-min">{{ a.minutes }} min</span>
              </div>
            </div>
            <p v-else style="text-align:center;color:#909399;font-size:12px;padding:20px">暂无应用使用数据（需在桌面端开启「用户行为采集」）</p>
          </div>
        </div>
      </el-col>

      <!-- Event type distribution -->
      <el-col :span="12">
        <div class="page-card">
          <div class="page-card-body">
            <h3 style="font-size:14px;font-weight:600;color:#1a1a2e;margin:0 0 12px">事件类型分布</h3>
            <div v-if="typeCountEntries.length" class="type-list">
              <div v-for="t in typeCountEntries" :key="t.type" class="type-row">
                <span class="type-label">{{ typeLabel(t.type) }}</span>
                <span class="type-count">{{ t.count }}</span>
              </div>
            </div>
            <p v-else style="text-align:center;color:#909399;font-size:12px;padding:20px">暂无事件</p>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- Event list -->
    <div class="page-card">
      <div class="page-card-body">
        <div class="list-toolbar">
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <el-select v-model="eventType" placeholder="全部类型" clearable size="small" style="width:160px" @change="page=1;loadEvents()">
              <el-option v-for="t in eventTypeOptions" :key="t.value" :label="t.label" :value="t.value" />
            </el-select>
            <el-select v-model="days" placeholder="时间范围" size="small" style="width:120px" @change="page=1;loadEvents()">
              <el-option label="近 1 天" :value="1" />
              <el-option label="近 7 天" :value="7" />
              <el-option label="近 30 天" :value="30" />
              <el-option label="全部" :value="0" />
            </el-select>
            <el-button size="small" :icon="Refresh" @click="loadAll" :loading="loading">刷新</el-button>
          </div>
          <span style="font-size:12px;color:#909399">共 {{ events.length }} 条</span>
        </div>

        <el-table :data="events" stripe size="small" v-loading="loading">
          <el-table-column label="类型" width="130">
            <template #default="{ row }">
              <el-tag :type="tagType(row.event_type)" size="small">{{ typeLabel(row.event_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="summary" label="内容" min-width="220" show-overflow-tooltip />
          <el-table-column label="详情" min-width="180">
            <template #default="{ row }">
              <span style="font-size:12px;color:#666">{{ detailText(row.details) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>

        <div v-if="hasMore" style="text-align:center;padding:12px">
          <el-button size="small" @click="loadMore" :loading="loadingMore">加载更多</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import client from '@/api/client'
import { Refresh } from '@element-plus/icons-vue'

const loading = ref(false)
const loadingMore = ref(false)
const events = ref<any[]>([])
const eventType = ref('')
const days = ref(7)
const page = ref(1)
const pageSize = 100
const hasMore = ref(false)
const stats = ref<any>({})

const TYPE_LABELS: Record<string, string> = {
  // 行为采集
  'app.used': '应用使用',
  'clipboard.copy': '剪贴板复制',
  // 文件
  'file.uploaded': '文件上传', 'file.trashed': '文件删除',
  'file.renamed': '文件重命名', 'file.moved': '文件移动',
  // 笔记
  'note.created': '笔记创建', 'note.updated': '笔记更新', 'note.deleted': '笔记删除',
  // 待办
  'todo.created': '待办创建', 'todo.updated': '待办修改', 'todo.deleted': '待办删除',
  // 日程
  'schedule.created': '日程创建', 'schedule.updated': '日程修改', 'schedule.deleted': '日程删除',
  // RSS
  'rss.subscribed': 'RSS订阅', 'rss.unsubscribed': 'RSS取消订阅', 'rss.refreshed': 'RSS刷新',
  'article.new': 'RSS新资讯获取',
  // 邮件
  'mail.received': '邮件收取',
  // 音乐
  'playlist.created': '歌单创建', 'playlist.deleted': '歌单删除',
  // 通知 / 其他
  'notifications.read': '通知已读', 'notifications.read-all': '通知全部已读',
  'search': '搜索', 'activities.created': '活动上报', 'briefing': '每日简报',
}
function typeLabel(t: string): string {
  if (TYPE_LABELS[t]) return TYPE_LABELS[t]
  // Fallback: convert snake_case English to a readable title case.
  return t
    .split('.')
    .filter(Boolean)
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join(' ')
}

const eventTypeOptions = computed(() => {
  const set = new Set<string>()
  const counts = stats.value?.type_counts || {}
  Object.keys(counts).forEach((k: string) => set.add(k))
  events.value.forEach((e: any) => e.event_type && set.add(e.event_type))
  return Array.from(set).sort().map((t) => ({ value: t, label: typeLabel(t) }))
})

const statCards = computed(() => [
  { label: '总事件数', value: String(stats.value?.event_count ?? '—') },
  { label: '应用总时长', value: stats.value?.total_minutes ? `${stats.value.total_minutes} min` : '—' },
  { label: '剪贴板次数', value: String(stats.value?.clipboard_count ?? '—') },
  { label: '最常用应用', value: friendlyApp(stats.value?.top_app ?? '—') as string },
])

const typeCountEntries = computed(() => {
  const counts = stats.value?.type_counts || {}
  return Object.entries(counts)
    .sort((a: any, b: any) => b[1] - a[1])
    .map(([type, count]) => ({ type, count: count as number }))
    .slice(0, 12)
})

function barWidth(minutes: number): number {
  const max = Math.max(...(stats.value?.app_minutes || []).map((a: any) => a.minutes), 1)
  return Math.round((minutes / max) * 100)
}

const APP_ALIASES: Record<string, string> = {
  code: 'VSCode', 'code-insiders': 'VSCode', cursor: 'Cursor',
  chrome: 'Chrome', msedge: 'Edge', firefox: 'Firefox', opera: 'Opera',
  explorer: '资源管理器', wechat: '微信', qq: 'QQ', wecom: '企业微信',
  dingtalk: '钉钉', feishu: '飞书', lark: '飞书',
  devenv: 'Visual Studio', idea64: 'IntelliJ IDEA', pycharm64: 'PyCharm',
  webstorm64: 'WebStorm', goland64: 'GoLand', studio64: 'Android Studio',
  windowsterminal: '终端', cmd: '命令行', powershell: 'PowerShell',
  node: 'Node.js', python: 'Python', java: 'Java', slack: 'Slack', teams: 'Teams', zoom: 'Zoom',
}
function friendlyApp(name: string): string {
  return APP_ALIASES[String(name || '').toLowerCase()] || name
}

function detailText(d: any): string {
  if (!d) return ''
  const parts: string[] = []
  if (d.app) parts.push(friendlyApp(d.app))
  if (d.title) parts.push(String(d.title).slice(0, 40))
  if (d.minutes) parts.push(`${d.minutes} 分钟`)
  if (d.length) parts.push(`长度 ${d.length}`)
  if (d.preview) parts.push(`「${String(d.preview).slice(0, 30)}…」`)
  return parts.join(' · ')
}

function tagType(t: string): string {
  if (t.includes('file') || t.includes('app')) return 'primary'
  if (t.includes('mail') || t.includes('article') || t.includes('rss')) return 'success'
  if (t.includes('todo') || t.includes('schedule') || t.includes('briefing')) return 'warning'
  if (t.includes('clipboard')) return 'info'
  return 'danger'
}

function formatTime(iso: string) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

async function loadStats() {
  try {
    const r = await client.get('/activities/stats', { params: { days: days.value || 30 } })
    stats.value = r.data || {}
  } catch { stats.value = {} }
}

async function loadEvents() {
  loading.value = true
  try {
    const r = await client.get('/activities', {
      params: {
        limit: pageSize,
        event_type: eventType.value || undefined,
        days: days.value || undefined,
      },
    })
    events.value = r.data || []
    hasMore.value = events.value.length >= pageSize
  } catch { events.value = [] } finally { loading.value = false }
}

async function loadMore() {
  if (loadingMore.value) return
  loadingMore.value = true
  try {
    page.value += 1
    const r = await client.get('/activities', {
      params: {
        limit: pageSize,
        offset: (page.value - 1) * pageSize,
        event_type: eventType.value || undefined,
        days: days.value || undefined,
      },
    })
    const more = r.data || []
    events.value.push(...more)
    hasMore.value = more.length >= pageSize
  } catch { hasMore.value = false } finally { loadingMore.value = false }
}

async function loadAll() {
  page.value = 1
  await Promise.all([loadStats(), loadEvents()])
}

onMounted(loadAll)
</script>

<style scoped>
.stat-card { background:#fff; border-radius:10px; border:1px solid var(--color-border); padding:20px; text-align:center; }
.stat-value { font-size:26px; font-weight:700; color:#1a1a2e; }
.stat-label { font-size:12px; color:#909399; margin-top:4px; }
.list-toolbar { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:8px; }
.app-bars { display:flex; flex-direction:column; gap:8px; }
.app-bar-row { display:flex; align-items:center; gap:8px; font-size:12px; }
.app-bar-name { width:90px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#333; }
.app-bar-track { flex:1; height:10px; background:#eef0f4; border-radius:5px; overflow:hidden; }
.app-bar-fill { height:100%; background:linear-gradient(90deg,#6366f1,#8b5cf6); border-radius:5px; transition:width .3s; }
.app-bar-min { width:50px; text-align:right; color:#909399; }
.type-list { display:flex; flex-direction:column; gap:6px; }
.type-row { display:flex; justify-content:space-between; align-items:center; padding:4px 8px; border-radius:6px; font-size:12px; }
.type-row:nth-child(odd) { background:#f8f9fa; }
.type-label { color:#333; }
.type-count { color:#6366f1; font-weight:600; }
</style>
