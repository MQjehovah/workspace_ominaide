<template>
  <div class="page-wrapper">
    <div class="page-header">
      <h2>每日回顾</h2>
      <div class="header-actions">
        <el-select v-model="days" size="small" style="width:110px" @change="load">
          <el-option label="近 7 天" :value="7" />
          <el-option label="近 14 天" :value="14" />
          <el-option label="近 30 天" :value="30" />
        </el-select>
        <el-button size="small" :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
        <el-button size="small" type="primary" :loading="generating" @click="generateToday">
          生成今日回顾
        </el-button>
      </div>
    </div>

    <div v-if="!loading && items.length === 0" class="page-card empty-card">
      <el-empty description="还没有回顾。开启桌面端的活动采集，并和助理聊几句，晚上会自动生成。">
        <el-button type="primary" @click="generateToday" :loading="generating">立即生成</el-button>
      </el-empty>
    </div>

    <div class="insight-list">
      <div v-for="item in items" :key="item.id" class="page-card insight-card">
        <div class="insight-head">
          <div>
            <span class="insight-date">{{ formatDay(item.day) }}</span>
            <el-tag size="small" type="info" style="margin-left:8px">{{ weekday(item.day) }}</el-tag>
          </div>
          <span class="insight-generated">{{ formatTime(item.generated_at) }} 生成</span>
        </div>

        <p class="insight-summary">{{ item.summary }}</p>

        <div v-if="item.highlights?.length" class="insight-section">
          <div class="section-label">完成与发生</div>
          <div class="tag-row">
            <el-tag v-for="(h, i) in item.highlights.slice(0, 8)" :key="i" size="small" effect="plain">
              {{ h }}
            </el-tag>
          </div>
        </div>

        <div v-if="item.patterns?.length" class="insight-section">
          <div class="section-label">观察</div>
          <ul class="plain-list">
            <li v-for="(p, i) in item.patterns" :key="i">{{ p }}</li>
          </ul>
        </div>

        <div v-if="item.suggestions?.length" class="insight-section">
          <div class="section-label">建议</div>
          <ul class="plain-list suggestion-list">
            <li v-for="(s, i) in item.suggestions" :key="i">
              {{ typeof s === 'string' ? s : s.text }}
            </li>
          </ul>
        </div>

        <div class="insight-stats">
          <span>活动 {{ item.stats?.activity_count || 0 }}</span>
          <span>对话 {{ item.stats?.chat_message_count || 0 }}</span>
          <span>待办完成 {{ item.stats?.todo_done_count || 0 }}</span>
          <span>日程 {{ item.stats?.schedule_count || 0 }}</span>
          <span v-if="item.stats?.top_apps?.length">常用 {{ item.stats.top_apps[0].app }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import client from '@/api/client'
import { parseBackendDate } from '@/utils/date'

const items = ref<any[]>([])
const days = ref(7)
const loading = ref(false)
const generating = ref(false)

function todayISO() {
  const d = new Date()
  const offset = d.getTimezoneOffset()
  return new Date(d.getTime() - offset * 60000).toISOString().slice(0, 10)
}

async function load() {
  loading.value = true
  try {
    const { data } = await client.get('/insights/daily', { params: { days: days.value } })
    items.value = data || []
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载回顾失败')
  } finally {
    loading.value = false
  }
}

async function generateToday() {
  generating.value = true
  try {
    await client.post('/insights/daily/run', { day: todayISO(), force: true })
    ElMessage.success('今日回顾已生成')
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '生成失败：今天还没有活动或会话')
  } finally {
    generating.value = false
  }
}

function formatDay(day: string) {
  if (!day) return ''
  const [, m, d] = day.split('-')
  return `${Number(m)} 月 ${Number(d)} 日`
}

function weekday(day: string) {
  if (!day) return ''
  const d = new Date(`${day}T00:00:00`)
  return '周' + '日一二三四五六'[d.getDay()]
}

function formatTime(value: any) {
  if (!value) return ''
  const d = parseBackendDate(value)
  if (!d) return ''
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

onMounted(load)
</script>

<style scoped>
.header-actions { display: flex; gap: 8px; align-items: center; }
.insight-list { display: flex; flex-direction: column; gap: 14px; }
.insight-card { padding: 18px 20px; }
.insight-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.insight-date { font-size: 16px; font-weight: 600; color: #1a1a2e; }
.insight-generated { font-size: 12px; color: #909399; }
.insight-summary { margin: 12px 0 4px; font-size: 14px; line-height: 1.7; color: #303133; }
.insight-section { margin-top: 12px; }
.section-label { font-size: 12px; color: #909399; margin-bottom: 6px; letter-spacing: .5px; }
.tag-row { display: flex; gap: 6px; flex-wrap: wrap; }
.plain-list { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.8; color: #606266; }
.suggestion-list li { color: #3a6ea5; }
.insight-stats { margin-top: 14px; padding-top: 10px; border-top: 1px solid #f0f2f5; display: flex; gap: 16px; flex-wrap: wrap; font-size: 12px; color: #909399; }
.empty-card { padding: 40px 0; }
</style>
