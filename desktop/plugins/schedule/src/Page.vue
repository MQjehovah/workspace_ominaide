<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
const props = defineProps<{ data?:any; execute?:(a:string,args?:any)=>Promise<any>; close?:()=>void }>()
const currentMonth = ref(new Date())
const events = ref<any[]>([])
const selectedDate = ref<string>('')
const dayEvents = ref<any[]>([])
const showDialog = ref(false)
const editing = ref<any>(null)
const form = ref({ title:'', start_time:'', end_time:'', notes:'', color:'#409EFF', remind_before:0 })
const saving = ref(false)
const api = (window as any).mqbox?.api

const monthStr = computed(() => `${currentMonth.value.getFullYear()}-${String(currentMonth.value.getMonth()+1).padStart(2,'0')}`)
const daysInMonth = computed(() => new Date(currentMonth.value.getFullYear(), currentMonth.value.getMonth()+1, 0).getDate())
const firstDay = computed(() => new Date(currentMonth.value.getFullYear(), currentMonth.value.getMonth(), 1).getDay())

async function loadEvents() {
  const s = new Date(currentMonth.value.getFullYear(), currentMonth.value.getMonth(), 1)
  const e = new Date(currentMonth.value.getFullYear(), currentMonth.value.getMonth()+1, 1)
  try { const r = await api.get(`/schedule?start=${toLocalISO(s)}&end=${toLocalISO(e)}`); events.value = r || [] } catch { events.value = [] }
}
function getDayEvents(day: number) {
  return events.value.filter((e:any) => {
    const d = new Date(e.start_time)
    return d.getUTCFullYear() === currentMonth.value.getFullYear() && d.getUTCMonth() === currentMonth.value.getMonth() && d.getUTCDate() === day
  })
}
function clickDay(day: number) { selectedDate.value = `${monthStr.value}-${String(day).padStart(2,'0')}`; dayEvents.value = getDayEvents(day); showDialog.value = false }
function prevMonth() { currentMonth.value = new Date(currentMonth.value.getFullYear(), currentMonth.value.getMonth()-1, 1); loadEvents() }
function nextMonth() { currentMonth.value = new Date(currentMonth.value.getFullYear(), currentMonth.value.getMonth()+1, 1); loadEvents() }
function openAdd() { editing.value = null; form.value = { title:'', start_time:`${selectedDate.value}T10:00`, end_time:'', notes:'', color:'#409EFF', remind_before:0 }; showDialog.value = true }
function openEdit(e: any) { editing.value = e; form.value = { title:e.title, start_time:e.start_time.slice(0,16), end_time:e.end_time?.slice(0,16)||'', notes:e.notes||'', color:e.color||'#409EFF', remind_before:e.remind_before||0 }; showDialog.value = true }
function toLocalISO(d: Date) { return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString() }

async function save() {
  if (!form.value.title.trim()) return; saving.value = true
  const body = {
    ...form.value,
    start_time: form.value.start_time ? toLocalISO(new Date(form.value.start_time)) : null,
    end_time: form.value.end_time ? toLocalISO(new Date(form.value.end_time)) : null,
  }
  try {
    if (editing.value) { await api.put(`/schedule/${editing.value.id}`, body) }
    else { await api.post('/schedule', body) }
    showDialog.value = false; loadEvents(); clickDay(parseInt(selectedDate.value.split('-')[2]))
  } catch(e:any) { console.error(e) }
  finally { saving.value = false }
}
async function deleteEvent(id: number) { try { await api.delete(`/schedule/${id}`); showDialog.value = false; loadEvents(); clickDay(parseInt(selectedDate.value.split('-')[2])) } catch {} }
onMounted(() => { const d = new Date(); selectedDate.value = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; loadEvents() })
</script>
<template>
  <div class="page">
    <div class="header"><h2>日程</h2><button class="close-btn" @click="close">×</button></div>
    <div class="cal-nav"><button class="nav-btn" @click="prevMonth">‹</button><span class="month-label">{{ monthStr }}</span><button class="nav-btn" @click="nextMonth">›</button></div>
    <div class="cal-grid">
      <div v-for="d in ['日','一','二','三','四','五','六']" :key="d" class="cal-header">{{ d }}</div>
      <div v-for="i in firstDay" :key="'e'+i" class="cal-cell disabled"></div>
      <div v-for="day in daysInMonth" :key="day" class="cal-cell" :class="{ today: selectedDate === `${monthStr}-${String(day).padStart(2,'0')}` }" @click="clickDay(day)">
        <span class="cal-day">{{ day }}</span>
        <div v-if="getDayEvents(day).length > 0" class="cal-dots"><span v-for="e in getDayEvents(day).slice(0,3)" :key="e.id" class="cal-dot" :style="{ background: e.color }"></span></div>
      </div>
    </div>
    <div class="day-detail">
      <div class="day-title">{{ selectedDate }} <button class="add-btn" @click="openAdd">+</button></div>
      <div v-if="dayEvents.length === 0" class="day-empty">无日程</div>
      <div v-for="e in dayEvents" :key="e.id" class="day-event" :style="{ borderLeftColor: e.color }">
        <div style="flex:1;cursor:pointer" @click="openEdit(e)"><strong>{{ e.title }}</strong><div class="event-time">{{ e.start_time.slice(11,16) }}{{ e.end_time ? ' — '+e.end_time.slice(11,16) : '' }}</div></div>
        <button class="del-btn" @click="deleteEvent(e.id)">×</button>
      </div>
    </div>
    <div v-if="showDialog" class="modal-overlay" @click.self="showDialog=false">
      <div class="modal"><h3>{{ editing ? '编辑' : '添加' }}日程</h3>
        <input v-model="form.title" class="input" placeholder="标题" />
        <label style="font-size:12px;color:#666">开始</label><input v-model="form.start_time" type="datetime-local" class="input" />
        <label style="font-size:12px;color:#666">结束</label><input v-model="form.end_time" type="datetime-local" class="input" />
        <label style="font-size:12px;color:#666">备注</label><textarea v-model="form.notes" class="input" rows="2"></textarea>
        <label style="font-size:12px;color:#666">颜色</label><input v-model="form.color" type="color" style="width:100%;height:36px;border:1px solid #dee2e6;border-radius:6px" />
        <div class="modal-actions"><button class="btn ghost" @click="showDialog=false">取消</button><button class="btn" @click="save" :disabled="saving">{{ saving ? '…' : '保存' }}</button></div>
      </div>
    </div>
  </div>
</template>
<style scoped>
.page { height:100vh; background:#f8f9fa; font-family:-apple-system,sans-serif; overflow-y:auto; }
.header { display:flex;align-items:center;justify-content:space-between;padding:16px 24px;border-bottom:1px solid #e9ecef; }
.header h2 { margin:0;font-size:18px;font-weight:600; }
.close-btn { width:32px;height:32px;border:none;border-radius:8px;background:transparent;font-size:20px;cursor:pointer;color:#868e96; }
.close-btn:hover { background:#ffebee;color:#e91e63; }
.cal-nav { display:flex;align-items:center;gap:16px;padding:16px 24px; }
.nav-btn { width:36px;height:36px;border:1px solid #dee2e6;border-radius:8px;background:#fff;font-size:20px;cursor:pointer; }
.nav-btn:hover { background:#f1f3f5; }
.month-label { font-size:16px;font-weight:600;color:#333;flex:1; }
.cal-grid { display:grid;grid-template-columns:repeat(7,1fr);gap:1px;background:#e9ecef;margin:0 24px;border-radius:8px;overflow:hidden; }
.cal-header { background:#fff;text-align:center;padding:8px;font-size:12px;font-weight:600;color:#909399; }
.cal-cell { background:#fff;min-height:64px;padding:4px;cursor:pointer;position:relative; }
.cal-cell.today { background:#e8f4fd; }
.cal-cell.disabled { background:#f8f9fa;cursor:default; }
.cal-day { font-size:13px;font-weight:500;color:#333;padding:2px 4px; }
.cal-dots { display:flex;gap:2px;flex-wrap:wrap;padding:2px; }
.cal-dot { width:5px;height:5px;border-radius:50%; }
.day-detail { padding:16px 24px; }
.day-title { font-size:14px;font-weight:600;color:#333;margin-bottom:8px;display:flex;align-items:center;justify-content:space-between; }
.add-btn { width:28px;height:28px;border:none;border-radius:6px;background:#fce4ec;color:#e91e63;font-size:18px;cursor:pointer; }
.add-btn:hover { background:#f8bbd0; }
.day-empty { font-size:13px;color:#909399; }
.day-event { display:flex;align-items:center;padding:8px 10px;margin-bottom:4px;border-left:4px solid;border-radius:0 6px 6px 0;background:#fff;border:1px solid #e9ecef;border-left-width:4px;font-size:13px; }
.event-time { font-size:11px;color:#909399;margin-top:2px; }
.del-btn { width:24px;height:24px;border:none;background:transparent;color:#ccc;cursor:pointer;font-size:16px;flex-shrink:0; }
.del-btn:hover { color:#e91e63; }
.modal-overlay { position:fixed;inset:0;background:rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;z-index:100; }
.modal { background:#fff;border-radius:12px;padding:24px;width:380px;max-width:90vw;box-shadow:0 20px 60px rgba(0,0,0,.2); }
.modal h3 { margin:0 0 16px;font-size:16px;font-weight:600; }
.input { width:100%;height:36px;padding:0 10px;border:1px solid #dee2e6;border-radius:6px;font-size:13px;margin-bottom:10px;outline:none;font-family:inherit; }
.input:focus { border-color:#e91e63; }
textarea.input { padding:8px 10px;height:auto; }
.modal-actions { display:flex;justify-content:flex-end;gap:8px;margin-top:12px; }
.btn { height:34px;padding:0 16px;border:none;border-radius:8px;background:#fce4ec;color:#e91e63;font-size:12px;font-weight:500;cursor:pointer; }
.btn:hover { background:#f8bbd0; }
.btn.ghost { background:transparent;color:#666; }
.btn.ghost:hover { background:#f1f3f5; }
</style>
