<template>
  <div class="page-wrapper about-page">
    <div class="page-header">
      <div>
        <h2>关于我</h2>
        <p class="sub">AI 对你的长期理解、实体关系和最近回顾。所有内容都可以被修正或遗忘。</p>
      </div>
      <div class="header-actions">
        <el-button :icon="MagicStick" :loading="extracting" @click="extractMemories">整理记忆</el-button>
        <el-button :icon="Edit" @click="$router.push('/settings')">编辑资料</el-button>
      </div>
    </div>

    <div class="about-grid">
      <section class="page-card profile-card">
        <div class="profile-head">
          <div class="avatar">{{ (profile.name || '我').slice(0, 1) }}</div>
          <div>
            <h3>{{ profile.name || '还没有填写姓名' }}</h3>
            <p class="muted">{{ [profile.role, profile.company].filter(Boolean).join(' · ') || '补充资料后，助手会更懂你' }}</p>
          </div>
        </div>

        <div class="block" v-if="profile.contacts?.length">
          <div class="block-title">联系人</div>
          <div class="tag-row">
            <el-tag v-for="c in profile.contacts" :key="c.name" size="small" effect="plain">
              {{ c.name }}<span v-if="c.relation" class="tag-sub">（{{ c.relation }}）</span>
            </el-tag>
          </div>
        </div>

        <div class="block" v-if="profile.projects?.length">
          <div class="block-title">项目</div>
          <div v-for="p in profile.projects" :key="p.name" class="project-row">
            <span>{{ p.name }}</span>
            <span class="muted">{{ p.deadline || p.status || '' }}</span>
          </div>
        </div>
      </section>

      <section class="page-card">
        <div class="section-head">
          <h3>AI 对你的理解</h3>
          <span class="muted" v-if="profile.last_analysis">更新于 {{ fmt(profile.last_analysis) }}</span>
        </div>

        <div v-if="profile.insights?.routine" class="insight-box">
          {{ profile.insights.routine }}
        </div>

        <div class="block" v-if="profile.interests?.length">
          <div class="block-title">关注领域</div>
          <div class="tag-row">
            <el-tag v-for="i in profile.interests" :key="i" size="small">{{ i }}</el-tag>
          </div>
        </div>

        <div class="block" v-if="profile.habits?.length">
          <div class="block-title">工作习惯</div>
          <ul class="plain-list">
            <li v-for="h in profile.habits" :key="h">{{ h }}</li>
          </ul>
        </div>

        <div class="block" v-if="profile.insights?.patterns?.length">
          <div class="block-title">观察到的规律</div>
          <ul class="plain-list">
            <li v-for="p in profile.insights.patterns" :key="p">{{ p }}</li>
          </ul>
        </div>

        <div class="block" v-if="profile.insights?.suggestions?.length">
          <div class="block-title">建议</div>
          <ul class="plain-list suggestion">
            <li v-for="s in profile.insights.suggestions" :key="textOf(s)">{{ textOf(s) }}</li>
          </ul>
        </div>

        <el-empty
          v-if="!profile.insights?.routine && !profile.interests?.length && !profile.habits?.length"
          description="还没有足够的活动数据。使用一段时间后，AI 会在这里形成对你的理解。"
          :image-size="70"
        />
      </section>

      <section class="page-card">
        <div class="section-head">
          <h3>实体图谱</h3>
          <el-select v-model="entityType" size="small" clearable placeholder="全部类型" style="width:120px" @change="loadEntities">
            <el-option label="人物" value="person" />
            <el-option label="项目" value="project" />
            <el-option label="术语" value="term" />
          </el-select>
        </div>
        <p v-if="!entitiesSupported" class="muted">
          当前数据库不支持实体图谱（需要 PostgreSQL + pgvector）。画像与回顾不受影响。
        </p>
        <div v-else-if="entities.length === 0" class="muted">还没有抽取到实体。</div>
        <div v-else class="entity-list">
          <div v-for="e in entities" :key="e.id" class="entity-row">
            <div class="entity-main">
              <span class="entity-name">{{ e.name }}</span>
              <el-tag size="small" effect="plain">{{ typeLabel(e.type) }}</el-tag>
              <span class="muted" v-if="e.sources?.length">来自 {{ e.sources.length }} 处内容</span>
            </div>
            <el-popconfirm title="忘掉这个实体？不会删除原始内容。" @confirm="forgetEntity(e)">
              <template #reference><el-button link type="danger" size="small">遗忘</el-button></template>
            </el-popconfirm>
          </div>
        </div>
      </section>

      <section class="page-card full-row">
        <div class="section-head">
          <h3>待审核记忆 <span class="count" v-if="candidates.length">{{ candidates.length }}</span></h3>
          <span class="muted">来自对话、邮件或外部消息；确认后才会进入长期记忆。</span>
        </div>
        <div v-if="candidates.length === 0" class="muted">没有待审核的记忆。点「整理记忆」从最近的对话中抽取。</div>
        <div v-for="c in candidates" :key="c.id" class="candidate-row">
          <div class="candidate-main">
            <div class="candidate-content">{{ c.content }}</div>
            <div class="candidate-meta">
              <el-tag size="small" effect="plain">{{ kindLabel(c.kind) }}</el-tag>
              <el-tag size="small" :type="c.trust === 'trusted' ? 'success' : 'warning'">
                {{ c.trust === 'trusted' ? '可信来源' : '外部内容' }}
              </el-tag>
              <span class="muted">置信度 {{ c.confidence }}</span>
              <span class="muted">{{ c.source_type }}</span>
            </div>
          </div>
          <div class="candidate-actions">
            <el-button size="small" type="primary" @click="approveCandidate(c)">记住</el-button>
            <el-button size="small" @click="rejectCandidate(c)">忽略</el-button>
          </div>
        </div>
      </section>

      <section class="page-card full-row">
        <div class="section-head">
          <h3>长期记忆 <span class="count" v-if="records.length">{{ records.length }}</span></h3>
          <span class="muted">Bot 每次对话会按相关度读取；每条都可以遗忘。</span>
        </div>
        <div v-if="records.length === 0" class="muted">还没有长期记忆。</div>
        <div v-for="r in records" :key="r.id" class="record-row">
          <div class="record-main">
            <div class="record-content">{{ r.content }}</div>
            <div class="candidate-meta">
              <el-tag size="small" effect="plain">{{ kindLabel(r.kind) }}</el-tag>
              <span class="muted">重要度 {{ r.importance }}</span>
              <span class="muted">{{ fmt(r.updated_at) }}</span>
            </div>
          </div>
          <el-popconfirm title="忘掉这条记忆？不会删除原始内容。" @confirm="forgetRecord(r)">
            <template #reference><el-button link type="danger" size="small">遗忘</el-button></template>
          </el-popconfirm>
        </div>
      </section>

      <section class="page-card">
        <div class="section-head">
          <h3>最近回顾</h3>
          <el-button link type="primary" @click="$router.push('/insights')">查看全部</el-button>
        </div>
        <div v-if="reviews.length === 0" class="muted">还没有每日回顾。</div>
        <div v-for="r in reviews" :key="r.id" class="review-row">
          <div class="review-date">{{ r.day }}</div>
          <div class="review-summary">{{ r.summary }}</div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Edit, MagicStick } from '@element-plus/icons-vue'
import client from '@/api/client'
import { formatBackendDate } from '@/utils/date'

const profile = ref<any>({ contacts: [], projects: [], interests: [], habits: [], insights: {} })
const entities = ref<any[]>([])
const entitiesSupported = ref(true)
const entityType = ref('')
const reviews = ref<any[]>([])
const candidates = ref<any[]>([])
const records = ref<any[]>([])
const extracting = ref(false)

function fmt(value: string) {
  return value ? formatBackendDate(value) : ''
}

function textOf(item: any) {
  return typeof item === 'string' ? item : item?.text || ''
}

function typeLabel(type: string) {
  return ({ person: '人物', project: '项目', term: '术语' } as Record<string, string>)[type] || type
}

function kindLabel(kind: string) {
  return ({
    fact: '事实', preference: '偏好', commitment: '承诺',
    relationship: '关系', project: '项目',
  } as Record<string, string>)[kind] || kind
}

async function loadMemory() {
  try {
    const [c, r] = await Promise.all([
      client.get('/memory/candidates', { params: { status: 'pending', limit: 100 } }),
      client.get('/memory/records', { params: { limit: 100 } }),
    ])
    candidates.value = c.data.items || []
    records.value = r.data.items || []
  } catch {
    candidates.value = []
    records.value = []
  }
}

async function extractMemories() {
  extracting.value = true
  try {
    const { data } = await client.post('/memory/extract', { hours: 24 })
    ElMessage.success(`已整理，新增 ${data.queued || 0} 条候选记忆`)
    await loadMemory()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '整理失败')
  } finally {
    extracting.value = false
  }
}

async function approveCandidate(c: any) {
  try {
    await client.post(`/memory/candidates/${c.id}/approve`)
    ElMessage.success('已记住')
    await loadMemory()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  }
}

async function rejectCandidate(c: any) {
  try {
    await client.post(`/memory/candidates/${c.id}/reject`)
    await loadMemory()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  }
}

async function forgetRecord(r: any) {
  try {
    await client.delete(`/memory/records/${r.id}`)
    ElMessage.success('已遗忘')
    await loadMemory()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  }
}

async function loadProfile() {
  try {
    const { data } = await client.get('/memory/profile')
    profile.value = { contacts: [], projects: [], interests: [], habits: [], insights: {}, ...data }
  } catch {
    ElMessage.error('加载画像失败')
  }
}

async function loadEntities() {
  try {
    const { data } = await client.get('/memory/entities', {
      params: { limit: 200, ...(entityType.value ? { entity_type: entityType.value } : {}) },
    })
    entities.value = data.items || []
    entitiesSupported.value = data.supported !== false
  } catch {
    entities.value = []
    entitiesSupported.value = false
  }
}

async function forgetEntity(e: any) {
  try {
    await client.delete(`/memory/entities/${encodeURIComponent(e.id)}`)
    ElMessage.success(`已遗忘「${e.name}」`)
    await loadEntities()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '遗忘失败')
  }
}

async function loadReviews() {
  try {
    const { data } = await client.get('/insights/daily', { params: { days: 3 } })
    reviews.value = data || []
  } catch {
    reviews.value = []
  }
}

onMounted(async () => {
  await Promise.all([loadProfile(), loadEntities(), loadReviews(), loadMemory()])
})
</script>

<style scoped>
.about-page { max-width: 1180px; }
.about-page .sub { margin: 4px 0 0; font-size: 12px; color: #909399; }
.header-actions { display: flex; gap: 8px; }
.full-row { grid-column: 1 / -1; }
.count { display: inline-block; margin-left: 6px; padding: 1px 7px; border-radius: 10px; background: #eef4ff; color: #2f6fbf; font-size: 11px; font-weight: 600; }
.candidate-row, .record-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; padding: 11px 0; border-bottom: 1px solid #f0f2f5; }
.candidate-row:last-child, .record-row:last-child { border-bottom: none; }
.candidate-main, .record-main { min-width: 0; flex: 1; }
.candidate-content, .record-content { font-size: 13px; line-height: 1.7; color: #303133; }
.candidate-meta { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 6px; }
.candidate-actions { display: flex; gap: 6px; flex-shrink: 0; }
.about-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; align-items: start; }
.profile-card { grid-row: span 2; }
.profile-head { display: flex; align-items: center; gap: 14px; margin-bottom: 18px; }
.avatar { width: 54px; height: 54px; border-radius: 50%; background: linear-gradient(135deg, #6366f1, #a855f7); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: 600; }
.profile-head h3 { margin: 0; font-size: 18px; color: #1a1a2e; }
.profile-head p { margin: 4px 0 0; }
.block { margin-top: 16px; }
.block-title { font-size: 12px; color: #909399; margin-bottom: 8px; }
.tag-row { display: flex; gap: 6px; flex-wrap: wrap; }
.tag-sub { opacity: .75; }
.project-row { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; color: #303133; padding: 7px 0; border-bottom: 1px dashed #eef0f4; }
.project-row:last-child { border-bottom: none; }
.section-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; }
.section-head h3 { margin: 0; font-size: 15px; color: #1a1a2e; }
.insight-box { background: #f5f9ff; border: 1px solid #d9e9ff; border-radius: 10px; padding: 12px 14px; font-size: 13px; line-height: 1.8; color: #2c3550; }
.plain-list { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.9; color: #606266; }
.plain-list.suggestion li { color: #2f6fbf; }
.entity-list { display: flex; flex-direction: column; }
.entity-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 9px 0; border-bottom: 1px solid #f0f2f5; }
.entity-row:last-child { border-bottom: none; }
.entity-main { display: flex; align-items: center; gap: 8px; min-width: 0; }
.entity-name { font-size: 13px; color: #303133; font-weight: 500; }
.review-row { padding: 10px 0; border-bottom: 1px solid #f0f2f5; }
.review-row:last-child { border-bottom: none; }
.review-date { font-size: 12px; color: #909399; margin-bottom: 4px; }
.review-summary { font-size: 13px; line-height: 1.7; color: #303133; }
.muted { color: #909399; font-size: 12px; }
@media (max-width: 900px) {
  .about-grid { grid-template-columns: 1fr; }
  .profile-card { grid-row: auto; }
}
</style>
