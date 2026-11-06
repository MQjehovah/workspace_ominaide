<template>
  <div class="page-wrapper">
    <div class="page-header" style="display:flex;align-items:center;justify-content:space-between">
      <h2>日程</h2>
      <div class="header-actions">
        <el-select v-model="sourceFilter" size="small" style="width:120px" @change="fetchEvents">
          <el-option label="全部来源" value="" />
          <el-option label="钉钉" value="dingtalk" />
          <el-option label="手动" value="manual" />
          <el-option label="助手" value="agent" />
        </el-select>
        <el-button type="primary" @click="openAdd">添加日程</el-button>
      </div>
    </div>
    <div class="page-card">
      <div class="page-card-body">
        <el-calendar v-model="currentDate">
          <template #date-cell="{ data }">
            <div class="cal-cell" @click="selectDate(data.day)">
              <span>{{ data.day.split('-').pop()?.replace(/^0/, '') }}</span>
              <div class="cal-dots">
                <span v-for="e in getDayEvents(data.day)" :key="e.id" class="cal-dot" :style="{ background: e.color || '#409EFF' }" />
              </div>
            </div>
          </template>
        </el-calendar>
      </div>
    </div>

    <el-drawer v-model="drawerVisible" :title="selectedDate" size="460px">
      <div v-if="dayEvents.length === 0" style="text-align:center;color:#909399;padding:40px">暂无日程</div>
      <div v-for="e in dayEvents" :key="e.id" class="event-card" :style="{ borderLeftColor: e.color || '#409EFF' }">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">
          <div style="min-width:0">
            <div class="event-title">
              {{ e.title }}
              <el-tag size="small" :type="sourceTagType(e.source)" effect="plain">{{ sourceLabel(e.source) }}</el-tag>
              <el-tag v-if="e.status === 'cancelled'" size="small" type="info" effect="plain">已取消</el-tag>
            </div>
            <div class="event-time">{{ formatTime(e.start_time) }}<template v-if="e.end_time"> — {{ formatTime(e.end_time) }}</template></div>
            <div v-if="e.location" class="event-meta">地点：{{ e.location }}</div>
            <div v-if="e.source === 'dingtalk'" class="event-meta">
              <span v-if="e.external_meta?.organizer">组织者：{{ e.external_meta.organizer }}</span>
              <span v-if="e.external_meta?.attendees?.length"> · 参会：{{ e.external_meta.attendees.map((a: any) => a.name).filter(Boolean).slice(0, 5).join('、') }}</span>
              <span v-if="e.external_meta?.rooms?.length"> · 会议室：{{ e.external_meta.rooms.map((r: any) => r.name).filter(Boolean).join('、') }}</span>
              <span v-if="e.external_meta?.meeting_room_code"> · 会议号 {{ e.external_meta.meeting_room_code }}</span>
              <a v-if="e.external_meta?.meeting_url" :href="e.external_meta.meeting_url" target="_blank" rel="noopener" class="meeting-link">加入会议</a>
            </div>
            <div v-if="e.notes" class="event-meta">备注：{{ e.notes }}</div>
          </div>
          <div class="event-actions">
            <el-button link size="small" @click="askAssistant(e)">让助手处理</el-button>
            <el-button link size="small" @click="openEdit(e)">编辑</el-button>
            <el-popconfirm title="确定删除？" @confirm="deleteEvent(e.id)">
              <template #reference><el-button link type="danger" size="small">删除</el-button></template>
            </el-popconfirm>
          </div>
        </div>
        <div class="event-comment-toggle">
          <el-button link size="small" @click="toggleComments(e.id)">
            {{ expandedComments.has(e.id) ? '收起评论与材料' : '评论与材料' }}
          </el-button>
        </div>
        <ObjectComments
          v-if="expandedComments.has(e.id)"
          type="schedule_event"
          :object-id="e.id"
          :title="e.title"
        />
      </div>
    </el-drawer>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑日程' : '添加日程'" width="480px">
      <el-form ref="formRef" :model="form" label-width="80px" :rules="rules">
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" />
        </el-form-item>
        <el-form-item label="开始时间" prop="start_time">
          <el-date-picker v-model="form.start_time" type="datetime" placeholder="选择日期时间" format="YYYY-MM-DD HH:mm" value-format="x" style="width:100%" />
        </el-form-item>
        <el-form-item label="结束时间">
          <el-date-picker v-model="form.end_time" type="datetime" placeholder="可选" format="YYYY-MM-DD HH:mm" value-format="x" style="width:100%" clearable />
        </el-form-item>
        <el-form-item label="颜色">
          <el-color-picker v-model="form.color" />
        </el-form-item>
        <el-form-item label="地点">
          <el-input v-model="form.location" placeholder="可选" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.notes" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="提醒">
          <el-select v-model="form.remind_before" style="width:100%">
            <el-option :value="0" label="不提醒" />
            <el-option :value="10" label="10 分钟前" />
            <el-option :value="30" label="30 分钟前" />
            <el-option :value="60" label="1 小时前" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEvent">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import client from '@/api/client'
import { parseLocalDate } from '@/utils/date'
import ObjectComments from '@/components/ObjectComments.vue'

interface ScheduleEvent {
  id: number
  title: string
  start_time: string
  end_time?: string
  notes?: string
  color?: string
  remind_before?: number
  source?: string
  external_id?: string
  external_meta?: any
  location?: string
  status?: string
  last_synced_at?: string
}

const route = useRoute()
const router = useRouter()
const currentDate = ref(new Date())
const events = ref<ScheduleEvent[]>([])
const drawerVisible = ref(false)
const dialogVisible = ref(false)
const selectedDate = ref('')
const editing = ref<ScheduleEvent | null>(null)
const saving = ref(false)
const formRef = ref<any>(null)
const sourceFilter = ref('')
const expandedComments = ref(new Set<number>())

const form = ref<{
  title: string
  start_time: number | null
  end_time: number | null
  color: string
  notes: string
  location: string
  remind_before: number
}>({
  title: '',
  start_time: null,
  end_time: null,
  color: '#409EFF',
  notes: '',
  location: '',
  remind_before: 0,
})

const rules = {
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
  start_time: [{ required: true, message: '请选择开始时间', trigger: 'change' }],
}

function getMonthRange(date: Date) {
  const year = date.getFullYear()
  const month = date.getMonth()
  const start = new Date(year, month, 1)
  const end = new Date(year, month + 1, 0, 23, 59, 59, 999)
  return { start: start.toISOString(), end: end.toISOString() }
}

async function fetchEvents() {
  try {
    const { start, end } = getMonthRange(currentDate.value)
    const res = await client.get('/schedule', {
      params: {
        start,
        end,
        ...(sourceFilter.value ? { source: sourceFilter.value } : {}),
      },
    })
    events.value = res.data || []
  } catch {
    events.value = []
  }
}

watch(currentDate, fetchEvents)

const dayEvents = computed(() =>
  events.value.filter(e => e.start_time?.startsWith(selectedDate.value))
)

function getDayEvents(day: string) {
  return events.value.filter(e => e.start_time?.startsWith(day))
}

function formatTime(iso: string) {
  if (!iso) return ''
  const d = parseLocalDate(iso)
  if (isNaN(d.getTime())) return ''
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function selectDate(date: string) {
  selectedDate.value = date
  drawerVisible.value = true
}

function sourceLabel(source?: string) {
  return ({ dingtalk: '钉钉', agent: '助手', manual: '手动' } as Record<string, string>)[source || 'manual'] || '手动'
}

function sourceTagType(source?: string) {
  if (source === 'dingtalk') return 'primary'
  if (source === 'agent') return 'success'
  return 'info'
}

function toggleComments(id: number) {
  if (expandedComments.value.has(id)) expandedComments.value.delete(id)
  else expandedComments.value.add(id)
}

function askAssistant(event: ScheduleEvent) {
  router.push({ path: '/chat', query: { ref: `schedule_event:${event.id}` } })
}

async function openFromRoute() {
  const id = Number(route.query.event)
  if (!Number.isFinite(id) || id <= 0) return
  try {
    const { data } = await client.get(`/objects/schedule_event/${id}`)
    const day = String(data.time || '').slice(0, 10)
    if (day) {
      currentDate.value = new Date(`${day}T12:00:00`)
      selectedDate.value = day
      await fetchEvents()
    }
    const event = events.value.find((item) => item.id === id)
    if (event) selectedDate.value = event.start_time.slice(0, 10)
    expandedComments.value.add(id)
    drawerVisible.value = true
  } catch {
    // Ignore an invalid or deleted event reference.
  }
}

function openAdd() {
  editing.value = null
  form.value = { title: '', start_time: null, end_time: null, color: '#409EFF', notes: '', location: '', remind_before: 0 }
  dialogVisible.value = true
}

function openEdit(e: ScheduleEvent) {
  editing.value = e
  form.value = {
    title: e.title,
    start_time: e.start_time ? new Date(e.start_time).getTime() : null,
    end_time: e.end_time ? new Date(e.end_time).getTime() : null,
    color: e.color || '#409EFF',
    notes: e.notes || '',
    location: e.location || '',
    remind_before: e.remind_before ?? 0,
  }
  dialogVisible.value = true
}

async function saveEvent() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    const payload: Record<string, any> = {
      title: form.value.title,
      start_time: new Date(form.value.start_time!).toISOString(),
      color: form.value.color,
      notes: form.value.notes,
      location: form.value.location || undefined,
      remind_before: form.value.remind_before,
    }
    if (form.value.end_time) {
      payload.end_time = new Date(form.value.end_time).toISOString()
    }
    if (editing.value) {
      await client.put(`/schedule/${editing.value.id}`, payload)
    } else {
      await client.post('/schedule', payload)
    }
    dialogVisible.value = false
    await fetchEvents()
  } finally {
    saving.value = false
  }
}

async function deleteEvent(id: number) {
  try {
    await client.delete(`/schedule/${id}`)
    drawerVisible.value = false
    await fetchEvents()
  } catch {
    //
  }
}

onMounted(async () => {
  await fetchEvents()
  await openFromRoute()
})
</script>

<style scoped>
.cal-cell { cursor: pointer; }
.cal-dots { display: flex; gap: 3px; justify-content: center; margin-top: 2px; }
.cal-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.header-actions { display: flex; align-items: center; gap: 8px; }
.event-card { border-left: 3px solid; padding: 12px; margin-bottom: 10px; border-radius: 6px; background: #fafafa; }
.event-title { font-weight: 600; font-size: 14px; color: #1a1a2e; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.event-time { font-size: 12px; color: #909399; margin-top: 4px; }
.event-meta { font-size: 12px; color: #666; margin-top: 5px; line-height: 1.6; }
.meeting-link { margin-left: 6px; color: #4f46e5; text-decoration: none; }
.event-actions { display: flex; gap: 2px; flex-shrink: 0; flex-wrap: wrap; justify-content: flex-end; max-width: 150px; }
.event-comment-toggle { margin-top: 8px; padding-top: 6px; border-top: 1px dashed #e7eaf1; }
</style>
