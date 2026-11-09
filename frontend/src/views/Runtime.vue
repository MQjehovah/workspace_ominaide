<template>
  <div class="page-wrapper">
    <div class="page-header" style="display:flex;align-items:center;justify-content:space-between">
      <div>
        <h2>运行看板</h2>
        <p style="color:#909399;font-size:13px;margin-top:4px">指标、任务、Agent、上下文调试</p>
      </div>
      <div class="header-actions">
        <el-select v-model="hours" size="small" style="width:130px" @change="loadMetrics">
          <el-option label="近 6 小时" :value="6" />
          <el-option label="近 24 小时" :value="24" />
          <el-option label="近 3 天" :value="72" />
          <el-option label="近 7 天" :value="168" />
        </el-select>
        <el-button :icon="Refresh" @click="refreshAll">刷新</el-button>
      </div>
    </div>

    <el-tabs v-model="tab" class="cap-tabs">
      <el-tab-pane label="运行指标" name="metrics">
        <div class="overview-grid" v-loading="loading.metrics">
          <div class="overview-card">
            <div class="overview-label">请求总数</div>
            <div class="overview-value">{{ formatNumber(metrics.overview?.requests) }}</div>
            <div class="overview-sub">近 {{ hours }} 小时</div>
          </div>
          <div class="overview-card">
            <div class="overview-label">错误率</div>
            <div class="overview-value" :class="{ danger: (metrics.overview?.error_rate || 0) > 0.05 }">
              {{ ((metrics.overview?.error_rate || 0) * 100).toFixed(1) }}%
            </div>
            <div class="overview-sub">{{ formatNumber(metrics.overview?.errors) }} 次错误</div>
          </div>
          <div class="overview-card">
            <div class="overview-label">P95 延迟</div>
            <div class="overview-value">{{ formatNumber(metrics.overview?.p95_ms) }}<small>ms</small></div>
            <div class="overview-sub">P50 {{ formatNumber(metrics.overview?.p50_ms) }} ms</div>
          </div>
          <div class="overview-card accent">
            <div class="overview-label">LLM Token</div>
            <div class="overview-value">{{ formatNumber(metrics.overview?.tokens) }}</div>
            <div class="overview-sub">{{ formatNumber(metrics.overview?.llm_calls) }} 次调用</div>
          </div>
          <div class="overview-card">
            <div class="overview-label">活跃后台任务</div>
            <div class="overview-value">{{ formatNumber(metrics.overview?.jobs_active) }}</div>
            <div class="overview-sub">排队 + 运行中</div>
          </div>
          <div class="overview-card">
            <div class="overview-label">活跃 Agent</div>
            <div class="overview-value">{{ formatNumber(metrics.overview?.agents_active) }}</div>
            <div class="overview-sub">{{ formatNumber(metrics.overview?.approvals_pending) }} 个待审批</div>
          </div>
        </div>

        <div class="token-grid" v-loading="loading.metrics" style="margin-top:14px">
          <div class="token-card primary">
            <div class="token-label">LLM 总 Token</div>
            <div class="token-value">{{ formatNumber(metrics.tokens?.total) }}</div>
            <div class="token-sub">输入 {{ formatNumber(metrics.tokens?.input) }} · 输出 {{ formatNumber(metrics.tokens?.output) }}</div>
          </div>
          <div class="token-card">
            <div class="token-label">平均每次 Token</div>
            <div class="token-value">{{ formatNumber(avgTokens) }}</div>
            <div class="token-sub">输入 + 输出 / 调用次数</div>
          </div>
          <div class="token-card">
            <div class="token-label">LLM 调用</div>
            <div class="token-value">{{ formatNumber(metrics.overview?.llm_calls) }}</div>
            <div class="token-sub">p95 {{ formatNumber(metrics.by_kind?.llm?.p95_ms) }} ms</div>
          </div>
        </div>

        <div class="page-card timeline-card" v-if="metrics.timeline?.length">
          <div class="page-card-body">
            <div class="timeline-head">
              <div>
                <h4>请求与 Token 趋势</h4>
                <span class="muted">按小时聚合</span>
              </div>
              <span class="timeline-total">请求 {{ formatNumber(metrics.overview?.requests) }} · Token {{ formatNumber(metrics.overview?.tokens) }}</span>
            </div>
            <div class="timeline-chart">
              <div v-for="(point, index) in metrics.timeline" :key="point.hour" class="bar-col">
                <div class="bar-stack">
                  <div class="bar request" :style="{ height: requestHeight(point.requests) + '%' }" :title="`${point.hour} 请求 ${point.requests}`"></div>
                </div>
                <div class="bar-label" v-if="hours <= 24 || index % 6 === 0">{{ point.hour.slice(11, 13) }}</div>
              </div>
            </div>
            <div class="timeline-chart token-chart">
              <div v-for="(point, index) in metrics.timeline" :key="`t-${point.hour}`" class="bar-col">
                <div class="bar-stack">
                  <div class="bar token" :style="{ height: tokenHeight(point.tokens) + '%' }" :title="`${point.hour} Token ${point.tokens}`"></div>
                </div>
                <div class="bar-label" v-if="hours <= 24 || index % 6 === 0">{{ point.hour.slice(11, 13) }}</div>
              </div>
            </div>
            <div class="timeline-legend">
              <span><i class="legend request"></i>请求量</span>
              <span><i class="legend token"></i>LLM Token</span>
            </div>
          </div>
        </div>

        <div class="page-card" style="margin-top:14px" v-if="metrics.tokens?.by_model?.length">
          <div class="page-card-body">
            <h4 style="margin:0 0 10px">按模型 Token</h4>
            <el-table :data="metrics.tokens.by_model" size="small" stripe>
              <el-table-column prop="model" label="模型" min-width="260" show-overflow-tooltip />
              <el-table-column label="输入" width="130">
                <template #default="{ row }">{{ formatNumber(row.input) }}</template>
              </el-table-column>
              <el-table-column label="输出" width="130">
                <template #default="{ row }">{{ formatNumber(row.output) }}</template>
              </el-table-column>
              <el-table-column label="合计" width="140">
                <template #default="{ row }"><b>{{ formatNumber(row.total) }}</b></template>
              </el-table-column>
              <el-table-column label="调用" width="100">
                <template #default="{ row }">{{ formatNumber(row.calls) }}</template>
              </el-table-column>
            </el-table>
          </div>
        </div>

        <div class="page-card" style="margin-top:14px" v-if="metrics.top_names?.length">
          <div class="page-card-body">
            <h4 style="margin:0 0 10px">调用排行</h4>
            <el-table :data="metrics.top_names" size="small" stripe>
              <el-table-column prop="kind" label="类型" width="90" />
              <el-table-column prop="name" label="名称" min-width="260" show-overflow-tooltip />
              <el-table-column prop="count" label="次数" width="100" />
              <el-table-column label="错误率" width="110">
                <template #default="{ row }">{{ (row.error_rate * 100).toFixed(1) }}%</template>
              </el-table-column>
              <el-table-column label="P95" width="110">
                <template #default="{ row }">{{ row.p95_ms }} ms</template>
              </el-table-column>
              <el-table-column label="Token" width="120">
                <template #default="{ row }">{{ formatNumber(row.tokens) }}</template>
              </el-table-column>
            </el-table>
          </div>
        </div>

        <div class="metric-grid" v-loading="loading.metrics" style="margin-top:14px">
          <div class="metric-card" v-for="(value, key) in metrics.by_kind" :key="key">
            <div class="metric-title">{{ kindLabel(String(key)) }}</div>
            <div class="metric-main">{{ value.count }}</div>
            <div class="metric-sub">
              错误率 {{ (value.error_rate * 100).toFixed(1) }}% ·
              p50 {{ value.p50_ms }}ms · p95 {{ value.p95_ms }}ms
            </div>
          </div>
          <el-empty v-if="!Object.keys(metrics.by_kind || {}).length" description="还没有指标数据" />
        </div>
        <div class="page-card" style="margin-top:14px">
          <div class="page-card-body">
            <h4 style="margin:0 0 10px">最慢调用</h4>
            <el-table :data="metrics.slowest || []" size="small" stripe>
              <el-table-column prop="kind" label="类型" width="90" />
              <el-table-column prop="name" label="名称" min-width="260" show-overflow-tooltip />
              <el-table-column prop="duration_ms" label="耗时" width="100">
                <template #default="{ row }">{{ row.duration_ms }} ms</template>
              </el-table-column>
              <el-table-column prop="status" label="状态" width="80" />
              <el-table-column prop="created_at" label="时间" width="180" />
            </el-table>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="后台任务" name="jobs">
        <div class="mini-grid">
          <div v-for="item in jobSummary" :key="item.key" class="mini-card">
            <div class="mini-label">{{ item.label }}</div>
            <div class="mini-value" :class="item.className">{{ formatNumber(item.value) }}</div>
          </div>
        </div>
        <div class="page-card">
          <div class="page-card-body">
            <div style="display:flex;gap:10px;margin-bottom:12px">
              <el-select v-model="jobStatus" clearable placeholder="全部状态" style="width:150px" @change="loadJobs">
                <el-option label="排队中" value="queued" />
                <el-option label="运行中" value="running" />
                <el-option label="完成" value="done" />
                <el-option label="失败" value="failed" />
                <el-option label="死信" value="dead" />
              </el-select>
              <el-button :icon="Refresh" @click="loadJobs">刷新</el-button>
            </div>
            <el-table :data="jobs" size="small" stripe v-loading="loading.jobs">
              <el-table-column prop="id" label="ID" width="70" />
              <el-table-column prop="kind" label="类型" min-width="180" />
              <el-table-column prop="status" label="状态" width="90">
                <template #default="{ row }">
                  <el-tag size="small" :type="jobTag(row.status)">{{ jobLabel(row.status) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="尝试" width="80">
                <template #default="{ row }">{{ row.attempts }}/{{ row.max_attempts }}</template>
              </el-table-column>
              <el-table-column prop="error" label="错误" min-width="240" show-overflow-tooltip />
              <el-table-column prop="created_at" label="创建时间" width="180" />
              <el-table-column label="操作" width="150" fixed="right">
                <template #default="{ row }">
                  <el-button v-if="['failed','dead'].includes(row.status)" link type="primary" size="small" @click="retryJob(row)">重试</el-button>
                  <el-button v-if="!['done','dead','cancelled'].includes(row.status)" link type="danger" size="small" @click="cancelJob(row)">取消</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="Agent 任务" name="agent">
        <div class="mini-grid">
          <div v-for="item in agentSummary" :key="item.key" class="mini-card">
            <div class="mini-label">{{ item.label }}</div>
            <div class="mini-value" :class="item.className">{{ formatNumber(item.value) }}</div>
          </div>
        </div>
        <div class="page-card">
          <div class="page-card-body">
            <div style="display:flex;gap:10px;margin-bottom:12px">
              <el-input v-model="goal" placeholder="描述一个可执行目标，例如：准备明天客户会" style="max-width:520px" />
              <el-button type="primary" :loading="creating" @click="createTask">创建任务</el-button>
              <el-button :icon="Refresh" @click="loadTasks">刷新</el-button>
            </div>
            <el-table :data="tasks" size="small" stripe v-loading="loading.agent">
              <el-table-column prop="id" label="ID" width="70" />
              <el-table-column prop="input" label="目标" min-width="300" show-overflow-tooltip />
              <el-table-column prop="status" label="状态" width="120">
                <template #default="{ row }"><el-tag size="small">{{ row.status }}</el-tag></template>
              </el-table-column>
              <el-table-column prop="created_at" label="创建时间" width="180" />
              <el-table-column label="操作" width="180" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="openTask(row)">详情</el-button>
                  <el-button v-if="!['done','failed','cancelled'].includes(row.status)" link type="danger" size="small" @click="cancelTask(row)">取消</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="上下文调试" name="context">
        <div class="page-card">
          <div class="page-card-body">
            <div style="display:flex;gap:10px;margin-bottom:12px">
              <el-input v-model="contextQuery" placeholder="输入客户、项目或关键词" style="max-width:480px" @keyup.enter="runContext" />
              <el-button type="primary" :loading="loading.context" @click="runContext">构建上下文</el-button>
            </div>
            <el-table :data="contextItems" size="small" stripe>
              <el-table-column prop="type" label="类型" width="90" />
              <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
              <el-table-column prop="snippet" label="摘要" min-width="360" show-overflow-tooltip />
              <el-table-column prop="citation" label="引用" width="150" />
            </el-table>
            <el-empty v-if="!contextItems.length" description="输入关键词后构建跨源上下文" />
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="自动化校验" name="automation">
        <div class="page-card">
          <div class="page-card-body">
            <el-input v-model="automationText" type="textarea" :rows="16" spellcheck="false" />
            <div style="margin-top:10px;display:flex;gap:10px;align-items:center">
              <el-button type="primary" :loading="loading.automation" @click="validateAutomation">校验 DSL</el-button>
              <el-tag v-if="automationResult" :type="automationResult.valid ? 'success' : 'danger'">
                {{ automationResult.valid ? '通过' : '不通过' }}
              </el-tag>
            </div>
            <pre v-if="automationResult" class="json-box">{{ JSON.stringify(automationResult, null, 2) }}</pre>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="taskDialog" title="Agent 任务详情" width="720px">
      <div v-if="taskDetail">
        <p style="font-size:13px;color:#606266">{{ taskDetail.input }}</p>
        <el-tag size="small" style="margin-bottom:10px">{{ taskDetail.status }}</el-tag>
        <el-table :data="taskDetail.steps || []" size="small" stripe>
          <el-table-column prop="seq" label="#" width="50" />
          <el-table-column prop="type" label="类型" width="90" />
          <el-table-column prop="tool_name" label="工具" width="150" />
          <el-table-column prop="status" label="状态" width="80" />
          <el-table-column prop="result" label="结果" min-width="320" show-overflow-tooltip />
        </el-table>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import client from '@/api/client'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'

const tab = ref('metrics')
const hours = ref(24)
const loading = reactive({ metrics: false, jobs: false, agent: false, context: false, automation: false })
const metrics = ref<any>({ by_kind: {}, slowest: [], tokens: {}, overview: {}, timeline: [], top_names: [], jobs: {}, agents: {} })
const jobs = ref<any[]>([])
const jobStatus = ref('')
const goal = ref('')
const creating = ref(false)
const tasks = ref<any[]>([])
const taskDialog = ref(false)
const taskDetail = ref<any>(null)
const contextQuery = ref('')
const contextItems = ref<any[]>([])
const automationText = ref(JSON.stringify({
  name: '每日邮件摘要',
  enabled: true,
  trigger: { type: 'schedule', cron: '0 9 * * *' },
  conditions: [],
  actions: [{ type: 'agent', params: { goal: '汇总未读邮件并生成摘要' } }],
}, null, 2))
const automationResult = ref<any>(null)

function formatNumber(value: any) {
  const number = Number(value || 0)
  return Number.isFinite(number) ? number.toLocaleString('zh-CN') : '0'
}

const jobSummary = computed(() => {
  const j = metrics.value?.jobs || {}
  return [
    { key: 'queued', label: '排队', value: j.queued, className: '' },
    { key: 'running', label: '运行中', value: j.running, className: 'warn' },
    { key: 'done', label: '完成', value: j.done, className: 'ok' },
    { key: 'failed', label: '失败', value: j.failed, className: 'danger' },
    { key: 'dead', label: '死信', value: j.dead, className: 'danger' },
  ]
})

const agentSummary = computed(() => {
  const a = metrics.value?.agents || {}
  return [
    { key: 'active', label: '活跃', value: a.active, className: 'warn' },
    { key: 'done', label: '完成', value: a.done, className: 'ok' },
    { key: 'failed', label: '失败', value: a.failed, className: 'danger' },
    { key: 'waiting', label: '待审批', value: a.waiting_approval, className: 'warn' },
    { key: 'queued', label: '排队', value: a.queued, className: '' },
  ]
})

const maxRequests = computed(() => Math.max(...(metrics.value?.timeline || []).map((p: any) => p.requests), 1))
const maxTokens = computed(() => Math.max(...(metrics.value?.timeline || []).map((p: any) => p.tokens), 1))

function requestHeight(value: number) {
  return Math.max(2, Math.round((value / maxRequests.value) * 100))
}
function tokenHeight(value: number) {
  return Math.max(2, Math.round((value / maxTokens.value) * 100))
}

const avgTokens = computed(() => {
  const calls = Number(metrics.value?.by_kind?.llm?.count || 0)
  const total = Number(metrics.value?.tokens?.total || 0)
  return calls > 0 ? Math.round(total / calls) : 0
})

function kindLabel(kind: string) {
  return ({ request: '接口请求', mcp: 'MCP 调用', llm: 'LLM 调用', asr: 'ASR 转写' } as any)[kind] || kind
}
function jobLabel(status: string) {
  return ({ queued: '排队', running: '运行中', done: '完成', failed: '失败', dead: '死信', cancelled: '取消' } as any)[status] || status
}
function jobTag(status: string) {
  return status === 'done' ? 'success' : status === 'failed' || status === 'dead' ? 'danger' : 'info'
}

async function loadMetrics() {
  loading.metrics = true
  try { metrics.value = (await client.get('/metrics', { params: { hours: hours.value } })).data } finally { loading.metrics = false }
}
async function loadJobs() {
  loading.jobs = true
  try {
    const params: any = { limit: 100 }
    if (jobStatus.value) params.status = jobStatus.value
    jobs.value = (await client.get('/jobs', { params })).data.items || []
  } finally { loading.jobs = false }
}
async function retryJob(row: any) {
  await client.post(`/jobs/${row.id}/retry`)
  ElMessage.success('已重新入队')
  await loadJobs()
}
async function cancelJob(row: any) {
  await client.post(`/jobs/${row.id}/cancel`)
  ElMessage.success('已取消')
  await loadJobs()
}
async function loadTasks() {
  loading.agent = true
  try { tasks.value = (await client.get('/agent/tasks')).data || [] } finally { loading.agent = false }
}
async function createTask() {
  if (!goal.value.trim()) return
  creating.value = true
  try {
    await client.post('/agent/tasks', { goal: goal.value.trim() })
    goal.value = ''
    ElMessage.success('任务已创建')
    await loadTasks()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '创建失败')
  } finally { creating.value = false }
}
async function openTask(row: any) {
  taskDetail.value = (await client.get(`/agent/tasks/${row.id}`)).data
  taskDialog.value = true
}
async function cancelTask(row: any) {
  await client.post(`/agent/tasks/${row.id}/cancel`)
  ElMessage.success('已取消')
  await loadTasks()
}
async function runContext() {
  loading.context = true
  try {
    contextItems.value = (await client.get('/context/build', { params: { q: contextQuery.value } })).data.items || []
  } finally { loading.context = false }
}
async function validateAutomation() {
  loading.automation = true
  try {
    automationResult.value = (await client.post('/automations/validate', { spec: JSON.parse(automationText.value) })).data
  } catch (e: any) {
    automationResult.value = { valid: false, errors: [e?.message || 'JSON 解析失败'] }
  } finally { loading.automation = false }
}
async function refreshAll() {
  await Promise.all([loadMetrics(), loadJobs(), loadTasks()])
}
onMounted(refreshAll)
</script>

<style scoped>
.token-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.token-card { background: #fff; border: 1px solid #ebeef5; border-radius: 12px; padding: 16px; }
.token-card.primary { background: linear-gradient(135deg, #eef2ff, #f5f3ff); border-color: #ddd6fe; }
.token-label { font-size: 12px; color: #909399; }
.token-value { font-size: 28px; font-weight: 800; color: #303133; margin-top: 4px; font-variant-numeric: tabular-nums; }
.token-card.primary .token-value { color: #4338ca; }
.token-sub { font-size: 11px; color: #909399; margin-top: 4px; }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.metric-card { background: #fff; border: 1px solid #ebeef5; border-radius: 12px; padding: 16px; }
.metric-title { font-size: 12px; color: #909399; }
.metric-main { font-size: 30px; font-weight: 800; color: #303133; margin-top: 4px; }
.metric-sub { font-size: 11px; color: #909399; margin-top: 4px; }
.json-box { margin-top: 12px; background: #f5f7fa; border-radius: 8px; padding: 12px; font-size: 12px; overflow: auto; max-height: 420px; }
@media (max-width: 900px) { .token-grid { grid-template-columns: 1fr; } }

.header-actions { display: flex; align-items: center; gap: 8px; }
.overview-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; }
.overview-card { background: #fff; border: 1px solid #ebeef5; border-radius: 12px; padding: 14px; }
.overview-card.accent { background: linear-gradient(135deg, #eef2ff, #f5f3ff); border-color: #ddd6fe; }
.overview-label { font-size: 11px; color: #909399; }
.overview-value { margin-top: 4px; font-size: 24px; font-weight: 800; color: #1f2937; font-variant-numeric: tabular-nums; }
.overview-value small { font-size: 11px; font-weight: 500; color: #909399; margin-left: 2px; }
.overview-value.danger { color: #dc2626; }
.overview-card.accent .overview-value { color: #4338ca; }
.overview-sub { margin-top: 3px; font-size: 10.5px; color: #a0a6b3; }
.timeline-card { margin-top: 14px; }
.timeline-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 12px; }
.timeline-head h4 { margin: 0; font-size: 14px; color: #303133; }
.timeline-total { font-size: 12px; color: #909399; }
.timeline-chart { display: flex; align-items: flex-end; gap: 3px; height: 100px; padding-top: 10px; }
.token-chart { height: 72px; margin-top: 10px; }
.bar-col { flex: 1; min-width: 2px; height: 100%; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; }
.bar-stack { width: 100%; height: 100%; display: flex; align-items: flex-end; }
.bar { width: 100%; min-height: 2px; border-radius: 3px 3px 1px 1px; transition: height .2s; }
.bar.request { background: linear-gradient(180deg, #60a5fa, #6366f1); }
.bar.token { background: linear-gradient(180deg, #c084fc, #8b5cf6); }
.bar-label { font-size: 8px; color: #a0a6b3; margin-top: 3px; height: 10px; }
.timeline-legend { display: flex; gap: 16px; margin-top: 8px; font-size: 11px; color: #909399; }
.timeline-legend span { display: flex; align-items: center; gap: 5px; }
.legend { width: 9px; height: 9px; border-radius: 3px; display: inline-block; }
.legend.request { background: #6366f1; }
.legend.token { background: #8b5cf6; }
.mini-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; margin-bottom: 14px; }
.mini-card { background: #fff; border: 1px solid #ebeef5; border-radius: 10px; padding: 12px; }
.mini-label { font-size: 11px; color: #909399; }
.mini-value { font-size: 22px; font-weight: 800; margin-top: 3px; color: #303133; }
.mini-value.ok { color: #059669; }
.mini-value.warn { color: #d97706; }
.mini-value.danger { color: #dc2626; }
.muted { color: #909399; font-size: 11px; }
@media (max-width: 1100px) { .overview-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 700px) { .overview-grid, .mini-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
