<template>
  <div class="page-wrapper about-page">
    <section class="hero">
      <div class="hero-top">
        <div class="hero-id">
          <div class="avatar">{{ initial }}</div>
          <div class="hero-text">
            <div class="hero-name-row">
              <h2>{{ profile.name || '还没有填写姓名' }}</h2>
              <span class="hero-badge" v-if="profile.role || profile.company">
                {{ [profile.role, profile.company].filter(Boolean).join(' · ') }}
              </span>
            </div>
            <p class="hero-sub">AI 对你的长期理解 · 每一项都可以被修正或遗忘</p>
            <div class="hero-tags" v-if="profile.interests?.length">
              <span v-for="i in profile.interests.slice(0, 6)" :key="i" class="soft-tag">{{ i }}</span>
            </div>
          </div>
        </div>
        <div class="hero-actions">
          <el-button :icon="MagicStick" :loading="extracting" @click="extractMemories">整理记忆</el-button>
          <el-button :icon="Edit" type="primary" plain @click="$router.push('/settings')">编辑资料</el-button>
        </div>
      </div>

      <div class="hero-stats">
        <div v-for="s in stats" :key="s.key" class="hero-stat">
          <span class="num" :class="s.key">{{ s.value }}</span>
          <span class="label">{{ s.label }}</span>
        </div>
      </div>
    </section>

    <div class="about-grid">
      <section class="page-card understanding-card">
        <div class="section-head">
          <div class="section-title">
            <span class="section-icon">✦</span>
            <h3>AI 对你的理解</h3>
          </div>
          <span class="muted" v-if="profile.last_analysis">更新于 {{ fmt(profile.last_analysis) }}</span>
        </div>

        <blockquote v-if="profile.insights?.routine" class="routine-quote">
          {{ profile.insights.routine }}
        </blockquote>

        <div class="block" v-if="profile.interests?.length">
          <div class="block-title">关注领域</div>
          <div class="tag-row">
            <span v-for="i in profile.interests" :key="i" class="interest-chip">{{ i }}</span>
          </div>
        </div>

        <div class="block two-col" v-if="profile.habits?.length || profile.insights?.patterns?.length">
          <div v-if="profile.habits?.length">
            <div class="block-title">工作习惯</div>
            <ul class="tick-list">
              <li v-for="h in profile.habits" :key="h">{{ h }}</li>
            </ul>
          </div>
          <div v-if="profile.insights?.patterns?.length">
            <div class="block-title">观察到的规律</div>
            <ul class="tick-list pattern">
              <li v-for="p in profile.insights.patterns" :key="p">{{ p }}</li>
            </ul>
          </div>
        </div>

        <div class="block" v-if="profile.insights?.suggestions?.length">
          <div class="block-title">给你的建议</div>
          <div class="suggestion-list">
            <div v-for="s in profile.insights.suggestions" :key="textOf(s)" class="suggestion-row">
              <span class="suggestion-dot"></span>
              <span>{{ textOf(s) }}</span>
            </div>
          </div>
        </div>

        <el-empty
          v-if="!profile.insights?.routine && !profile.interests?.length && !profile.habits?.length"
          description="还没有足够的活动数据。使用一段时间后，AI 会在这里形成对你的理解。"
          :image-size="64"
        />
      </section>

      <section class="page-card profile-card">
        <div class="section-head">
          <div class="section-title">
            <span class="section-icon">◎</span>
            <h3>我的画像</h3>
          </div>
          <el-button link type="primary" @click="$router.push('/settings')">完善</el-button>
        </div>

        <div class="block" v-if="profile.contacts?.length">
          <div class="block-title">重要联系人</div>
          <div class="contact-list">
            <div v-for="c in profile.contacts" :key="c.name" class="contact-row">
              <span class="contact-avatar">{{ (c.name || '?').slice(0, 1) }}</span>
              <div class="contact-main">
                <span class="contact-name">{{ c.name }}</span>
                <span class="muted" v-if="c.relation">{{ c.relation }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="block" v-if="profile.projects?.length">
          <div class="block-title">正在推进</div>
          <div v-for="p in profile.projects" :key="p.name" class="project-row">
            <div class="project-main">
              <span class="project-name">{{ p.name }}</span>
              <span class="muted" v-if="p.deadline">截止 {{ p.deadline }}</span>
            </div>
            <el-tag v-if="p.status" size="small" effect="plain">{{ p.status }}</el-tag>
          </div>
        </div>

        <div class="empty-soft" v-if="!profile.contacts?.length && !profile.projects?.length">
          <p>在设置里补充姓名、角色和项目，助手会更懂你的上下文。</p>
        </div>
      </section>

      <section class="page-card entity-card">
        <div class="section-head">
          <div class="section-title">
            <span class="section-icon">◇</span>
            <h3>实体图谱</h3>
            <span class="count" v-if="entities.length">{{ entities.length }}</span>
          </div>
          <el-select v-model="entityType" size="small" clearable placeholder="全部类型" style="width:120px" @change="loadEntities">
            <el-option label="人物" value="person" />
            <el-option label="项目" value="project" />
            <el-option label="术语" value="term" />
          </el-select>
        </div>
        <p v-if="!entitiesSupported" class="muted">
          当前数据库不支持实体图谱（需要 PostgreSQL + pgvector）。画像与回顾不受影响。
        </p>
        <div v-else-if="entities.length === 0" class="empty-soft">
          <p>还没有抽取到实体。多聊聊人、项目和术语，它们会出现在这里。</p>
        </div>
        <div v-else class="entity-list">
          <div v-for="e in entities" :key="e.id" class="entity-row">
            <div class="entity-main">
              <span class="entity-avatar">{{ (e.name || '?').slice(0, 1) }}</span>
              <div class="entity-text">
                <span class="entity-name">{{ e.name }}</span>
                <span class="muted" v-if="e.sources?.length">来自 {{ e.sources.length }} 处内容</span>
              </div>
              <el-tag size="small" effect="plain">{{ typeLabel(e.type) }}</el-tag>
            </div>
            <el-popconfirm title="忘掉这个实体？不会删除原始内容。" @confirm="forgetEntity(e)">
              <template #reference><el-button link type="danger" size="small">遗忘</el-button></template>
            </el-popconfirm>
          </div>
        </div>
      </section>

      <section class="page-card review-card">
        <div class="section-head">
          <div class="section-title">
            <span class="section-icon">↻</span>
            <h3>最近回顾</h3>
          </div>
          <el-button link type="primary" @click="$router.push('/insights')">查看全部</el-button>
        </div>
        <div v-if="reviews.length === 0" class="empty-soft">
          <p>还没有每日回顾。每天结束时会自动生成一份。</p>
        </div>
        <div v-for="r in reviews" :key="r.id" class="review-row">
          <div class="review-date">{{ r.day }}</div>
          <div class="review-summary">{{ r.summary }}</div>
        </div>
      </section>

      <section class="page-card full-row candidates-card">
        <div class="section-head">
          <div class="section-title">
            <span class="section-icon">✓</span>
            <h3>待审核记忆</h3>
            <span class="count" v-if="candidates.length">{{ candidates.length }}</span>
          </div>
          <span class="muted">来自对话、邮件或外部消息；确认后才会进入长期记忆。</span>
        </div>
        <div v-if="candidates.length === 0" class="empty-soft">
          <p>没有待审核的记忆。点「整理记忆」从最近的对话中抽取。</p>
        </div>
        <div v-for="c in candidates" :key="c.id" class="candidate-row">
          <div class="candidate-main">
            <div class="candidate-content">{{ c.content }}</div>
            <div class="candidate-meta">
              <el-tag size="small" effect="plain">{{ kindLabel(c.kind) }}</el-tag>
              <el-tag size="small" :type="c.trust === 'trusted' ? 'success' : 'warning'">
                {{ c.trust === 'trusted' ? '可信来源' : '外部内容' }}
              </el-tag>
              <span class="muted">置信度 {{ c.confidence }}</span>
              <span class="muted" v-if="c.source_type">{{ c.source_type }}</span>
            </div>
          </div>
          <div class="candidate-actions">
            <el-button size="small" type="primary" @click="approveCandidate(c)">记住</el-button>
            <el-button size="small" @click="rejectCandidate(c)">忽略</el-button>
          </div>
        </div>
      </section>

      <section class="page-card full-row records-card">
        <div class="section-head">
          <div class="section-title">
            <span class="section-icon">▤</span>
            <h3>长期记忆</h3>
            <span class="count" v-if="records.length">{{ records.length }}</span>
          </div>
          <span class="muted">Bot 每次对话会按相关度读取；每条都可以遗忘。</span>
        </div>
        <div v-if="records.length === 0" class="empty-soft">
          <p>还没有长期记忆。审核通过的候选记忆会沉淀在这里。</p>
        </div>
        <div class="record-grid">
          <div v-for="r in records" :key="r.id" class="record-card">
            <div class="record-content">{{ r.content }}</div>
            <div class="record-foot">
              <el-tag size="small" effect="plain">{{ kindLabel(r.kind) }}</el-tag>
              <span class="importance" :title="`重要度 ${r.importance}`">
                <i v-for="n in 5" :key="n" class="dot" :class="{ on: n <= importanceOf(r) }"></i>
              </span>
              <span class="muted">{{ fmt(r.updated_at) }}</span>
              <el-popconfirm title="忘掉这条记忆？不会删除原始内容。" @confirm="forgetRecord(r)">
                <template #reference><el-button link type="danger" size="small">遗忘</el-button></template>
              </el-popconfirm>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
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

const initial = computed(() => (profile.value.name || '我').slice(0, 1))

const stats = computed(() => [
  { key: 'records', label: '长期记忆', value: records.value.length },
  { key: 'candidates', label: '待审核', value: candidates.value.length },
  { key: 'entities', label: '实体', value: entities.value.length },
  { key: 'reviews', label: '回顾', value: reviews.value.length },
])

function fmt(value: string) {
  return value ? formatBackendDate(value) : ''
}

function importanceOf(record: any) {
  const n = Number(record?.importance)
  if (!Number.isFinite(n)) return 0
  return Math.max(1, Math.min(5, Math.round(n)))
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
.about-page { max-width: 1180px; display: flex; flex-direction: column; gap: 16px; }

.hero {
  position: relative;
  overflow: hidden;
  border-radius: 18px;
  padding: 22px 24px 18px;
  background:
    radial-gradient(1200px 260px at 10% -40%, rgba(99, 102, 241, .35), transparent 60%),
    radial-gradient(900px 240px at 90% -30%, rgba(168, 85, 247, .28), transparent 60%),
    linear-gradient(135deg, #1e1b4b, #312e81 60%, #4c1d95);
  color: #eef2ff;
  box-shadow: 0 18px 40px -22px rgba(49, 46, 129, .65);
}
.hero-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; }
.hero-id { display: flex; gap: 16px; align-items: center; min-width: 0; }
.avatar {
  width: 66px; height: 66px; border-radius: 20px; flex-shrink: 0;
  background: linear-gradient(135deg, #a5b4fc, #c4b5fd);
  color: #312e81; font-size: 26px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 8px 24px -8px rgba(165, 180, 252, .8);
}
.hero-text { min-width: 0; }
.hero-name-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.hero-name-row h2 { margin: 0; font-size: 22px; letter-spacing: .5px; color: #fff; }
.hero-badge {
  font-size: 12px; padding: 2px 10px; border-radius: 999px;
  background: rgba(255, 255, 255, .14); border: 1px solid rgba(255, 255, 255, .18);
}
.hero-sub { margin: 6px 0 0; font-size: 12.5px; color: rgba(238, 242, 255, .66); }
.hero-tags { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
.soft-tag {
  font-size: 11.5px; padding: 2px 9px; border-radius: 999px;
  background: rgba(255, 255, 255, .1); color: #e0e7ff;
}
.hero-actions { display: flex; gap: 8px; flex-shrink: 0; }
.hero-actions :deep(.el-button) {
  background: rgba(255, 255, 255, .1); border-color: rgba(255, 255, 255, .22); color: #eef2ff;
}
.hero-actions :deep(.el-button--primary) { background: #6366f1; border-color: #818cf8; }
.hero-actions :deep(.el-button:hover) { background: rgba(255, 255, 255, .18); }

.hero-stats {
  display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px; margin-top: 20px;
}
.hero-stat {
  background: rgba(255, 255, 255, .08);
  border: 1px solid rgba(255, 255, 255, .1);
  border-radius: 12px; padding: 10px 14px;
  display: flex; flex-direction: column; gap: 2px;
  backdrop-filter: blur(4px);
}
.hero-stat .num { font-size: 22px; font-weight: 700; color: #fff; line-height: 1.2; }
.hero-stat .num.candidates { color: #fbbf24; }
.hero-stat .label { font-size: 12px; color: rgba(238, 242, 255, .6); }

.about-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; align-items: start; }
.full-row { grid-column: 1 / -1; }

.section-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 14px; }
.section-title { display: flex; align-items: center; gap: 8px; min-width: 0; }
.section-title h3 { margin: 0; font-size: 15px; color: #1a1a2e; }
.section-icon {
  width: 24px; height: 24px; border-radius: 8px; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  background: #eef2ff; color: #4f46e5; font-size: 13px;
}
.count {
  display: inline-block; padding: 1px 8px; border-radius: 999px;
  background: #eef4ff; color: #2f6fbf; font-size: 11px; font-weight: 600;
}

.block { margin-top: 16px; }
.block:first-of-type { margin-top: 0; }
.block-title { font-size: 12px; color: #909399; margin-bottom: 8px; letter-spacing: .3px; }
.block.two-col { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }

.routine-quote {
  margin: 0 0 4px; padding: 14px 16px; border-radius: 12px;
  background: linear-gradient(135deg, #f5f9ff, #eef4ff);
  border: 1px solid #dbe7ff; border-left: 3px solid #6366f1;
  font-size: 13.5px; line-height: 1.85; color: #2c3550;
}

.tag-row { display: flex; gap: 6px; flex-wrap: wrap; }
.interest-chip {
  font-size: 12px; padding: 3px 11px; border-radius: 999px;
  background: #f4f6fb; color: #4b5563; border: 1px solid #e8ecf5;
}

.tick-list { margin: 0; padding: 0; list-style: none; }
.tick-list li {
  position: relative; padding-left: 18px; font-size: 13px; line-height: 1.85; color: #606266;
}
.tick-list li::before {
  content: '✓'; position: absolute; left: 0; top: 0;
  color: #22c55e; font-size: 12px;
}
.tick-list.pattern li::before { content: '◎'; color: #6366f1; }

.suggestion-list { display: flex; flex-direction: column; gap: 8px; }
.suggestion-row {
  display: flex; gap: 10px; align-items: flex-start;
  font-size: 13px; line-height: 1.7; color: #334155;
  background: #f8faff; border: 1px solid #eef2ff; border-radius: 10px; padding: 9px 12px;
}
.suggestion-dot {
  width: 6px; height: 6px; border-radius: 50%; background: #6366f1;
  margin-top: 8px; flex-shrink: 0;
}

.contact-list { display: flex; flex-direction: column; gap: 2px; }
.contact-row { display: flex; align-items: center; gap: 10px; padding: 7px 0; }
.contact-avatar {
  width: 30px; height: 30px; border-radius: 50%; flex-shrink: 0;
  background: #eef2ff; color: #4f46e5; font-size: 13px; font-weight: 600;
  display: flex; align-items: center; justify-content: center;
}
.contact-main { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
.contact-name { font-size: 13px; color: #303133; }

.project-row {
  display: flex; justify-content: space-between; align-items: center; gap: 12px;
  padding: 9px 0; border-bottom: 1px dashed #eef0f4;
}
.project-row:last-child { border-bottom: none; }
.project-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.project-name { font-size: 13px; color: #303133; }

.entity-list { display: flex; flex-direction: column; }
.entity-row {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 9px 0; border-bottom: 1px solid #f4f5f8;
}
.entity-row:last-child { border-bottom: none; }
.entity-main { display: flex; align-items: center; gap: 10px; min-width: 0; }
.entity-avatar {
  width: 28px; height: 28px; border-radius: 9px; flex-shrink: 0;
  background: #f3f0ff; color: #7c3aed; font-size: 12px; font-weight: 600;
  display: flex; align-items: center; justify-content: center;
}
.entity-text { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.entity-name { font-size: 13px; color: #303133; font-weight: 500; }

.review-row { padding: 12px 0; border-bottom: 1px solid #f4f5f8; }
.review-row:last-child { border-bottom: none; padding-bottom: 0; }
.review-date {
  display: inline-block; font-size: 11px; color: #6366f1; font-weight: 600;
  background: #eef2ff; padding: 1px 8px; border-radius: 999px; margin-bottom: 6px;
}
.review-summary { font-size: 13px; line-height: 1.75; color: #303133; }

.candidate-row, .record-row {
  display: flex; justify-content: space-between; align-items: flex-start; gap: 14px;
  padding: 12px 0; border-bottom: 1px solid #f4f5f8;
}
.candidate-row:last-child, .record-row:last-child { border-bottom: none; }
.candidate-main, .record-main { min-width: 0; flex: 1; }
.candidate-content, .record-content { font-size: 13px; line-height: 1.7; color: #303133; }
.candidate-meta { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 6px; }
.candidate-actions { display: flex; gap: 6px; flex-shrink: 0; }

.record-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.record-card {
  border: 1px solid #eef0f6; border-radius: 12px; padding: 12px 14px;
  background: #fcfcfe; transition: border-color .18s, box-shadow .18s;
}
.record-card:hover { border-color: #dbe3f5; box-shadow: 0 10px 24px -18px rgba(49, 46, 129, .5); }
.record-foot { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 9px; }
.importance { display: inline-flex; gap: 3px; align-items: center; }
.importance .dot { width: 5px; height: 5px; border-radius: 50%; background: #e2e8f0; display: inline-block; }
.importance .dot.on { background: #f59e0b; }

.empty-soft {
  border: 1px dashed #e4e8f2; border-radius: 12px; padding: 18px;
  text-align: center; background: #fafbff;
}
.empty-soft p { margin: 0; font-size: 12.5px; line-height: 1.7; color: #9aa3b2; }

.muted { color: #909399; font-size: 12px; }

@media (max-width: 960px) {
  .about-grid { grid-template-columns: 1fr; }
  .record-grid { grid-template-columns: 1fr; }
  .hero-top { flex-direction: column; }
  .hero-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .block.two-col { grid-template-columns: 1fr; }
}
</style>
