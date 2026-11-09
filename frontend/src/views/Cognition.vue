<template>
  <div class="page-wrapper">
    <div class="page-header" style="display:flex;align-items:center;justify-content:space-between">
      <div>
        <h2>协同</h2>
        <p style="color:#909399;font-size:13px;margin-top:4px">情境、提案、目标、工作区与授权</p>
      </div>
      <el-button :icon="Refresh" @click="refreshAll">刷新</el-button>
    </div>

    <el-tabs v-model="tab">
      <el-tab-pane label="情境" name="now">
        <div v-loading="loading.now" class="grid">
          <div class="page-card">
            <h3>当前</h3>
            <p class="muted">{{ now.generated_at || '还没有情境' }}</p>
            <p>在线设备：{{ now.presence?.machines?.length || 0 }}</p>
            <p>未读邮件：{{ now.inbox?.mail_unread || 0 }} · 钉钉：{{ now.inbox?.dingtalk_unread || 0 }} · 通知：{{ now.inbox?.notifications || 0 }}</p>
          </div>
          <div class="page-card">
            <h3>信号</h3>
            <el-tag v-for="s in now.signals || []" :key="s.type + (s.title || '')" style="margin:0 6px 6px 0">
              {{ s.type }}<span v-if="s.count"> · {{ s.count }}</span>
            </el-tag>
            <p v-if="!(now.signals || []).length" class="muted">暂时没有需要立即处理的信号</p>
          </div>
          <div class="page-card">
            <h3>接下来日程</h3>
            <div v-for="e in (now.calendar || []).slice(0, 5)" :key="e.id" class="row">
              <span>{{ (e.time || '').slice(11, 16) }}</span>
              <span>{{ e.title }}</span>
            </div>
            <p v-if="!(now.calendar || []).length" class="muted">没有日程</p>
          </div>
          <div class="page-card">
            <h3>待办</h3>
            <div v-for="t in (now.todos || []).slice(0, 5)" :key="t.id" class="row">
              <span>{{ t.title }}</span>
              <span class="muted">{{ t.meta?.due || '' }}</span>
            </div>
            <p v-if="!(now.todos || []).length" class="muted">没有待办</p>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="提案" name="proposals">
        <div class="page-card" v-loading="loading.proposals">
          <div style="display:flex;gap:8px;margin-bottom:12px">
            <el-select v-model="proposalStatus" style="width:140px" @change="loadProposals">
              <el-option label="待处理" value="new" />
              <el-option label="进行中" value="open" />
              <el-option label="全部" value="all" />
            </el-select>
            <el-button @click="loadProposals">刷新</el-button>
          </div>
          <div v-for="p in proposals" :key="p.id" class="proposal">
            <div>
              <div class="proposal-title">{{ p.title }}</div>
              <div class="muted">{{ p.reason }}</div>
              <div class="muted">置信度 {{ (p.confidence * 100).toFixed(0) }}% · {{ p.status }}</div>
            </div>
            <div>
              <el-button size="small" type="primary" @click="actProposal(p, 'accept')">接受</el-button>
              <el-button size="small" @click="actProposal(p, 'snooze')">稍后</el-button>
              <el-button size="small" @click="actProposal(p, 'dismiss')">忽略</el-button>
            </div>
          </div>
          <el-empty v-if="!proposals.length" description="没有提案" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="目标" name="goals">
        <div class="page-card" style="margin-bottom:14px">
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <el-input v-model="goalTitle" placeholder="目标，例如：周五前拿到预算确认" style="max-width:420px" />
            <el-input v-model="goalDescription" placeholder="背景（可选）" style="max-width:320px" />
            <el-button type="primary" @click="createGoal">创建目标</el-button>
          </div>
        </div>
        <div class="goal-layout">
          <div class="page-card">
            <div v-for="g in goals" :key="g.id" class="goal" :class="{ active: selectedGoal?.id === g.id }" @click="selectGoal(g)">
              <div class="proposal-title">{{ g.title }}</div>
              <div class="muted">{{ g.status }} · {{ g.created_by }}</div>
            </div>
            <el-empty v-if="!goals.length" description="没有目标" />
          </div>
          <div class="page-card" v-if="selectedGoal">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <h3>{{ selectedGoal.title }}</h3>
              <div>
                <el-button size="small" @click="planGoal(selectedGoal)">规划</el-button>
                <el-button size="small" type="primary" @click="tickGoal(selectedGoal)">推进</el-button>
              </div>
            </div>
            <p class="muted">{{ selectedGoal.description }}</p>
            <p>状态：{{ selectedGoal.status }} · 工作区：{{ selectedGoal.workspace_id || '-' }}</p>
            <el-table :data="tasks" size="small" stripe>
              <el-table-column prop="id" label="#" width="50" />
              <el-table-column prop="title" label="任务" min-width="200" />
              <el-table-column prop="agent_profile_key" label="角色" width="110" />
              <el-table-column prop="status" label="状态" width="110" />
              <el-table-column label="验收" width="80">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="verifyTask(row)">验收</el-button>
                </template>
              </el-table-column>
            </el-table>
            <div style="margin-top:10px">
              <el-button size="small" @click="openWorkspace(selectedGoal)">查看工作区</el-button>
              <el-button size="small" @click="exportWorkspace(selectedGoal)">导出</el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="Agent" name="agents">
        <div class="page-card">
          <h3>Agent 模板</h3>
          <p class="muted">Agent 是执行主体；只读模板不能执行写操作。角色级授权只影响该角色的调用。</p>
          <div class="agent-grid">
            <div v-for="a in agentProfiles" :key="a.key" class="agent-card">
              <div class="proposal-title">
                {{ a.title }}
                <el-tag size="small" :type="a.read_only ? 'info' : 'success'">
                  {{ a.read_only ? '只读' : '可执行' }}
                </el-tag>
              </div>
              <div class="muted">{{ a.key }} · 最多 {{ a.max_turns }} 轮</div>
              <div class="muted">{{ a.acceptance_hint }}</div>
              <el-button size="small" style="margin-top:8px" @click="grantForProfile(a)">
                添加该角色授权
              </el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="评估" name="evals">
        <div class="grid" style="margin-bottom:14px">
          <div class="page-card">
            <h3>通过率</h3>
            <p style="font-size:26px;font-weight:700">{{ ((evalReport.metrics?.pass_rate || 0) * 100).toFixed(1) }}%</p>
            <p class="muted">{{ evalReport.metrics?.passed || 0 }} / {{ evalReport.metrics?.total || 0 }}</p>
          </div>
          <div class="page-card">
            <h3>平均耗时</h3>
            <p style="font-size:26px;font-weight:700">{{ evalReport.metrics?.avg_ms || 0 }}ms</p>
            <p class="muted">p95 {{ evalReport.metrics?.p95_ms || 0 }}ms</p>
          </div>
          <div class="page-card">
            <h3>最近运行</h3>
            <p>{{ evalReport.generated_at || '还没有运行评估' }}</p>
            <p class="muted">python -m evals.cognition --user-id &lt;id&gt;</p>
          </div>
        </div>
        <div class="page-card">
          <el-table :data="evalReport.cases || []" size="small" stripe>
            <el-table-column prop="category" label="类别" width="120" />
            <el-table-column prop="name" label="用例" min-width="220" />
            <el-table-column label="结果" width="80">
              <template #default="{ row }">
                <el-tag size="small" :type="row.ok ? 'success' : 'danger'">
                  {{ row.ok ? '通过' : '失败' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="duration_ms" label="耗时(ms)" width="100" />
            <el-table-column prop="detail" label="详情" min-width="220" />
          </el-table>
          <el-empty v-if="!(evalReport.cases || []).length" description="还没有评估报告" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="授权" name="grants">
        <div class="page-card" style="margin-bottom:14px">
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <el-input v-model="grantKey" placeholder="能力，例如 send_email" style="max-width:260px" />
            <el-select v-model="grantScope" style="width:120px">
              <el-option label="一次" value="once" />
              <el-option label="今天" value="day" />
              <el-option label="一直" value="always" />
            </el-select>
            <el-select v-model="grantProfile" clearable placeholder="角色（可选）" style="width:140px">
              <el-option v-for="a in agentProfiles" :key="a.key" :label="a.title" :value="a.key" />
            </el-select>
            <el-button type="primary" @click="addGrant">添加授权</el-button>
          </div>
        </div>
        <div class="page-card">
          <el-table :data="grants" size="small" stripe>
            <el-table-column prop="capability_key" label="能力" min-width="220" />
            <el-table-column prop="decision" label="决定" width="90" />
            <el-table-column prop="scope" label="范围" width="90" />
            <el-table-column prop="agent_profile_key" label="角色" width="110" />
            <el-table-column prop="expires_at" label="过期" width="180" />
            <el-table-column label="" width="80">
              <template #default="{ row }">
                <el-button link type="danger" size="small" @click="removeGrant(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!grants.length" description="没有授权" />
        </div>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="workspaceVisible" title="工作区" width="min(760px, 94vw)">
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">
        <el-input v-model="newItemType" placeholder="类型" style="width:110px" />
        <el-input v-model="newItemContent" placeholder="记录或评论" style="flex:1;min-width:220px" />
        <el-button type="primary" @click="addWorkspaceItem">添加</el-button>
      </div>
      <el-table :data="workspace?.items || []" size="small" stripe>
        <el-table-column prop="type" label="类型" width="90" />
        <el-table-column label="内容" min-width="260">
          <template #default="{ row }">
            <el-input
              v-if="editingItemId === row.id"
              v-model="editingContent"
              size="small"
              @keyup.enter="saveItem(row)"
            />
            <span v-else>{{ itemText(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_by" label="来源" width="110" />
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <template v-if="editingItemId === row.id">
              <el-button link type="primary" size="small" @click="saveItem(row)">保存</el-button>
              <el-button link size="small" @click="editingItemId = 0">取消</el-button>
            </template>
            <template v-else>
              <el-button link size="small" @click="startEdit(row)">编辑</el-button>
              <el-button link type="danger" size="small" @click="deleteItem(row)">删除</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!(workspace?.items || []).length" description="工作区还没有记录" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import client from '@/api/client'

const tab = ref('now')
const loading = reactive({ now: false, proposals: false })
const now = ref<any>({})
const proposals = ref<any[]>([])
const proposalStatus = ref('new')
const goals = ref<any[]>([])
const selectedGoal = ref<any>(null)
const tasks = ref<any[]>([])
const goalTitle = ref('')
const goalDescription = ref('')
const grants = ref<any[]>([])
const grantKey = ref('')
const grantScope = ref('always')
const grantProfile = ref('')
const agentProfiles = ref<any[]>([])
const workspaceVisible = ref(false)
const workspace = ref<any>(null)
const newItemType = ref('comment')
const newItemContent = ref('')
const editingItemId = ref(0)
const editingContent = ref('')
const evalReport = ref<any>({})

async function loadNow() {
  loading.now = true
  try { now.value = (await client.get('/cognition/now')).data } finally { loading.now = false }
}
async function loadProposals() {
  loading.proposals = true
  try { proposals.value = (await client.get('/proposals', { params: { status: proposalStatus.value, limit: 50 } })).data.items || [] } finally { loading.proposals = false }
}
async function actProposal(p: any, action: string) {
  await client.post(`/proposals/${p.id}/act`, { action })
  ElMessage.success('已处理')
  await loadProposals()
}
async function loadGoals() {
  goals.value = (await client.get('/cognition/goals', { params: { status: 'all', limit: 100 } })).data
}
async function createGoal() {
  if (!goalTitle.value.trim()) return
  await client.post('/cognition/goals', { title: goalTitle.value, description: goalDescription.value })
  goalTitle.value = ''
  goalDescription.value = ''
  await loadGoals()
  ElMessage.success('已创建目标')
}
async function selectGoal(g: any) {
  selectedGoal.value = g
  tasks.value = (await client.get(`/cognition/goals/${g.id}/tasks`)).data
}
async function planGoal(g: any) {
  await client.post(`/cognition/goals/${g.id}/plan`)
  ElMessage.success('已规划')
  await loadGoals()
  await selectGoal({ ...g })
}
async function tickGoal(g: any) {
  const res = await client.post(`/cognition/goals/${g.id}/tick`)
  selectedGoal.value = res.data.goal
  tasks.value = res.data.tasks || []
  ElMessage.success('已推进')
  await loadGoals()
}
async function verifyTask(t: any) {
  await client.post(`/cognition/tasks/${t.id}/verify`)
  ElMessage.success('已验收')
  if (selectedGoal.value) await selectGoal(selectedGoal.value)
}
function itemText(row: any) {
  const content = row?.content
  if (typeof content === 'string') return content
  if (content && typeof content === 'object') {
    return content.text ? String(content.text) : JSON.stringify(content)
  }
  return ''
}
async function openWorkspace(g: any) {
  if (!g.workspace_id) return
  workspace.value = (await client.get(`/cognition/workspaces/${g.workspace_id}`)).data
  workspaceVisible.value = true
}
async function refreshWorkspace() {
  if (!workspace.value?.id) return
  workspace.value = (await client.get(`/cognition/workspaces/${workspace.value.id}`)).data
}
async function addWorkspaceItem() {
  if (!workspace.value?.id || !newItemContent.value.trim()) return
  await client.post(`/cognition/workspaces/${workspace.value.id}/items`, {
    type: newItemType.value || 'comment',
    content: { text: newItemContent.value.trim() },
    created_by: 'user',
  })
  newItemContent.value = ''
  await refreshWorkspace()
}
function startEdit(row: any) {
  editingItemId.value = row.id
  editingContent.value = itemText(row)
}
async function saveItem(row: any) {
  if (!workspace.value?.id) return
  await client.patch(`/cognition/workspaces/${workspace.value.id}/items/${row.id}`, {
    content: { text: editingContent.value },
  })
  editingItemId.value = 0
  await refreshWorkspace()
}
async function deleteItem(row: any) {
  if (!workspace.value?.id) return
  await client.delete(`/cognition/workspaces/${workspace.value.id}/items/${row.id}`)
  await refreshWorkspace()
}
async function exportWorkspace(g: any) {
  if (!g.workspace_id) return
  window.open(`/api/cognition/workspaces/${g.workspace_id}/export`)
}
async function loadGrants() {
  grants.value = (await client.get('/capabilities/grants')).data
}
async function loadAgentProfiles() {
  agentProfiles.value = (await client.get('/cognition/agent-profiles')).data
}
function grantForProfile(profile: any) {
  grantProfile.value = profile.key
  tab.value = 'grants'
  ElMessage.info(`请填写能力，授权将只作用于 ${profile.title} 角色`)
}
async function addGrant() {
  if (!grantKey.value.trim()) return
  await client.post('/capabilities/grants', {
    capability_key: grantKey.value.trim(),
    scope: grantScope.value,
    agent_profile_key: grantProfile.value || undefined,
  })
  grantKey.value = ''
  await loadGrants()
}
async function removeGrant(row: any) {
  await client.delete(`/capabilities/grants/${row.id}`)
  await loadGrants()
}
async function loadEvals() {
  evalReport.value = (await client.get('/cognition/evals')).data
}
async function refreshAll() {
  await Promise.all([
    loadNow(),
    loadProposals(),
    loadGoals(),
    loadGrants(),
    loadAgentProfiles(),
    loadEvals(),
  ])
}
onMounted(refreshAll)
</script>

<style scoped>
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; }
.grid .page-card { padding: 16px; }
.muted { color: #909399; font-size: 12px; }
.row { display: flex; justify-content: space-between; gap: 12px; padding: 6px 0; border-bottom: 1px solid #f2f3f5; }
.proposal { display: flex; justify-content: space-between; gap: 12px; padding: 12px 0; border-bottom: 1px solid #f2f3f5; }
.proposal-title { font-weight: 600; margin-bottom: 4px; }
.goal-layout { display: grid; grid-template-columns: 300px 1fr; gap: 14px; }
.goal { padding: 10px; border-radius: 8px; cursor: pointer; border: 1px solid transparent; }
.goal:hover, .goal.active { background: #f5f7ff; border-color: #dbe3ff; }
.agent-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; margin-top: 12px; }
.agent-card { border: 1px solid #e6e8ef; border-radius: 10px; padding: 12px; }
@media (max-width: 900px) { .goal-layout { grid-template-columns: 1fr; } }
</style>
