<template>
  <div class="page-wrapper">
    <div class="page-header">
      <div>
        <h2>人物</h2>
        <p class="sub">从邮件、日程、会议、笔记和随手记里聚合出的人物时间线。</p>
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
        <el-button :loading="backfilling" @click="backfill">重建索引</el-button>
      </div>
    </div>

    <el-row :gutter="16">
      <el-col :xs="24" :md="8">
        <div class="page-card">
          <div class="page-card-body">
            <div v-loading="loading">
              <div v-for="p in people" :key="p.id" class="person-row"
                   :class="{ active: active?.id === p.id }" @click="select(p)">
                <div class="person-avatar">{{ (p.display_name || '?')[0] }}</div>
                <div class="person-main">
                  <div class="person-name">{{ p.display_name }}</div>
                  <div class="person-sub">{{ p.mention_count }} 条记录 · {{ p.last_interaction ? fmt(p.last_interaction) : '暂无互动' }}</div>
                </div>
              </div>
              <div v-if="!loading && !people.length" class="empty">
                <el-icon :size="28"><UserFilled /></el-icon>
                <p>还没有人物索引。点击「重建索引」。</p>
              </div>
            </div>
          </div>
        </div>
      </el-col>

      <el-col :xs="24" :md="16">
        <div v-if="active" class="page-card">
          <div class="page-card-body">
            <div class="detail-head">
              <div class="person-avatar big">{{ (active.display_name || '?')[0] }}</div>
              <div>
                <h3>{{ active.display_name }}</h3>
                <div class="person-sub">{{ (active.emails || []).join(' · ') || '未记录邮箱' }}</div>
              </div>
              <el-tag v-if="commitmentCount" type="warning" style="margin-left:auto">{{ commitmentCount }} 个承诺</el-tag>
            </div>

            <el-tabs v-model="tab">
              <el-tab-pane label="时间线" name="timeline">
                <div v-loading="loadingDetail" class="timeline">
                  <div v-for="item in timeline" :key="item.id" class="timeline-item">
                    <div class="timeline-dot" :class="item.type"></div>
                    <div class="timeline-body">
                      <div class="timeline-head">
                        <el-tag size="small" effect="plain">{{ typeText(item.type) }}</el-tag>
                        <span class="muted">{{ fmt(item.occurred_at) }}</span>
                        <el-link v-if="item.link" type="primary" @click="openLink(item)">打开</el-link>
                      </div>
                      <div class="timeline-title">{{ item.title || '(无标题)' }}</div>
                      <div class="timeline-snippet">{{ item.snippet }}</div>
                    </div>
                  </div>
                  <div v-if="!loadingDetail && !timeline.length" class="empty"><p>还没有可展示的互动。</p></div>
                </div>
              </el-tab-pane>
              <el-tab-pane label="承诺" name="commitments">
                <div v-if="commitments.length" class="commitment-list">
                  <div v-for="c in commitments" :key="c.id" class="commitment-item">
                    <div>{{ c.content }}</div>
                    <div class="muted">{{ fmt(c.created_at) }} · 置信度 {{ c.confidence }}</div>
                  </div>
                </div>
                <div v-else class="empty"><p>没有记录到未完成承诺。</p></div>
              </el-tab-pane>
            </el-tabs>
          </div>
        </div>
        <div v-else class="page-card">
          <div class="page-card-body empty"><p>选择左侧人物查看时间线。</p></div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, UserFilled } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import client from '@/api/client'
import { formatBackendDate } from '@/utils/date'

const router = useRouter()
const people = ref<any[]>([])
const active = ref<any>(null)
const timeline = ref<any[]>([])
const commitments = ref<any[]>([])
const loading = ref(false)
const loadingDetail = ref(false)
const backfilling = ref(false)
const tab = ref('timeline')

const commitmentCount = computed(() => commitments.value.length)
const fmt = (v: string | null) => (v ? formatBackendDate(v) : '—')
const typeText = (type: string) => ({ mail: '邮件', event: '日程', meeting: '会议', note: '笔记', capture: '随手记', memory: '记忆' } as any)[type] || type

async function loadAll() {
  loading.value = true
  try {
    const res = await client.get('/people')
    people.value = res.data?.items || []
    if (people.value.length && !active.value) await select(people.value[0])
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

async function select(person: any) {
  active.value = person
  tab.value = 'timeline'
  loadingDetail.value = true
  try {
    const [t, c] = await Promise.all([
      client.get(`/people/${person.id}/timeline`, { params: { limit: 80 } }),
      client.get(`/people/${person.id}/commitments`),
    ])
    timeline.value = t.data?.items || []
    commitments.value = c.data?.items || []
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '加载人物失败')
  } finally {
    loadingDetail.value = false
  }
}

async function backfill() {
  backfilling.value = true
  try {
    const res = await client.post('/people/backfill')
    ElMessage.success(`索引完成：${res.data?.people || 0} 人，${res.data?.mentions || 0} 条记录`)
    active.value = null
    await loadAll()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '重建失败')
  } finally {
    backfilling.value = false
  }
}

function openLink(item: any) {
  if (!item.link) return
  const path = item.link.split('?')[0]
  router.push(path)
}

onMounted(loadAll)
</script>

<style scoped>
.sub { color: #94a3b8; font-size: 12.5px; margin-top: 4px; }
.header-actions { display: flex; gap: 8px; }
.person-row { display: flex; align-items: center; gap: 10px; padding: 10px; border-radius: 10px; cursor: pointer; }
.person-row:hover, .person-row.active { background: #eef2ff; }
.person-avatar { width: 36px; height: 36px; border-radius: 50%; background: #e0e7ff; color: #4338ca; display: flex; align-items: center; justify-content: center; font-weight: 700; }
.person-avatar.big { width: 48px; height: 48px; font-size: 18px; }
.person-main { min-width: 0; }
.person-name { font-size: 13.5px; font-weight: 700; color: #111827; }
.person-sub { font-size: 11px; color: #94a3b8; }
.detail-head { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.detail-head h3 { margin: 0; font-size: 18px; }
.timeline { min-height: 120px; }
.timeline-item { display: flex; gap: 12px; padding: 10px 0; border-bottom: 1px dashed #eef0f4; }
.timeline-dot { width: 8px; height: 8px; border-radius: 50%; background: #6366f1; margin-top: 7px; flex-shrink: 0; }
.timeline-dot.mail { background: #0ea5e9; }
.timeline-dot.event { background: #f59e0b; }
.timeline-dot.capture { background: #10b981; }
.timeline-body { min-width: 0; }
.timeline-head { display: flex; align-items: center; gap: 8px; font-size: 11px; }
.timeline-title { font-size: 13.5px; font-weight: 600; color: #1f2937; margin-top: 3px; }
.timeline-snippet { font-size: 12px; color: #64748b; line-height: 1.6; margin-top: 3px; }
.commitment-item { padding: 10px 0; border-bottom: 1px dashed #eef0f4; font-size: 13px; color: #334155; }
.muted { color: #94a3b8; }
.empty { display: flex; flex-direction: column; align-items: center; gap: 8px; color: #94a3b8; padding: 36px 0; }
</style>
