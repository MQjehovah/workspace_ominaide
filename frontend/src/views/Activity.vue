<template>
  <div class="page-wrapper activity-page">
    <div class="page-header">
      <div>
        <h2>活动</h2>
        <div class="muted">事件分布与内容，不再展示应用使用统计</div>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="loadStats">刷新</el-button>
    </div>

    <div class="summary-grid">
      <div class="summary-card">
        <div class="summary-value">{{ stats.event_count ?? '—' }}</div>
        <div class="summary-label">事件总数</div>
      </div>
      <div class="summary-card">
        <div class="summary-value">{{ stats.type_count ?? '—' }}</div>
        <div class="summary-label">事件类型</div>
      </div>
      <div class="summary-card summary-note">
        <div class="summary-value small">{{ days }} 天</div>
        <div class="summary-label">统计范围</div>
      </div>
    </div>

    <div class="page-card block">
      <div class="card-head">
        <div>
          <h3>事件类型分布</h3>
          <span class="card-sub">按事件数量排序</span>
        </div>
        <el-select v-model="days" size="small" style="width:120px" @change="loadStats">
          <el-option label="近 1 天" :value="1" />
          <el-option label="近 7 天" :value="7" />
          <el-option label="近 30 天" :value="30" />
          <el-option label="全部" :value="90" />
        </el-select>
      </div>
      <div class="card-body">
        <div v-if="typeCountEntries.length" class="type-list">
          <div v-for="t in typeCountEntries" :key="t.type" class="type-row">
            <div class="type-row-head">
              <span class="type-label">{{ typeLabel(t.type) }}</span>
              <span class="type-count">{{ t.count }}</span>
            </div>
            <div class="type-track">
              <div class="type-fill" :style="{ width: typeWidth(t.count) + '%' }"></div>
            </div>
          </div>
        </div>
        <p v-else class="empty-hint">暂无事件</p>
      </div>
    </div>

    <div class="page-card block">
      <div class="card-head">
        <div>
          <h3>最近事件</h3>
          <span class="card-sub">只展示最近 6 条，完整内容请查看全部</span>
        </div>
        <el-button size="small" @click="openAll">查看全部</el-button>
      </div>
      <div class="card-body">
        <div v-if="previewEvents.length" class="event-preview">
          <div v-for="e in previewEvents" :key="e.id" class="event-row">
            <el-tag :type="tagType(e.event_type)" size="small">{{ typeLabel(e.event_type) }}</el-tag>
            <div class="event-main">
              <div class="event-summary">{{ e.summary || typeLabel(e.event_type) }}</div>
              <div class="event-detail">{{ detailText(e.details) }}</div>
            </div>
            <span class="event-time">{{ formatTime(e.created_at) }}</span>
          </div>
        </div>
        <p v-else class="empty-hint">暂无事件</p>
      </div>
    </div>

    <el-drawer v-model="drawerVisible" title="全部活动事件" size="72%" destroy-on-close>
      <div class="drawer-toolbar">
        <el-select v-model="eventType" placeholder="全部类型" clearable size="small" style="width:180px" @change="page = 1; loadPage()">
          <el-option v-for="t in eventTypeOptions" :key="t.value" :label="t.label" :value="t.value" />
        </el-select>
        <el-select v-model="drawerDays" placeholder="时间范围" size="small" style="width:120px" @change="page = 1; loadPage()">
          <el-option label="近 1 天" :value="1" />
          <el-option label="近 7 天" :value="7" />
          <el-option label="近 30 天" :value="30" />
          <el-option label="全部" :value="90" />
        </el-select>
        <el-button size="small" :icon="Refresh" @click="loadPage" :loading="pageLoading">刷新</el-button>
        <span class="drawer-total">共 {{ total }} 条</span>
      </div>

      <el-table :data="pageEvents" stripe size="small" v-loading="pageLoading">
        <el-table-column label="类型" width="140">
          <template #default="{ row }">
            <el-tag :type="tagType(row.event_type)" size="small">{{ typeLabel(row.event_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="summary" label="内容" min-width="220" show-overflow-tooltip />
        <el-table-column label="详情" min-width="220">
          <template #default="{ row }">
            <span class="table-detail">{{ detailText(row.details) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>

      <div class="drawer-pager">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next, total"
          @current-change="loadPage"
        />
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import client from '@/api/client'
import { Refresh } from '@element-plus/icons-vue'
import { formatLocalDate, parseBackendDate } from '@/utils/date'

const loading = ref(false)
const pageLoading = ref(false)
const stats = ref<any>({})
const previewEvents = ref<any[]>([])
const pageEvents = ref<any[]>([])
const drawerVisible = ref(false)
const days = ref(7)
const drawerDays = ref(7)
const eventType = ref('')
const page = ref(1)
const pageSize = 20
const total = ref(0)

const TYPE_LABELS: Record<string, string> = {
  'app.used': '应用使用',
  'clipboard.copy': '剪贴板复制',
  'file.uploaded': '文件上传', 'file.trashed': '文件删除',
  'file.renamed': '文件重命名', 'file.moved': '文件移动',
  'note.created': '笔记创建', 'note.updated': '笔记更新', 'note.deleted': '笔记删除',
  'todo.created': '待办创建', 'todo.updated': '待办修改', 'todo.deleted': '待办删除',
  'schedule.created': '日程创建', 'schedule.updated': '日程修改', 'schedule.deleted': '日程删除',
  'sources.subscribed': '添加资讯源', 'sources.unsubscribed': '删除资讯源', 'sources.refreshed': '资讯源刷新',
  'sources.item.new': '资讯源新内容',
  'mail.received': '邮件收取',
  'playlist.created': '歌单创建', 'playlist.deleted': '歌单删除',
  'notifications.read': '通知已读', 'notifications.read-all': '通知全部已读',
  'mcp.tool.called': 'MCP 工具调用', 'mcp.call.created': 'MCP 工具调用',
  'mcp.servers.created': 'MCP 服务', 'mcp.servers.updated': 'MCP 服务', 'mcp.servers.deleted': 'MCP 服务',
  'approval.decided': '审批决定', 'approvals.decision.created': '审批决定',
  'memory.candidate.approved': '记忆通过', 'memory.candidate.rejected': '记忆忽略',
  'memory.candidates.created': '记忆审核', 'memory.extract.created': '记忆整理',
  'bot.run.finished': 'Bot 运行', 'bot.run.failed': 'Bot 运行', 'bot.run.cancelled': 'Bot 运行',
  'bots.created': 'Bot 管理', 'bots.updated': 'Bot 管理', 'bots.deleted': 'Bot 管理',
  'bots.routines.created': 'Bot 例行任务', 'bots.routines.updated': 'Bot 例行任务',
  'bots.routines.deleted': 'Bot 例行任务', 'bots.runs.created': 'Bot 运行',
  'bots.memories.created': 'Bot 记忆', 'bots.memories.deleted': 'Bot 记忆',
  'automation.from-template.created': '自动化任务', 'runs.cancel.created': '运行取消',
  'device.briefing.created': '简报触发', 'device.tts.created': '语音播报',
  'device.gesture.created': '手势控制',
  'note.imported': '知识导入', 'note.restored': '笔记恢复', 'todo.completed': '待办完成',
  'search': '搜索', 'activities.created': '活动上报', 'briefing': '每日简报',
}

function typeLabel(t: string): string {
  if (TYPE_LABELS[t]) return TYPE_LABELS[t]
  return t
    .split('.')
    .filter(Boolean)
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join(' ')
}

const eventTypeOptions = computed(() => {
  const set = new Set<string>()
  Object.keys(stats.value?.type_counts || {}).forEach((k) => set.add(k))
  return Array.from(set).sort().map((t) => ({ value: t, label: typeLabel(t) }))
})

const typeCountEntries = computed(() => {
  const counts = stats.value?.type_counts || {}
  return Object.entries(counts)
    .sort((a: any, b: any) => b[1] - a[1])
    .map(([type, count]) => ({ type, count: count as number }))
    .slice(0, 12)
})

function typeWidth(count: number): number {
  const max = Math.max(...typeCountEntries.value.map((t) => t.count), 1)
  return Math.max(4, Math.round((count / max) * 100))
}

function tagType(t: string): string {
  if (t.includes('file') || t.includes('app')) return 'primary'
  if (t.includes('mail') || t.includes('article') || t.includes('rss') || t.includes('sources')) return 'success'
  if (t.includes('todo') || t.includes('schedule') || t.includes('briefing')) return 'warning'
  if (t.includes('clipboard')) return 'info'
  return 'danger'
}

function formatTime(iso: string) {
  if (!iso) return ''
  const d = parseBackendDate(iso)
  if (isNaN(d.getTime())) return ''
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function detailText(d: any): string {
  if (!d) return ''
  const clip = (v: any, n = 60) => {
    const text = String(v ?? '').replace(/\s+/g, ' ').trim()
    return text.length > n ? `${text.slice(0, n)}…` : text
  }
  const parts: string[] = []
  if (d.title) parts.push(clip(d.title, 40))
  if (d.start_time) parts.push(`开始 ${clip(formatLocalDate(d.start_time), 16)}`)
  if (d.end_time) parts.push(`结束 ${clip(formatLocalDate(d.end_time), 16)}`)
  if (d.due_date) parts.push(`截止 ${clip(formatLocalDate(d.due_date), 16)}`)
  if (d.source) parts.push(`来源 ${clip(d.source, 12)}`)
  if (d.filename) parts.push(`文件 ${clip(d.filename, 30)}`)
  if (d.url) parts.push(`链接 ${clip(d.url, 40)}`)
  if (d.tool_name) parts.push(`工具 ${d.tool_name}`)
  if (d.reason) parts.push(`原因：${clip(d.reason, 40)}`)
  if (d.input) parts.push(`输入：${clip(d.input, 50)}`)
  if (d.output) parts.push(`输出：${clip(d.output, 60)}`)
  if (d.error) parts.push(`错误：${clip(d.error, 50)}`)
  if (d.notes) parts.push(`备注：${clip(d.notes, 40)}`)
  if (d.description) parts.push(`描述：${clip(d.description, 40)}`)
  if (d.status) parts.push(`状态 ${d.status}`)
  if (d.minutes) parts.push(`${d.minutes} 分钟`)
  if (d.preview) parts.push(`「${clip(d.preview, 30)}」`)
  if (d.method && d.path) parts.push(`${d.method} ${d.path}`)
  return parts.join(' · ')
}

async function loadStats() {
  loading.value = true
  try {
    const [statsRes, previewRes] = await Promise.all([
      client.get('/activities/stats', { params: { days: days.value } }),
      client.get('/activities/page', { params: { page: 1, page_size: 6, days: days.value } }),
    ])
    stats.value = statsRes.data || {}
    previewEvents.value = previewRes.data?.items || []
  } catch {
    stats.value = {}
    previewEvents.value = []
  } finally {
    loading.value = false
  }
}

function openAll() {
  drawerVisible.value = true
  page.value = 1
  eventType.value = ''
  drawerDays.value = days.value
  loadPage()
}

async function loadPage() {
  pageLoading.value = true
  try {
    const res = await client.get('/activities/page', {
      params: {
        page: page.value,
        page_size: pageSize,
        event_type: eventType.value || undefined,
        days: drawerDays.value || undefined,
      },
    })
    pageEvents.value = res.data?.items || []
    total.value = Number(res.data?.total || 0)
  } catch {
    pageEvents.value = []
    total.value = 0
  } finally {
    pageLoading.value = false
  }
}

onMounted(loadStats)
</script>

<style scoped>
.activity-page { max-width: 1180px; }
.muted { font-size: 12px; color: #909399; }
.summary-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
.summary-card { background: #fff; border: 1px solid var(--color-border); border-radius: 12px; padding: 16px 18px; }
.summary-value { font-size: 26px; line-height: 1.1; font-weight: 700; color: #111827; }
.summary-value.small { font-size: 20px; }
.summary-label { margin-top: 5px; font-size: 12px; color: #909399; }
.block { margin-bottom: 16px; }
.card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 18px 20px 0; }
.card-head h3 { margin: 0; font-size: 14.5px; font-weight: 600; color: #111827; }
.card-sub { display: block; margin-top: 4px; font-size: 11.5px; color: #9aa5b8; }
.card-body { padding: 16px 20px 20px; }
.type-list { display: flex; flex-direction: column; gap: 11px; }
.type-row-head { display: flex; justify-content: space-between; align-items: center; font-size: 12px; margin-bottom: 4px; }
.type-label { color: #4b5563; }
.type-count { color: #4f46e5; font-weight: 700; font-variant-numeric: tabular-nums; }
.type-track { height: 7px; border-radius: 5px; background: #eef0f4; overflow: hidden; }
.type-fill { height: 100%; border-radius: 5px; background: linear-gradient(90deg, #6366f1, #8b5cf6); }
.event-preview { display: flex; flex-direction: column; }
.event-row { display: grid; grid-template-columns: 110px 1fr 150px; align-items: start; gap: 12px; padding: 11px 0; border-bottom: 1px dashed #f0f2f5; }
.event-row:last-child { border-bottom: none; }
.event-main { min-width: 0; }
.event-summary { font-size: 13px; color: #303133; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.event-detail { margin-top: 3px; font-size: 11.5px; color: #909399; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.event-time { font-size: 11.5px; color: #a0a4ad; text-align: right; padding-top: 2px; }
.empty-hint { margin: 0; padding: 28px 0; text-align: center; color: #909399; font-size: 12px; }
.drawer-toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
.drawer-total { margin-left: auto; font-size: 12px; color: #909399; }
.table-detail { font-size: 12px; color: #666; }
.drawer-pager { display: flex; justify-content: flex-end; padding-top: 16px; }
@media (max-width: 800px) {
  .summary-grid { grid-template-columns: 1fr; }
  .event-row { grid-template-columns: 1fr; gap: 5px; }
  .event-time { text-align: left; }
}
</style>
