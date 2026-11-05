<template>
  <div class="page-wrapper dashboard">
    <div class="view-switch">
      <button :class="{ active: view === 'overview' }" @click="setView('overview')">概览</button>
      <button :class="{ active: view === 'cos' }" @click="setView('cos')">幕僚长</button>
      <span class="switch-hint">收件箱 · 简报 · 会议准备 · 周报</span>
    </div>

    <template v-if="view === 'overview'">
    <section class="hero">
      <div class="hero-main">
        <div class="hero-kicker">{{ greeting }}，{{ displayName }}</div>
        <h1>今天 · {{ dateText }}</h1>
        <p class="hero-sub">
          {{ todayEvents.length ? `${todayEvents.length} 个日程` : '今天没有日程' }}
          · {{ pendingTodos.length }} 个待办
          · {{ unread }} 条未读
        </p>
        <div class="hero-actions">
          <el-button type="primary" :icon="Cpu" @click="router.push('/projects')">打开项目</el-button>
          <el-button :icon="Document" @click="router.push('/notes')">写笔记</el-button>
          <el-button :icon="Calendar" @click="router.push('/schedule')">看日程</el-button>
        </div>
      </div>
      <div class="hero-side">
        <div class="hero-ring"></div>
        <div class="hero-badge">
          <span class="hero-badge-value">{{ counts.files }}</span>
          <span class="hero-badge-label">文件</span>
        </div>
      </div>
    </section>

    <div class="stat-grid">
      <button v-for="s in stats" :key="s.label" class="stat-card" @click="router.push(s.path)">
        <el-icon class="stat-icon" :style="{ color: s.color, background: s.bg }">
          <component :is="s.icon" />
        </el-icon>
        <div class="stat-body">
          <div class="stat-value">{{ s.value }}</div>
          <div class="stat-label">{{ s.label }}</div>
        </div>
        <el-icon class="stat-arrow"><ArrowRight /></el-icon>
      </button>
    </div>

    <el-row :gutter="16">
      <el-col :xs="24" :lg="15">
        <div class="page-card block">
          <div class="card-head">
            <div>
              <h3>今日日程</h3>
              <span class="card-sub">{{ todayEvents.length ? '按时间顺序' : '今天可以专注做自己的事' }}</span>
            </div>
            <el-button link @click="router.push('/schedule')">全部日程</el-button>
          </div>
          <div class="card-body">
            <div v-if="todayEvents.length" class="timeline">
              <div v-for="e in todayEvents" :key="e.id" class="timeline-item">
                <span class="timeline-dot" :style="{ background: e.color || '#409EFF' }"></span>
                <div class="timeline-time">{{ eventTime(e.start_time) }}</div>
                <div class="timeline-main">
                  <div class="timeline-title">{{ e.title }}</div>
                  <div v-if="e.notes" class="timeline-note">{{ e.notes }}</div>
                </div>
              </div>
            </div>
            <div v-else class="empty">
              <el-icon :size="28"><Calendar /></el-icon>
              <p>今天没有安排，适合推进想做的事。</p>
            </div>
          </div>
        </div>

        <div class="page-card block">
          <div class="card-head">
            <div>
              <h3>待办</h3>
              <span class="card-sub">{{ pendingTodos.length ? `还有 ${pendingTodos.length} 项未完成` : '全部完成' }}</span>
            </div>
            <el-button link @click="router.push('/apps/todo')">查看待办</el-button>
          </div>
          <div class="card-body">
            <div v-if="pendingTodos.length" class="todo-list">
              <button v-for="t in pendingTodos.slice(0, 5)" :key="t.id" class="todo-item" @click="toggleTodo(t)">
                <span class="todo-check"><el-icon><Check /></el-icon></span>
                <span class="todo-title">{{ t.title }}</span>
                <span v-if="t.due_date" class="todo-due">{{ shortDate(t.due_date) }}</span>
              </button>
            </div>
            <div v-else class="empty">
              <el-icon :size="28"><Check /></el-icon>
              <p>待办已清空。</p>
            </div>
          </div>
        </div>

        <div class="page-card block">
          <div class="card-head">
            <div>
              <h3>最近活动</h3>
              <span class="card-sub">来自你的数字足迹</span>
            </div>
            <el-button link @click="router.push('/activities')">全部活动</el-button>
          </div>
          <div class="card-body">
            <div v-if="events.length" class="activity-list">
              <div v-for="e in events" :key="e.id" class="activity-item">
                <span class="activity-dot"></span>
                <div class="activity-main">
                  <div class="activity-summary">{{ e.summary || e.event_type }}</div>
                  <div class="activity-meta">{{ e.event_type }} · {{ relTime(e.created_at) }}</div>
                </div>
              </div>
            </div>
            <div v-else class="empty">
              <el-icon :size="28"><TrendCharts /></el-icon>
              <p>还没有活动。</p>
            </div>
          </div>
        </div>
      </el-col>

      <el-col :xs="24" :lg="9">
        <div class="page-card block">
          <div class="card-head">
            <div>
              <h3>快捷入口</h3>
              <span class="card-sub">常用功能一步直达</span>
            </div>
          </div>
          <div class="card-body">
            <div class="quick-grid">
              <button v-for="q in quickLinks" :key="q.path" class="quick-item" @click="router.push(q.path)">
                <el-icon :size="20"><component :is="q.icon" /></el-icon>
                <span>{{ q.label }}</span>
              </button>
            </div>
          </div>
        </div>

        <div class="page-card block">
          <div class="card-head">
            <div>
              <h3>系统状态</h3>
              <span class="card-sub">后端与数据节点</span>
            </div>
            <el-tag :type="connected ? 'success' : 'danger'" size="small" effect="light">
              {{ connected ? '在线' : '离线' }}
            </el-tag>
          </div>
          <div class="card-body">
            <div class="info-row"><span class="info-label">后端版本</span><span>{{ serverVersion || '-' }}</span></div>
            <div class="info-row"><span class="info-label">数据节点</span><span>{{ today }}</span></div>
            <div class="info-row"><span class="info-label">未读通知</span><span>{{ unread }}</span></div>
          </div>
        </div>

        <div v-if="codingTasks.length" class="page-card block">
          <div class="card-head">
            <div>
              <h3>最近 Coding Run</h3>
              <span class="card-sub">来自 Bot 的 coding 能力</span>
            </div>
            <el-button link @click="router.push('/projects')">打开</el-button>
          </div>
          <div class="card-body">
            <div v-for="t in codingTasks.slice(0, 4)" :key="t.id" class="coding-item">
              <div class="coding-title">{{ t.project_path || t.branch || 'Coding Run' }}</div>
              <div class="coding-meta">
                <el-tag size="small" :type="t.status === 'running' ? 'warning' : (t.status === 'failed' ? 'danger' : 'success')">
                  {{ t.status }}
                </el-tag>
                <span>{{ t.branch || 'feature/*' }}</span>
              </div>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
    </template>

    <ChiefOfStaff v-else embedded />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ChiefOfStaff from './ChiefOfStaff.vue'
import {
  ArrowRight, Bell, Calendar, Check, Cpu, Document, Folder, Promotion, TrendCharts,
} from '@element-plus/icons-vue'
import client from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { formatBackendDate, relTime } from '@/utils/date'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

type DashView = 'overview' | 'cos'
const view = ref<DashView>(route.query.tab === 'cos' ? 'cos' : 'overview')

function setView(next: DashView) {
  view.value = next
  router.replace({ path: '/dashboard', query: next === 'cos' ? { tab: 'cos' } : {} })
}

watch(() => route.query.tab, (tab) => {
  const next: DashView = tab === 'cos' ? 'cos' : 'overview'
  if (next !== view.value) view.value = next
})

const displayName = computed(() => auth.user?.username || '朋友')
const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 11) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})
const dateText = computed(() => new Intl.DateTimeFormat('zh-CN', {
  month: 'long', day: 'numeric', weekday: 'long',
}).format(new Date()))
const today = computed(() => new Intl.DateTimeFormat('zh-CN').format(new Date()))

const counts = reactive({ files: 0, notes: 0, todos: 0, unread: 0 })
const events = ref<any[]>([])
const todayEvents = ref<any[]>([])
const todos = ref<any[]>([])
const codingTasks = ref<any[]>([])
const connected = ref(false)
const serverVersion = ref('')
const unread = ref(0)

const pendingTodos = computed(() => todos.value.filter(t => t.status !== 'done'))

const stats = computed(() => [
  { label: '文件', value: counts.files, icon: Folder, color: '#4f46e5', bg: '#eef2ff', path: '/files' },
  { label: '笔记', value: counts.notes, icon: Document, color: '#7c3aed', bg: '#f5f3ff', path: '/notes' },
  { label: '待办', value: pendingTodos.value.length, icon: Check, color: '#059669', bg: '#ecfdf5', path: '/apps/todo' },
  { label: '未读通知', value: unread.value, icon: Bell, color: '#d97706', bg: '#fffbeb', path: '/notifications' },
])

const quickLinks = [
  { label: '项目', path: '/projects', icon: Cpu },
  { label: '笔记', path: '/notes', icon: Document },
  { label: '日程', path: '/schedule', icon: Calendar },
  { label: '文件', path: '/files', icon: Folder },
  { label: '资讯', path: '/rss', icon: Promotion },
  { label: '活动', path: '/activities', icon: TrendCharts },
]

function eventTime(iso: string) {
  const text = formatBackendDate(iso)
  return text.split(' ')[1] || ''
}

function shortDate(iso: string) {
  const text = formatBackendDate(iso)
  const parts = text.split(' ')
  return parts.length > 1 ? parts[0].slice(5) : text
}

function countNotes(nodes: any[]): number {
  let n = 0
  for (const node of nodes || []) {
    if (!node.is_folder) n++
    n += countNotes(node.children || [])
  }
  return n
}

function todayRange() {
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  const end = new Date(start)
  end.setDate(end.getDate() + 1)
  return { start: start.toISOString(), end: end.toISOString() }
}

async function loadAll() {
  await auth.fetchUser().catch(() => {})
  const range = todayRange()

  await Promise.allSettled([
    client.get('/health').then(r => {
      connected.value = true
      serverVersion.value = r.data?.version || ''
    }).catch(() => { connected.value = false }),

    client.get('/files?page_size=1').then(r => {
      counts.files = Number(r.data?.total ?? r.data?.length ?? 0)
    }),

    client.get('/plugins/notes/tree').then(r => {
      counts.notes = countNotes(r.data)
    }),

    client.get('/plugins/todo/items').then(r => {
      todos.value = Array.isArray(r.data) ? r.data : (r.data?.items || [])
    }),

    client.get('/notifications/unread-count').then(r => {
      unread.value = Number(r.data?.count || 0)
    }),

    client.get('/schedule', { params: range }).then(r => {
      todayEvents.value = Array.isArray(r.data) ? r.data : []
    }),

    client.get('/activities?limit=8').then(r => {
      events.value = Array.isArray(r.data) ? r.data : []
    }),

    client.get('/projects/runs?limit=5').then(r => {
      codingTasks.value = Array.isArray(r.data) ? r.data : []
    }),
  ])
}

async function toggleTodo(t: any) {
  try {
    await client.put(`/plugins/todo/items/${t.id}`, { status: 'done' })
    todos.value = todos.value.filter(x => x.id !== t.id)
  } catch { }
}

function refreshUnread() {
  client.get('/notifications/unread-count')
    .then(r => { unread.value = Number(r.data?.count || 0) })
    .catch(() => {})
}

onMounted(() => {
  loadAll()
  window.addEventListener('omniaide:notification', refreshUnread)
})
onUnmounted(() => {
  window.removeEventListener('omniaide:notification', refreshUnread)
})
</script>

<style scoped>
.dashboard { max-width: 1280px; margin: 0 auto; }
.view-switch {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px; margin-bottom: 16px;
  background: #eef1f8; border-radius: 11px;
}
.view-switch button {
  border: none; background: transparent; cursor: pointer;
  padding: 7px 16px; border-radius: 8px;
  font-size: 13px; color: #64748b;
  transition: background .15s, color .15s, box-shadow .15s;
}
.view-switch button:hover { color: #334155; }
.view-switch button.active {
  background: #fff; color: #111827; font-weight: 600;
  box-shadow: 0 2px 10px -4px rgba(16, 24, 40, .28);
}
.switch-hint { margin-left: 8px; font-size: 11.5px; color: #94a3b8; }
.hero {
  display: flex; align-items: center; justify-content: space-between; gap: 24px;
  padding: 28px 30px; border-radius: 18px; margin-bottom: 18px;
  background:
    radial-gradient(600px 260px at 88% -30%, rgba(168, 85, 247, .4), transparent 62%),
    radial-gradient(520px 240px at 4% 120%, rgba(56, 189, 248, .22), transparent 60%),
    linear-gradient(120deg, #171436 0%, #26205e 48%, #3b1670 100%);
  color: #fff; position: relative; overflow: hidden;
  box-shadow: 0 24px 50px -30px rgba(49, 46, 129, .8);
}
.hero::after {
  content: ''; position: absolute; right: -80px; top: -120px; width: 320px; height: 320px;
  border-radius: 50%; background: radial-gradient(circle, rgba(129,140,248,.35), transparent 68%);
}
.hero-kicker { font-size: 13px; color: #c7d2fe; letter-spacing: .5px; }
.hero h1 { font-size: 30px; font-weight: 700; margin: 8px 0 6px; letter-spacing: -.5px; }
.hero-sub { font-size: 13px; color: rgba(199, 210, 254, .72); }
.hero-actions { display: flex; gap: 10px; margin-top: 18px; flex-wrap: wrap; }
.hero-actions :deep(.el-button) { border-radius: 9px; }
.hero-actions :deep(.el-button:not(.el-button--primary)) {
  background: rgba(255, 255, 255, .1);
  border-color: rgba(255, 255, 255, .2);
  color: #eef2ff;
}
.hero-actions :deep(.el-button:not(.el-button--primary):hover) {
  background: rgba(255, 255, 255, .18);
  border-color: rgba(255, 255, 255, .28);
}
.hero-side { position: relative; width: 120px; height: 120px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.hero-ring {
  position: absolute; inset: 0; border-radius: 50%;
  border: 1px solid rgba(255,255,255,.18);
  box-shadow: inset 0 0 40px rgba(129,140,248,.28);
}
.hero-badge { position: relative; text-align: center; }
.hero-badge-value { display: block; font-size: 28px; font-weight: 700; }
.hero-badge-label { font-size: 12px; color: #c7d2fe; }

.stat-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }
.stat-card {
  display: flex; align-items: center; gap: 12px; padding: 16px 18px; text-align: left;
  background: #fff; border: 1px solid var(--color-border); border-radius: 14px; cursor: pointer;
  box-shadow: 0 1px 2px rgba(16, 24, 40, .03);
  transition: transform .15s, box-shadow .15s, border-color .15s;
}
.stat-card:hover { transform: translateY(-2px); border-color: #dbe3f5; box-shadow: 0 14px 30px -20px rgba(30, 41, 59, .45); }
.stat-icon { width: 40px; height: 40px; border-radius: 11px; font-size: 20px; flex-shrink: 0; }
.stat-body { flex: 1; min-width: 0; }
.stat-value { font-size: 24px; font-weight: 700; color: #111827; line-height: 1.1; font-variant-numeric: tabular-nums; }
.stat-label { font-size: 12px; color: #94a3b8; margin-top: 3px; }
.stat-arrow { color: #cbd5e1; }

.block { margin-bottom: 16px; }
.card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 18px 20px 0; }
.card-head h3 { margin: 0; font-size: 14.5px; font-weight: 600; color: #111827; }
.card-sub { display: block; margin-top: 4px; font-size: 11.5px; color: #9aa5b8; }
.card-body { padding: 16px 20px 20px; }

.timeline { display: flex; flex-direction: column; gap: 2px; }
.timeline-item { display: grid; grid-template-columns: 10px 64px 1fr; align-items: start; gap: 10px; padding: 10px 0; border-bottom: 1px dashed #f0f2f5; }
.timeline-item:last-child { border-bottom: none; }
.timeline-dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 5px; }
.timeline-time { font-size: 12px; color: #8a9099; font-variant-numeric: tabular-nums; padding-top: 1px; }
.timeline-title { font-size: 13px; font-weight: 600; color: #2c3550; }
.timeline-note { font-size: 11px; color: #909399; margin-top: 3px; }

.todo-list { display: flex; flex-direction: column; }
.todo-item { display: flex; align-items: center; gap: 10px; padding: 10px 0; border: none; background: none; cursor: pointer; text-align: left; border-bottom: 1px dashed #f0f2f5; }
.todo-item:last-child { border-bottom: none; }
.todo-check { width: 20px; height: 20px; border-radius: 6px; border: 1.5px solid #d9dde3; display: flex; align-items: center; justify-content: center; color: transparent; flex-shrink: 0; transition: all .15s; }
.todo-item:hover .todo-check { border-color: #10B981; color: #10B981; background: #e8f8f1; }
.todo-title { flex: 1; font-size: 13px; color: #3a4256; }
.todo-due { font-size: 11px; color: #f59e0b; }

.activity-list { display: flex; flex-direction: column; }
.activity-item { display: flex; gap: 10px; padding: 8px 0; border-bottom: 1px dashed #f0f2f5; }
.activity-item:last-child { border-bottom: none; }
.activity-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--brand-500); margin-top: 6px; flex-shrink: 0; }
.activity-summary { font-size: 13px; color: #3a4256; }
.activity-meta { font-size: 11px; color: #a0a4ad; margin-top: 2px; }

.quick-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.quick-item { display: flex; flex-direction: column; align-items: center; gap: 7px; padding: 14px 8px; border-radius: 11px; border: 1px solid #eef0f4; background: #fafbfd; color: #4b5563; font-size: 12px; cursor: pointer; transition: all .15s; }
.quick-item:hover { border-color: #c7d2fe; background: #f5f7ff; color: var(--brand-500); }

.info-row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; font-size: 13px; border-bottom: 1px solid #f5f6f8; }
.info-row:last-child { border-bottom: none; }
.info-label { color: #909399; }

.coding-item { padding: 9px 0; border-bottom: 1px dashed #f0f2f5; }
.coding-item:last-child { border-bottom: none; }
.coding-title { font-size: 13px; color: #2c3550; font-weight: 500; }
.coding-meta { display: flex; align-items: center; gap: 8px; margin-top: 5px; font-size: 11px; color: #a0a4ad; }

.empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 24px 0; color: #b0b5bd; }
.empty p { margin: 0; font-size: 12px; }

@media (max-width: 900px) {
  .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .hero-side { display: none; }
  .hero h1 { font-size: 24px; }
  .switch-hint { display: none; }
  .view-switch { width: 100%; }
  .view-switch button { flex: 1; }
}
@media (max-width: 600px) {
  .hero { flex-direction: column; align-items: flex-start; padding: 20px; }
  .stat-grid { grid-template-columns: 1fr; }
  .quick-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
