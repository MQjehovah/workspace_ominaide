<template>
  <div class="page-wrapper about-page">
    <section class="hero">
      <div class="blob b1"></div>
      <div class="blob b2"></div>
      <div class="hero-top">
        <div class="hero-id">
          <div class="avatar-wrap">
            <div class="avatar">{{ initial }}</div>
            <span class="status-dot" title="正在学习"></span>
          </div>
          <div class="hero-text">
            <div class="hero-name-row">
              <h1>{{ profile.name || '还没有填写姓名' }}</h1>
              <span class="hero-badge" v-if="profile.role || profile.company">
                {{ [profile.role, profile.company].filter(Boolean).join(' · ') }}
              </span>
            </div>
            <p class="hero-sub">AI 对你的长期理解 · 每一项都可以被修正或遗忘</p>
          </div>
        </div>
        <div class="hero-actions">
          <el-tooltip content="刷新" placement="top">
            <el-button :icon="Refresh" circle :loading="refreshing" @click="refreshAll" />
          </el-tooltip>
          <el-button :icon="Edit" @click="$router.push('/settings')">编辑资料</el-button>
        </div>
      </div>

      <div class="hero-stats">
        <button v-for="s in stats" :key="s.key" class="hero-stat" @click="openTab(s.tab)">
          <span class="num" :class="s.key">{{ s.value }}</span>
          <span class="label">{{ s.label }}</span>
        </button>
      </div>
    </section>

    <nav class="about-tabs">
      <button
        v-for="t in tabs"
        :key="t.key"
        class="about-tab"
        :class="{ active: tab === t.key }"
        @click="tab = t.key"
      >
        {{ t.label }}
        <span v-if="t.count" class="tab-count">{{ t.count }}</span>
      </button>
    </nav>

    <div v-if="loading" class="overview-grid">
      <div class="page-card skeleton-card" v-for="n in 3" :key="n">
        <div class="sk-line w40"></div>
        <div class="sk-line w90"></div>
        <div class="sk-line w70"></div>
        <div class="sk-line w80"></div>
      </div>
    </div>

    <div
      v-else
      class="tab-panel"
      :class="tab === 'overview' ? 'overview-grid' : (tab === 'memory' ? 'memory-stack' : 'graph-single')"
    >
      <section v-if="tab === 'overview'" id="understanding" class="page-card understanding-card reveal" style="--d: 0ms">
        <div class="section-head">
          <div class="section-title">
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

      <section v-if="tab === 'overview'" id="profile" class="page-card profile-card reveal" style="--d: 60ms">
        <div class="section-head">
          <div class="section-title">
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

      <section v-if="tab === 'graph'" id="entities" class="page-card entity-card reveal" style="--d: 0ms">
        <div class="section-head">
          <div class="section-title">
            <h3>实体图谱</h3>
          </div>
          <div class="entity-tools">
            <span class="graph-summary" v-if="entities.length">{{ entities.length }} 个实体 · {{ entityLinks.length }} 条关系</span>
            <el-select v-model="entityType" size="small" clearable placeholder="全部类型" style="width:118px" @change="loadEntities">
              <el-option label="人物" value="person" />
              <el-option label="项目" value="project" />
              <el-option label="术语" value="term" />
            </el-select>
          </div>
        </div>
        <p v-if="!entitiesSupported" class="muted">
          当前数据库不支持实体图谱（需要 PostgreSQL + pgvector）。画像与回顾不受影响。
        </p>
        <div v-else-if="entities.length === 0" class="empty-soft">
          <p>还没有抽取到实体。多聊聊人、项目和术语，它们会出现在这里。</p>
        </div>
        <template v-else>
          <EntityGraph
            ref="graphRef"
            :nodes="entities"
            :links="entityLinks"
            :selected-id="selectedEntityId"
            @select="selectEntity"
          />
          <div v-if="selectedEntity" class="entity-detail">
            <div class="entity-detail-main">
              <span class="entity-avatar" :class="selectedEntity.type">{{ (selectedEntity.name || '?').slice(0, 1) }}</span>
              <div class="entity-text">
                <span class="entity-name">{{ selectedEntity.name }}</span>
                <span class="muted">
                  {{ typeLabel(selectedEntity.type) }}
                  · 来自 {{ selectedEntity.source_count || 0 }} 处内容
                  <template v-if="selectedEntity.last_seen"> · 最近 {{ fmt(selectedEntity.last_seen) }}</template>
                </span>
              </div>
            </div>
            <el-popconfirm title="忘掉这个实体？不会删除原始内容。" @confirm="forgetEntity(selectedEntity)">
              <template #reference><el-button link type="danger" size="small">遗忘</el-button></template>
            </el-popconfirm>
          </div>
          <div class="graph-foot">
            <div class="graph-legend">
              <span><i class="legend-dot person"></i>人物</span>
              <span><i class="legend-dot project"></i>项目</span>
              <span><i class="legend-dot term"></i>术语</span>
            </div>
            <span class="muted">{{ selectedEntity ? '再次点击节点可取消选择' : '点击节点查看详情' }}</span>
          </div>
        </template>
      </section>

      <section v-if="tab === 'overview'" id="reviews" class="page-card review-card reveal" style="--d: 180ms">
        <div class="section-head">
          <div class="section-title">
            <h3>最近回顾</h3>
          </div>
          <el-button link type="primary" @click="$router.push('/insights')">查看全部</el-button>
        </div>
        <div v-if="reviews.length === 0" class="empty-soft">
          <p>还没有每日回顾。每天结束时会自动生成一份。</p>
        </div>
        <div class="review-list">
          <div v-for="r in reviews" :key="r.id" class="review-row">
            <div class="review-date">{{ r.day }}</div>
            <div class="review-summary">{{ r.summary }}</div>
          </div>
        </div>
      </section>

      <div v-if="tab === 'memory'" class="memory-status">
        <div class="memory-status-item">
          <b>{{ candidates.length }}</b>
          <span>待审核</span>
        </div>
        <div class="memory-status-item">
          <b>{{ records.length }}</b>
          <span>长期记忆</span>
        </div>
        <p class="muted">每日凌晨自动整理；低置信度的候选会先放在这里等你确认。</p>
      </div>

      <section v-if="tab === 'memory' && candidates.length" id="candidates" class="page-card candidates-card reveal" style="--d: 0ms">
        <div class="section-head">
          <div class="section-title">
            <h3>待审核记忆</h3>
            <span class="count warn" v-if="candidates.length">{{ candidates.length }}</span>
          </div>
          <span class="muted">来自对话、邮件或外部消息；确认后才会进入长期记忆。</span>
        </div>
        <div v-if="candidates.length === 0" class="empty-soft">
          <p>没有待审核的记忆。每日凌晨会自动分析聊天和事件，低置信度的候选会出现在这里。</p>
        </div>
        <transition-group name="list" tag="div" class="candidate-list">
          <div
            v-for="c in candidates"
            :key="c.id"
            class="candidate-row"
            :class="c.trust === 'trusted' ? 'trusted' : 'untrusted'"
          >
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
        </transition-group>
      </section>

      <section v-if="tab === 'memory'" id="records" class="page-card records-card reveal" style="--d: 60ms">
        <div class="section-head">
          <div class="section-title">
            <h3>长期记忆</h3>
            <span class="count" v-if="records.length">{{ records.length }}</span>
          </div>
          <span class="muted">Bot 每次对话会按相关度读取；每条都可以遗忘。</span>
        </div>

        <div class="record-toolbar" v-if="records.length">
          <el-input
            v-model="recordQuery"
            size="small"
            clearable
            :prefix-icon="Search"
            placeholder="搜索记忆内容"
            class="record-search"
          />
          <el-select v-model="recordKind" size="small" clearable placeholder="全部类型" class="record-kind">
            <el-option v-for="k in kindOptions" :key="k.value" :label="k.label" :value="k.value" />
          </el-select>
          <span class="muted">{{ filteredRecords.length }} / {{ records.length }}</span>
        </div>

        <div v-if="records.length === 0" class="empty-soft">
          <p>还没有长期记忆。审核通过的候选记忆会沉淀在这里。</p>
        </div>
        <div v-else-if="filteredRecords.length === 0" class="empty-soft">
          <p>没有匹配的记忆，换个关键词试试。</p>
        </div>
        <transition-group v-else name="list" tag="div" class="record-grid">
          <article v-for="r in filteredRecords" :key="r.id" class="record-card">
            <div class="record-head">
              <span class="kind-chip" :class="r.kind">{{ kindLabel(r.kind) }}</span>
              <span class="importance" :title="`重要度 ${r.importance}`">
                <i v-for="n in 5" :key="n" class="dot" :class="{ on: n <= importanceOf(r) }"></i>
              </span>
              <el-popconfirm title="忘掉这条记忆？不会删除原始内容。" @confirm="forgetRecord(r)">
                <template #reference><button class="record-forget">遗忘</button></template>
              </el-popconfirm>
            </div>
            <p class="record-content" :class="{ expanded: expanded.has(r.id) }">{{ r.content }}</p>
            <button v-if="isLong(r.content)" class="record-more" @click="toggleRecord(r.id)">
              {{ expanded.has(r.id) ? '收起' : '展开' }}
            </button>
            <div class="record-time">{{ fmt(r.updated_at) }}</div>
          </article>
        </transition-group>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Edit, Refresh, Search } from '@element-plus/icons-vue'
import client from '@/api/client'
import { formatBackendDate } from '@/utils/date'
import EntityGraph from '@/components/EntityGraph.vue'

const profile = ref<any>({ contacts: [], projects: [], interests: [], habits: [], insights: {} })
const entities = ref<any[]>([])
const entityLinks = ref<any[]>([])
const entitiesSupported = ref(true)
const entityType = ref('')
const selectedEntityId = ref<string | null>(null)
const graphRef = ref<any>(null)
const reviews = ref<any[]>([])
const candidates = ref<any[]>([])
const records = ref<any[]>([])
const refreshing = ref(false)
const loading = ref(true)

const recordQuery = ref('')
const recordKind = ref('')
const expanded = reactive(new Set<number>())

const kindOptions = [
  { label: '事实', value: 'fact' },
  { label: '偏好', value: 'preference' },
  { label: '承诺', value: 'commitment' },
  { label: '关系', value: 'relationship' },
  { label: '项目', value: 'project' },
]

type TabKey = 'overview' | 'memory' | 'graph'
const tab = ref<TabKey>('overview')

const initial = computed(() => (profile.value.name || '我').slice(0, 1))

const selectedEntity = computed(() =>
  entities.value.find((e) => e.id === selectedEntityId.value) || null,
)

const tabs = computed(() => [
  { key: 'overview' as TabKey, label: '概览', count: 0 },
  { key: 'memory' as TabKey, label: '记忆库', count: candidates.value.length },
  { key: 'graph' as TabKey, label: '关系图谱', count: entities.value.length },
])

const stats = computed(() => [
  { key: 'records', label: '长期记忆', value: records.value.length, tab: 'memory' as TabKey },
  { key: 'candidates', label: '待审核', value: candidates.value.length, tab: 'memory' as TabKey },
  { key: 'entities', label: '实体', value: entities.value.length, tab: 'graph' as TabKey },
  { key: 'reviews', label: '回顾', value: reviews.value.length, tab: 'overview' as TabKey },
])

const filteredRecords = computed(() => {
  const q = recordQuery.value.trim().toLowerCase()
  return records.value.filter((r) => {
    if (recordKind.value && r.kind !== recordKind.value) return false
    if (!q) return true
    return String(r.content || '').toLowerCase().includes(q)
  })
})

function openTab(next: TabKey) {
  tab.value = next
  document.querySelector('.about-tabs')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function toggleRecord(id: number) {
  if (expanded.has(id)) expanded.delete(id)
  else expanded.add(id)
}

function isLong(text: string) {
  return String(text || '').length > 120
}

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

async function approveCandidate(c: any) {
  try {
    await client.post(`/memory/candidates/${c.id}/approve`)
    candidates.value = candidates.value.filter((x) => x.id !== c.id)
    ElMessage.success('已记住')
    await Promise.all([loadMemory()])
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  }
}

async function rejectCandidate(c: any) {
  try {
    await client.post(`/memory/candidates/${c.id}/reject`)
    candidates.value = candidates.value.filter((x) => x.id !== c.id)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  }
}

async function forgetRecord(r: any) {
  try {
    await client.delete(`/memory/records/${r.id}`)
    records.value = records.value.filter((x) => x.id !== r.id)
    ElMessage.success('已遗忘')
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
    const { data } = await client.get('/memory/entities/graph', {
      params: { limit: 200, ...(entityType.value ? { entity_type: entityType.value } : {}) },
    })
    entities.value = data.nodes || []
    entityLinks.value = data.links || []
    entitiesSupported.value = data.supported !== false
    if (!entities.value.some((e: any) => e.id === selectedEntityId.value)) {
      selectedEntityId.value = null
    }
  } catch {
    entities.value = []
    entityLinks.value = []
    entitiesSupported.value = false
    selectedEntityId.value = null
  }
}

function selectEntity(id: string) {
  selectedEntityId.value = selectedEntityId.value === id ? null : id
}

async function forgetEntity(e: any) {
  try {
    await client.delete(`/memory/entities/${encodeURIComponent(e.id)}`)
    ElMessage.success(`已遗忘「${e.name}」`)
    selectedEntityId.value = null
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

async function loadAll() {
  await Promise.all([loadProfile(), loadEntities(), loadReviews(), loadMemory()])
}

async function refreshAll() {
  refreshing.value = true
  try {
    await loadAll()
  } finally {
    refreshing.value = false
  }
}

onMounted(async () => {
  try {
    await loadAll()
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.about-page { max-width: 1080px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; }
.about-page .page-card { padding: 18px 20px; }

.hero {
  position: relative; overflow: hidden;
  border-radius: 20px; padding: 24px 26px 20px;
  background:
    radial-gradient(700px 280px at 8% -60%, rgba(99, 102, 241, .55), transparent 62%),
    radial-gradient(620px 260px at 92% -40%, rgba(168, 85, 247, .45), transparent 62%),
    linear-gradient(135deg, #151238, #241d5c 55%, #3b1670);
  color: #eef2ff;
  box-shadow: 0 26px 54px -30px rgba(49, 46, 129, .8);
}
.blob {
  position: absolute; border-radius: 50%; filter: blur(60px); opacity: .5;
  animation: float 12s ease-in-out infinite;
}
.blob.b1 { width: 260px; height: 260px; left: -80px; bottom: -140px; background: #6366f1; }
.blob.b2 { width: 220px; height: 220px; right: 6%; top: -120px; background: #a855f7; animation-delay: -6s; }
@keyframes float {
  0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
  50% { transform: translate3d(14px, -12px, 0) scale(1.08); }
}

.hero-top { position: relative; display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; }
.hero-id { display: flex; gap: 16px; align-items: center; min-width: 0; }
.avatar-wrap { position: relative; flex-shrink: 0; }
.avatar {
  width: 68px; height: 68px; border-radius: 22px;
  background: linear-gradient(135deg, #c7d2fe, #ddd6fe);
  color: #312e81; font-size: 27px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 12px 28px -14px rgba(199, 210, 254, .9);
}
.status-dot {
  position: absolute; right: -3px; bottom: -3px; width: 14px; height: 14px;
  border-radius: 50%; background: #34d399; border: 3px solid #241d5c;
  box-shadow: 0 0 0 4px rgba(52, 211, 153, .18);
}
.hero-text { min-width: 0; }
.hero-name-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.hero-name-row h1 { margin: 0; font-size: 23px; letter-spacing: .2px; color: #fff; }
.hero-badge {
  font-size: 11.5px; padding: 3px 10px; border-radius: 999px;
  background: rgba(255, 255, 255, .13); border: 1px solid rgba(255, 255, 255, .18);
}
.hero-sub { margin: 7px 0 0; font-size: 12.5px; color: rgba(238, 242, 255, .62); }
.hero-actions { display: flex; gap: 8px; flex-shrink: 0; flex-wrap: wrap; justify-content: flex-end; }
.hero-actions :deep(.el-button) {
  background: rgba(255, 255, 255, .09);
  border-color: rgba(255, 255, 255, .2);
  color: #eef2ff;
}
.hero-actions :deep(.el-button:hover) {
  background: rgba(255, 255, 255, .17);
  border-color: rgba(255, 255, 255, .3);
  color: #fff;
}

.hero-stats {
  position: relative; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px; margin-top: 22px;
}
.hero-stat {
  display: flex; flex-direction: column; gap: 1px; text-align: left;
  padding: 11px 14px; border-radius: 13px; cursor: pointer;
  background: rgba(255, 255, 255, .07);
  border: 1px solid rgba(255, 255, 255, .1);
  color: #eef2ff;
  transition: background .18s, transform .18s, border-color .18s;
}
.hero-stat:hover {
  background: rgba(255, 255, 255, .13);
  border-color: rgba(255, 255, 255, .22);
  transform: translateY(-2px);
}
.hero-stat .num { font-size: 23px; font-weight: 700; line-height: 1.15; font-variant-numeric: tabular-nums; }
.hero-stat .num.candidates { color: #fbbf24; }
.hero-stat .label { font-size: 11.5px; color: rgba(238, 242, 255, .6); }

.about-tabs {
  display: flex; gap: 4px; width: max-content; max-width: 100%;
  padding: 4px; border-radius: 12px; background: #eef1f7; overflow-x: auto;
  scrollbar-width: none;
}
.about-tabs::-webkit-scrollbar { display: none; }
.about-tab {
  flex-shrink: 0; display: inline-flex; align-items: center; gap: 6px;
  border: none; background: transparent; color: #64748b;
  font-size: 13px; padding: 7px 16px; border-radius: 9px; cursor: pointer;
  transition: color .15s, background .15s, box-shadow .15s;
}
.about-tab:hover { color: #4338ca; }
.about-tab.active {
  background: #fff; color: #312e81; font-weight: 600;
  box-shadow: 0 2px 8px rgba(49, 46, 129, .12);
}
.tab-count {
  font-size: 10.5px; font-weight: 600; padding: 1px 6px; border-radius: 999px;
  background: #eef2ff; color: #4f46e5;
}

.tab-panel { animation: fade-in .22s ease both; }
@keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }
.overview-grid {
  display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(0, 1fr);
  gap: 16px; align-items: start;
}
.review-card { grid-column: 1 / -1; }
.memory-stack { display: flex; flex-direction: column; gap: 16px; }
.graph-single { display: block; }
section[id] { scroll-margin-top: 12px; }

.memory-status {
  display: flex; align-items: center; gap: 18px; flex-wrap: wrap;
  padding: 12px 20px; border-radius: 14px;
  background: #fff; border: 1px solid #e8edf8;
}
.memory-status-item { display: flex; align-items: baseline; gap: 6px; }
.memory-status-item b { font-size: 19px; color: #312e81; font-variant-numeric: tabular-nums; }
.memory-status-item span { font-size: 11.5px; color: #94a3b8; }
.memory-status .muted { margin: 0 0 0 auto; font-size: 11.5px; }

.reveal { animation: rise .45s cubic-bezier(.2, .7, .3, 1) both; animation-delay: var(--d, 0ms); }
@keyframes rise {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.section-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 14px; }
.section-title { display: flex; align-items: center; gap: 8px; min-width: 0; }
.section-title h3 { margin: 0; display: flex; align-items: center; gap: 8px; font-size: 15px; color: #111827; }
.section-title h3::before {
  content: ''; width: 3px; height: 14px; border-radius: 2px;
  background: linear-gradient(180deg, #6366f1, #a855f7);
}
.count {
  display: inline-block; padding: 1px 8px; border-radius: 999px;
  background: #eef4ff; color: #2f6fbf; font-size: 11px; font-weight: 600;
}
.count.warn { background: #fff7e6; color: #b45309; }

.block { margin-top: 16px; }
.block:first-of-type { margin-top: 0; }
.block-title { font-size: 11.5px; color: #94a3b8; margin-bottom: 8px; letter-spacing: .4px; }
.block.two-col { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }

.routine-quote {
  margin: 0 0 4px; padding: 14px 16px; border-radius: 12px;
  background: linear-gradient(135deg, #f7f9ff, #eef2ff);
  border: 1px solid #e2e8ff; border-left: 3px solid #6366f1;
  font-size: 13.5px; line-height: 1.85; color: #2c3550;
}

.tag-row { display: flex; gap: 6px; flex-wrap: wrap; }
.interest-chip {
  font-size: 12px; padding: 4px 12px; border-radius: 999px;
  background: #f5f7fc; color: #4b5563; border: 1px solid #e9edf6;
  transition: all .15s;
}
.interest-chip:hover { border-color: #c7d2fe; background: #f5f7ff; color: var(--brand-600); }

.tick-list { margin: 0; padding: 0; list-style: none; }
.tick-list li {
  position: relative; padding-left: 18px; font-size: 13px; line-height: 1.85; color: #5b667a;
}
.tick-list li::before { content: '✓'; position: absolute; left: 0; top: 0; color: #10b981; font-size: 11px; }
.tick-list.pattern li::before { content: '◎'; color: #6366f1; }

.suggestion-list { display: flex; flex-direction: column; gap: 8px; }
.suggestion-row {
  display: flex; gap: 10px; align-items: flex-start;
  font-size: 13px; line-height: 1.7; color: #334155;
  background: #f8faff; border: 1px solid #eef2ff; border-radius: 10px; padding: 9px 12px;
  transition: border-color .15s, background .15s;
}
.suggestion-row:hover { background: #f4f7ff; border-color: #dbe4ff; }
.suggestion-dot {
  width: 6px; height: 6px; border-radius: 50%; background: #6366f1;
  margin-top: 8px; flex-shrink: 0;
}

.contact-list { display: flex; flex-direction: column; gap: 2px; }
.contact-row { display: flex; align-items: center; gap: 10px; padding: 7px 0; }
.contact-avatar {
  width: 30px; height: 30px; border-radius: 50%; flex-shrink: 0;
  background: linear-gradient(135deg, #eef2ff, #e0e7ff); color: #4f46e5;
  font-size: 13px; font-weight: 600;
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

.entity-tools { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; justify-content: flex-end; }
.graph-summary { font-size: 11.5px; color: #94a3b8; }
.entity-card :deep(.entity-graph) { height: 560px; }
.graph-legend { display: flex; align-items: center; gap: 10px; font-size: 11.5px; color: #64748b; }
.graph-legend span { display: inline-flex; align-items: center; gap: 4px; }
.legend-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.legend-dot.person { background: #6366f1; }
.legend-dot.project { background: #10b981; }
.legend-dot.term { background: #f59e0b; }
.entity-detail {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  margin-top: 12px; padding: 10px 12px; border-radius: 12px;
  background: #f8faff; border: 1px solid #e8edf8;
}
.entity-detail-main { display: flex; align-items: center; gap: 10px; min-width: 0; }
.entity-main { display: flex; align-items: center; gap: 10px; min-width: 0; }
.entity-avatar {
  width: 28px; height: 28px; border-radius: 9px; flex-shrink: 0;
  background: #f3f0ff; color: #7c3aed; font-size: 12px; font-weight: 600;
  display: flex; align-items: center; justify-content: center;
}
.entity-avatar.person { background: #eef2ff; color: #4f46e5; }
.entity-avatar.project { background: #ecfdf5; color: #059669; }
.entity-avatar.term { background: #fffbeb; color: #d97706; }
.entity-text { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.entity-name { font-size: 13px; color: #303133; font-weight: 500; }
.graph-foot {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  margin-top: 10px; font-size: 11.5px;
}

.review-list { display: flex; flex-direction: column; }
.review-row { padding: 12px 0; border-bottom: 1px solid #f4f5f8; }
.review-row:last-child { border-bottom: none; padding-bottom: 0; }
.review-date {
  display: inline-block; font-size: 11px; color: #4f46e5; font-weight: 600;
  background: #eef2ff; padding: 1px 9px; border-radius: 999px; margin-bottom: 6px;
}
.review-summary { font-size: 13px; line-height: 1.78; color: #334155; }

.candidate-list { display: flex; flex-direction: column; }
.candidate-row {
  display: flex; justify-content: space-between; align-items: flex-start; gap: 14px;
  padding: 12px 14px; margin-bottom: 8px;
  border-radius: 11px; border: 1px solid #eef1f7; background: #fcfdff;
  border-left: 3px solid #e2e8f0;
  transition: border-color .15s, box-shadow .15s;
}
.candidate-row.trusted { border-left-color: #10b981; }
.candidate-row.untrusted { border-left-color: #f59e0b; }
.candidate-row:hover { box-shadow: 0 10px 24px -20px rgba(16, 24, 40, .4); }
.candidate-main { min-width: 0; flex: 1; }
.candidate-content { font-size: 13px; line-height: 1.7; color: #303133; }
.candidate-meta { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 6px; }
.candidate-actions { display: flex; gap: 6px; flex-shrink: 0; }

.record-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
.record-search { width: 240px; }
.record-kind { width: 118px; }

.record-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.record-card {
  border: 1px solid #eef0f6; border-radius: 13px; padding: 13px 15px;
  background: linear-gradient(180deg, #fdfdff, #fafbff);
  transition: border-color .18s, box-shadow .18s, transform .18s;
}
.record-card:hover {
  border-color: #dbe3f5;
  box-shadow: 0 16px 32px -26px rgba(30, 41, 59, .55);
  transform: translateY(-1px);
}
.record-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.kind-chip {
  font-size: 10.5px; font-weight: 600; padding: 2px 9px; border-radius: 999px;
  background: #eef2ff; color: #4f46e5;
}
.kind-chip.preference { background: #f5f3ff; color: #7c3aed; }
.kind-chip.commitment { background: #fffbeb; color: #b45309; }
.kind-chip.relationship { background: #fdf2f8; color: #be185d; }
.kind-chip.project { background: #ecfdf5; color: #047857; }
.importance { display: inline-flex; gap: 3px; align-items: center; }
.importance .dot { width: 5px; height: 5px; border-radius: 50%; background: #e2e8f0; display: inline-block; }
.importance .dot.on { background: #f59e0b; }
.record-forget {
  margin-left: auto; border: none; background: transparent; cursor: pointer;
  font-size: 11px; color: #cbd5e1; transition: color .15s;
}
.record-card:hover .record-forget { color: #f87171; }
.record-content {
  margin: 0; font-size: 13px; line-height: 1.72; color: #303133;
  display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden;
  white-space: pre-wrap; word-break: break-word;
}
.record-content.expanded { display: block; -webkit-line-clamp: unset; }
.record-more {
  margin-top: 6px; border: none; background: none; padding: 0; cursor: pointer;
  font-size: 11.5px; color: var(--brand-500);
}
.record-more:hover { color: var(--brand-600); }
.record-time { margin-top: 8px; font-size: 11px; color: #a6b0c0; }

.list-enter-active, .list-leave-active { transition: all .2s ease; }
.list-enter-from { opacity: 0; transform: translateY(6px); }
.list-leave-to { opacity: 0; transform: scale(.98); }
.list-leave-active { position: absolute; }

.empty-soft {
  border: 1px dashed #e4e8f2; border-radius: 12px; padding: 18px;
  text-align: center; background: #fafbff;
}
.empty-soft p { margin: 0; font-size: 12.5px; line-height: 1.7; color: #9aa3b2; }

.muted { color: #94a3b8; font-size: 12px; }

.skeleton-card { padding: 18px; }
.sk-line {
  height: 12px; border-radius: 6px; margin-bottom: 10px;
  background: linear-gradient(90deg, #f1f4f9 25%, #e9edf5 37%, #f1f4f9 63%);
  background-size: 400% 100%;
  animation: shimmer 1.4s ease infinite;
}
.sk-line.w40 { width: 40%; }
.sk-line.w70 { width: 70%; }
.sk-line.w80 { width: 80%; }
.sk-line.w90 { width: 90%; }
@keyframes shimmer { 0% { background-position: 100% 50%; } 100% { background-position: 0 50%; } }

@media (max-width: 960px) {
  .overview-grid { grid-template-columns: 1fr; }
  .record-grid { grid-template-columns: 1fr; }
  .hero-top { flex-direction: column; }
  .hero-actions { justify-content: flex-start; }
  .block.two-col { grid-template-columns: 1fr; }
}

@media (max-width: 640px) {
  .about-page { gap: 12px; }
  .about-page .page-card { padding: 14px; }
  .hero { padding: 18px 16px 14px; border-radius: 16px; }
  .avatar { width: 54px; height: 54px; border-radius: 17px; font-size: 22px; }
  .hero-name-row h1 { font-size: 19px; }
  .hero-sub { font-size: 12px; }
  .hero-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); margin-top: 16px; }
  .hero-stat { padding: 10px 12px; }
  .hero-stat .num { font-size: 20px; }
  .hero-actions { width: 100%; }
  .hero-actions :deep(.el-button) { flex: 1; }
  .about-tabs { width: 100%; }
  .about-tab { flex: 1; justify-content: center; padding: 7px 10px; }
  .memory-status { gap: 12px; padding: 10px 14px; }
  .memory-status .muted { width: 100%; margin-left: 0; }
  .section-head { flex-wrap: wrap; gap: 8px; }
  .record-toolbar { gap: 8px; }
  .record-search { width: 100%; }
  .record-kind { width: 118px; }
  .candidate-row { flex-direction: column; }
  .candidate-actions { width: 100%; justify-content: flex-end; }
  .entity-tools { width: 100%; justify-content: space-between; }
  .entity-card :deep(.entity-graph) { height: 380px; }
  .entity-detail { flex-direction: column; align-items: flex-start; }
}

@media (prefers-reduced-motion: reduce) {
  .blob, .reveal, .sk-line { animation: none !important; }
  .record-card, .hero-stat { transition: none; }
}
</style>
