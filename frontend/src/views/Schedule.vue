<template>
  <div class="page-wrapper">
    <div class="page-header" style="display:flex;align-items:center;justify-content:space-between">
      <h2>日程</h2>
      <el-button type="primary" @click="openAdd">添加日程</el-button>
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

    <el-drawer v-model="drawerVisible" :title="selectedDate" size="360px">
      <div v-if="dayEvents.length === 0" style="text-align:center;color:#909399;padding:40px">暂无日程</div>
      <div v-for="e in dayEvents" :key="e.id" class="event-card" :style="{ borderLeftColor: e.color || '#409EFF' }">
        <div style="display:flex;justify-content:space-between;align-items:flex-start">
          <div>
            <div style="font-weight:600;font-size:14px;color:#1a1a2e">{{ e.title }}</div>
            <div style="font-size:12px;color:#909399;margin-top:4px">{{ formatTime(e.start_time) }}<template v-if="e.end_time"> — {{ formatTime(e.end_time) }}</template></div>
            <div v-if="e.notes" style="font-size:12px;color:#666;margin-top:6px">{{ e.notes }}</div>
          </div>
          <div style="display:flex;gap:4px;flex-shrink:0">
            <el-button link size="small" @click="openEdit(e)">编辑</el-button>
            <el-popconfirm title="确定删除？" @confirm="deleteEvent(e.id)">
              <template #reference><el-button link type="danger" size="small">删除</el-button></template>
            </el-popconfirm>
          </div>
        </div>
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
import client from '@/api/client'

interface ScheduleEvent {
  id: number
  title: string
  start_time: string
  end_time?: string
  notes?: string
  color?: string
  remind_before?: number
}

const currentDate = ref(new Date())
const events = ref<ScheduleEvent[]>([])
const drawerVisible = ref(false)
const dialogVisible = ref(false)
const selectedDate = ref('')
const editing = ref<ScheduleEvent | null>(null)
const saving = ref(false)
const formRef = ref<any>(null)

const form = ref<{
  title: string
  start_time: number | null
  end_time: number | null
  color: string
  notes: string
  remind_before: number
}>({
  title: '',
  start_time: null,
  end_time: null,
  color: '#409EFF',
  notes: '',
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
    const res = await client.get('/schedule', { params: { start, end } })
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
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function selectDate(date: string) {
  selectedDate.value = date
  drawerVisible.value = true
}

function openAdd() {
  editing.value = null
  form.value = { title: '', start_time: null, end_time: null, color: '#409EFF', notes: '', remind_before: 0 }
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

onMounted(() => fetchEvents())
</script>

<style scoped>
.cal-cell { cursor: pointer; }
.cal-dots { display: flex; gap: 3px; justify-content: center; margin-top: 2px; }
.cal-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.event-card { border-left: 3px solid; padding: 12px; margin-bottom: 8px; border-radius: 6px; background: #fafafa; }
</style>
