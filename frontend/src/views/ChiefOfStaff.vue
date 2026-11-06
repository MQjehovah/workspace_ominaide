<template>
  <div class="page-wrapper">
    <div class="page-header">
      <div>
        <h2>幕僚长</h2>
        <p class="page-sub">
          把邮件、资讯、日程、待办、钉钉和长期记忆合成一个工作台：
          现在该处理什么、会前看什么、这周怎么复盘。
        </p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="reload">刷新</el-button>
    </div>

    <el-tabs v-model="tab" class="cos-tabs">
      <el-tab-pane label="统一收件箱" name="triage">
        <div v-if="triage" class="stat-row">
          <div v-for="s in statCards" :key="s.key" class="stat-card" :class="s.key">
            <span class="stat-value">{{ s.value }}</span>
            <span class="stat-label">{{ s.label }}</span>
          </div>
        </div>

        <div v-if="['not_configured', 'error'].includes(triage?.sources?.dingtalk || '')" class="source-note">
          钉钉未连接：在「MCP 管理」中启用 dingtalk 后，未读消息会自动进入收件箱。
        </div>

        <div v-for="group in groupList" :key="group.key" class="page-card group-card">
          <div class="group-head">
            <h3>{{ group.label }}</h3>
            <span class="count">{{ group.items.length }}</span>
          </div>
          <div v-if="group.items.length === 0" class="muted">暂无</div>
          <div v-for="item in group.items" :key="item.id" class="triage-item">
            <div class="item-main">
              <div class="item-title">
                <el-tag size="small" effect="plain" :type="sourceTag(item.source)">{{ sourceLabel(item.source) }}</el-tag>
                <span class="title-text">{{ item.title }}</span>
              </div>
              <div class="item-summary" v-if="item.summary">{{ item.summary }}</div>
              <div class="item-meta">
                <span v-if="item.from">{{ item.from }}</span>
                <span v-if="item.time">{{ fmtTime(item.time) }}</span>
                <span v-if="item.meta?.important" class="danger-text">重要</span>
              </div>
            </div>
            <div class="item-actions">
              <el-button v-if="!['todo', 'schedule'].includes(item.source)" size="small" @click="createTodo(item)">转待办</el-button>
              <el-button
                v-if="item.source === 'mail'"
                size="small"
                type="primary"
                plain
                @click="openDraft(item)"
              >起草回复</el-button>
              <el-button size="small" link @click="$router.push(item.link || '/dashboard')">打开</el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="每日简报" name="brief">
        <div v-if="brief" class="page-card brief-card">
          <div class="brief-head">
            <h3>{{ brief.day }} 简报</h3>
            <el-button size="small" :icon="Refresh" @click="loadBrief">重新生成</el-button>
          </div>
          <p class="brief-summary">{{ brief.summary }}</p>
          <div v-if="brief.focus?.length" class="focus-row">
            <span class="focus-label">优先</span>
            <el-tag v-for="(f, i) in brief.focus" :key="i" type="warning" effect="plain">{{ f }}</el-tag>
          </div>
        </div>

        <div v-if="brief" class="brief-grid">
          <div v-for="section in brief.sections" :key="section.key" class="page-card section-card">
            <div class="group-head">
              <h3>{{ section.title }}</h3>
              <span class="count">{{ section.items.length }}</span>
            </div>
            <div v-if="section.items.length === 0" class="muted">暂无</div>
            <div v-for="item in section.items" :key="item.id" class="mini-item">
              <div class="mini-title">{{ item.title }}</div>
              <div class="item-meta">
                <span v-if="item.from">{{ item.from }}</span>
                <span v-if="item.time">{{ fmtTime(item.time) }}</span>
              </div>
              <div v-if="item.summary" class="mini-summary">{{ item.summary }}</div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="会议准备" name="meeting">
        <div class="page-card">
          <div class="prep-form">
            <el-input v-model="meeting.title" placeholder="会议主题，例如：预算评审会" />
            <el-input v-model="meeting.query" placeholder="检索关键词（留空则用主题）" />
            <el-input v-model="meeting.attendees" placeholder="参会人，用逗号分隔" />
            <el-date-picker
              v-model="meeting.start"
              type="datetime"
              placeholder="会议时间（可选）"
              value-format="YYYY-MM-DDTHH:mm:ss"
              style="width: 100%"
            />
            <el-button type="primary" :loading="prepLoading" @click="runMeetingPrep">生成会前简报</el-button>
          </div>
        </div>

        <div v-if="prep" class="page-card">
          <h3>{{ prep.title }}</h3>
          <p class="brief-summary">{{ prep.summary }}</p>
          <div v-if="prep.attendees?.length" class="item-meta">参会人：{{ prep.attendees.join('、') }}</div>

          <div class="prep-columns">
            <div>
              <div class="section-label">建议议程</div>
              <ol class="plain-list"><li v-for="(a, i) in prep.agenda" :key="i">{{ a }}</li></ol>
            </div>
            <div>
              <div class="section-label">要确认的问题</div>
              <ul class="plain-list"><li v-for="(q, i) in prep.questions" :key="i">{{ q }}</li></ul>
            </div>
          </div>

          <div v-if="prep.risks?.length" class="prep-block">
            <div class="section-label">风险与未决</div>
            <div class="tag-row">
              <el-tag v-for="(r, i) in prep.risks" :key="i" type="danger" effect="plain">{{ r }}</el-tag>
            </div>
          </div>

          <div class="prep-block">
            <div class="section-label">相关材料</div>
            <div v-if="prep.context.length === 0" class="muted">没有找到相关材料。</div>
            <div v-for="(c, i) in prep.context" :key="i" class="mini-item">
              <div class="mini-title">
                <el-tag size="small" effect="plain">{{ sourceLabel(c.source) }}</el-tag>
                {{ c.title }}
              </div>
              <div v-if="c.snippet" class="mini-summary">{{ c.snippet }}</div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="周报" name="weekly">
        <div v-if="weekly" class="page-card">
          <div class="brief-head">
            <h3>{{ weekly.period.start }} ~ {{ weekly.period.end }}</h3>
            <el-button size="small" :icon="Refresh" @click="loadWeekly">重新生成</el-button>
          </div>
          <p class="brief-summary">{{ weekly.summary }}</p>
          <div class="stat-row compact">
            <div class="stat-card"><span class="stat-value">{{ weekly.stats.todos_done }}</span><span class="stat-label">完成待办</span></div>
            <div class="stat-card"><span class="stat-value">{{ weekly.stats.todos_pending }}</span><span class="stat-label">进行中</span></div>
            <div class="stat-card"><span class="stat-value">{{ weekly.stats.insight_days }}</span><span class="stat-label">回顾天数</span></div>
            <div class="stat-card"><span class="stat-value">{{ weekly.stats.important_mail }}</span><span class="stat-label">重要邮件</span></div>
          </div>

          <div class="weekly-grid">
            <div class="weekly-block">
              <div class="section-label">本周成果</div>
              <ul class="plain-list"><li v-for="(w, i) in weekly.wins" :key="i">{{ w }}</li></ul>
            </div>
            <div class="weekly-block">
              <div class="section-label">进行中</div>
              <ul class="plain-list"><li v-for="(w, i) in weekly.in_progress" :key="i">{{ w }}</li></ul>
            </div>
            <div class="weekly-block">
              <div class="section-label">风险</div>
              <ul class="plain-list risk"><li v-for="(w, i) in weekly.risks" :key="i">{{ w }}</li></ul>
            </div>
            <div class="weekly-block">
              <div class="section-label">下周重点</div>
              <ul class="plain-list"><li v-for="(w, i) in weekly.next_week" :key="i">{{ w }}</li></ul>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="draftVisible" title="起草回复" width="640px">
      <div v-loading="draftLoading" class="draft-body">
        <div v-if="draft">
          <div class="draft-meta">
            <el-tag size="small" effect="plain">{{ draft.to || '收件人' }}</el-tag>
            <el-select v-model="draftTone" size="small" style="width: 130px">
              <el-option label="专业" value="professional" />
              <el-option label="友好" value="friendly" />
              <el-option label="简短" value="concise" />
            </el-select>
            <el-button size="small" link type="primary" @click="generateDraft">重新生成</el-button>
          </div>
          <el-input v-model="draft.subject" class="draft-input" placeholder="主题" />
          <el-input v-model="draft.body" type="textarea" :rows="10" class="draft-input" />
          <p class="muted">{{ draft.note }}</p>
        </div>
      </div>
      <template #footer>
        <el-button @click="draftVisible = false">关闭</el-button>
        <el-button type="primary" :disabled="!draft" @click="copyDraft">复制草稿</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import client from '@/api/client'
import { parseBackendDate } from '@/utils/date'

const tab = ref('triage')
const loading = ref(false)
const triage = ref<any>(null)
const brief = ref<any>(null)
const prep = ref<any>(null)
const weekly = ref<any>(null)
const prepLoading = ref(false)
const meeting = reactive({ title: '', query: '', attendees: '', start: '' })

const draftVisible = ref(false)
const draft = ref<any>(null)
const draftTone = ref('professional')
const draftItem = ref<any>(null)
const draftLoading = ref(false)

const groupList = computed(() => {
  const groups = triage.value?.groups || {}
  return [
    { key: 'urgent', label: '紧急', items: groups.urgent || [] },
    { key: 'needs_reply', label: '待回复', items: groups.needs_reply || [] },
    { key: 'today', label: '今天', items: groups.today || [] },
    { key: 'fyi', label: '知会', items: groups.fyi || [] },
  ]
})

const statCards = computed(() => [
  { key: 'total', label: '全部', value: triage.value?.counts?.total || 0 },
  { key: 'urgent', label: '紧急', value: triage.value?.counts?.urgent || 0 },
  { key: 'needs_reply', label: '待回复', value: triage.value?.counts?.needs_reply || 0 },
  { key: 'today', label: '今天', value: triage.value?.counts?.today || 0 },
])

function sourceLabel(source: string) {
  return ({ mail: '邮件', sources: '资讯', dingtalk: '钉钉', todo: '待办', schedule: '日程', memory: '记忆' } as Record<string, string>)[source] || source
}

function sourceTag(source: string) {
  return ({ mail: 'primary', sources: 'info', dingtalk: 'warning', todo: 'success', schedule: 'danger' } as Record<string, string>)[source] || 'info'
}

function fmtTime(value: any) {
  const d = parseBackendDate(value)
  if (!d) return ''
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

async function loadTriage() {
  loading.value = true
  try {
    const { data } = await client.get('/cos/triage', { params: { days: 3 } })
    triage.value = data
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '收件箱加载失败')
  } finally {
    loading.value = false
  }
}

async function loadBrief() {
  try {
    const { data } = await client.get('/cos/daily-brief')
    brief.value = data
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '简报生成失败')
  }
}

async function loadWeekly() {
  try {
    const { data } = await client.get('/cos/weekly-review')
    weekly.value = data
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '周报生成失败')
  }
}

async function reload() {
  await Promise.all([loadTriage(), loadBrief(), loadWeekly()])
}async function createTodo(item: any) {
  try {
    await client.post('/plugins/todo/items', {
      title: item.title.slice(0, 200),
      description: `来源：${sourceLabel(item.source)}\n${item.summary || ''}`.slice(0, 2000),
      priority: item.priority === 'urgent' ? 3 : item.priority === 'high' ? 2 : 1,
    })
    ElMessage.success('已创建待办')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '创建待办失败')
  }
}

function openDraft(item: any) {
  draftItem.value = item
  draftTone.value = 'professional'
  draft.value = null
  draftVisible.value = true
  generateDraft()
}

async function generateDraft() {
  if (!draftItem.value) return
  draftLoading.value = true
  try {
    const { data } = await client.post('/cos/draft-reply', {
      source: draftItem.value.source,
      message_id: draftItem.value.source_id,
      tone: draftTone.value,
    })
    draft.value = data
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '生成草稿失败')
  } finally {
    draftLoading.value = false
  }
}

async function copyDraft() {
  if (!draft.value) return
  const text = `主题：${draft.value.subject}\n\n${draft.value.body}`
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('草稿已复制')
  } catch {
    ElMessage.warning('复制失败，请手动选择文本')
  }
}

async function runMeetingPrep() {
  if (!meeting.title && !meeting.query) {
    ElMessage.warning('请填写会议主题或关键词')
    return
  }
  prepLoading.value = true
  try {
    const { data } = await client.post('/cos/meeting-prep', {
      title: meeting.title,
      query: meeting.query || undefined,
      attendees: meeting.attendees ? meeting.attendees.split(/[,，、]/).map(s => s.trim()).filter(Boolean) : [],
      start: meeting.start || undefined,
    })
    prep.value = data
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '会前简报生成失败')
  } finally {
    prepLoading.value = false
  }
}

watch(tab, (value) => {
  if (value === 'brief' && !brief.value) loadBrief()
  if (value === 'weekly' && !weekly.value) loadWeekly()
})

onMounted(loadTriage)
</script>

<style scoped>
.page-sub { margin: 4px 0 0; font-size: 12px; color: #909399; }
.cos-tabs { margin-top: 6px; }
.stat-row { display: flex; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.stat-row.compact { margin: 14px 0; }
.stat-card { flex: 1; min-width: 110px; padding: 12px 14px; border-radius: 10px; background: #fff; border: 1px solid #eef0f4; display: flex; flex-direction: column; gap: 2px; }
.stat-card.urgent { border-left: 3px solid #e45656; }
.stat-value { font-size: 20px; font-weight: 700; color: #1a1a2e; }
.stat-label { font-size: 12px; color: #909399; }
.source-note { margin-bottom: 12px; padding: 8px 12px; border-radius: 8px; background: #fdf6ec; color: #b88230; font-size: 12px; }
.group-card { margin-bottom: 14px; padding: 16px 18px; }
.group-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.group-head h3 { margin: 0; font-size: 14px; }
.count { display: inline-block; padding: 1px 7px; border-radius: 10px; background: #eef4ff; color: #2f6fbf; font-size: 11px; font-weight: 600; }
.triage-item { display: flex; justify-content: space-between; gap: 14px; padding: 12px 0; border-bottom: 1px solid #f0f2f5; }
.triage-item:last-child { border-bottom: none; }
.item-main { min-width: 0; flex: 1; }
.item-title { display: flex; align-items: center; gap: 8px; }
.title-text { font-size: 14px; font-weight: 500; color: #303133; }
.item-summary { margin-top: 4px; font-size: 12px; line-height: 1.6; color: #606266; }
.item-meta { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 4px; font-size: 11px; color: #909399; }
.danger-text { color: #e45656; }
.item-actions { display: flex; gap: 4px; align-items: flex-start; flex-shrink: 0; }
.brief-card { padding: 18px 20px; }
.brief-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.brief-head h3 { margin: 0; font-size: 15px; }
.brief-summary { margin: 12px 0; font-size: 14px; line-height: 1.8; color: #303133; }
.focus-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.focus-label { font-size: 12px; color: #909399; }
.brief-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; margin-top: 14px; }
.section-card { padding: 16px 18px; }
.mini-item { padding: 9px 0; border-bottom: 1px solid #f0f2f5; }
.mini-item:last-child { border-bottom: none; }
.mini-title { font-size: 13px; color: #303133; display: flex; gap: 6px; align-items: center; }
.mini-summary { margin-top: 3px; font-size: 12px; color: #606266; line-height: 1.6; }
.prep-form { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.prep-form .el-button { grid-column: 1 / -1; justify-self: start; }
.prep-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 14px; }
.section-label { font-size: 12px; color: #909399; margin: 12px 0 6px; letter-spacing: .5px; }
.plain-list { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.8; color: #606266; }
.plain-list.risk li { color: #c45656; }
.prep-block { margin-top: 14px; }
.tag-row { display: flex; gap: 6px; flex-wrap: wrap; }
.weekly-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-top: 8px; }
.weekly-block { min-width: 0; }
.draft-meta { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; }
.draft-input { margin-bottom: 10px; }
.muted { color: #909399; font-size: 12px; }
@media (max-width: 760px) {
  .prep-form, .prep-columns, .weekly-grid { grid-template-columns: 1fr; }
  .triage-item { flex-direction: column; }
  .item-actions { align-self: flex-end; }
}
</style>
