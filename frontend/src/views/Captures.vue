<template>
  <div class="page-wrapper">
    <div class="page-header">
      <div>
        <h2>随手记</h2>
        <p class="sub">链接、文章、图片和文本，先收进来，再慢慢分析。</p>
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="dialog = true">快速采集</el-button>
      </div>
    </div>

    <div class="capture-stats">
      <div class="capture-stat"><b>{{ items.length }}</b><span>全部</span></div>
      <div class="capture-stat"><b>{{ count('ready') }}</b><span>已分析</span></div>
      <div class="capture-stat"><b>{{ count('processing') }}</b><span>分析中</span></div>
      <div class="capture-stat"><b>{{ count('inbox') }}</b><span>待处理</span></div>
    </div>

    <div class="page-card">
      <div class="page-card-body">
        <div v-loading="loading" class="capture-grid">
          <div v-for="item in items" :key="item.id" class="capture-card" @click="open(item)">
            <div class="capture-head">
              <el-tag size="small" :type="statusType(item.status)">{{ statusText(item.status) }}</el-tag>
              <span class="capture-kind">{{ kindText(item.kind) }}</span>
              <span class="capture-time">{{ fmt(item.created_at) }}</span>
            </div>
            <div class="capture-title">{{ item.title || item.url || '随手记' }}</div>
            <div class="capture-summary">{{ item.summary || item.content || '等待分析…' }}</div>
            <div class="capture-tags">
              <el-tag v-for="tag in (item.tags || []).slice(0, 5)" :key="tag" size="small" effect="plain">{{ tag }}</el-tag>
            </div>
          </div>
          <div v-if="!loading && !items.length" class="capture-empty">
            <el-icon :size="32"><Collection /></el-icon>
            <p>还没有随手记。先收藏一个链接或图片。</p>
          </div>
        </div>
      </div>
    </div>

    <el-dialog v-model="dialog" title="快速采集" width="620px">
      <el-tabs v-model="mode">
        <el-tab-pane label="链接 / 文章" name="link">
          <el-form label-width="80px">
            <el-form-item label="URL">
              <el-input v-model="form.url" placeholder="https://..." />
            </el-form-item>
            <el-form-item label="标题">
              <el-input v-model="form.title" placeholder="可选，留空自动提取" />
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="form.text" type="textarea" :rows="3" placeholder="可选" />
            </el-form-item>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="文本" name="text">
          <el-form label-width="80px">
            <el-form-item label="标题">
              <el-input v-model="form.title" placeholder="可选" />
            </el-form-item>
            <el-form-item label="内容">
              <el-input v-model="form.text" type="textarea" :rows="7" placeholder="粘贴一段文字、想法或待整理内容" />
            </el-form-item>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="图片 / 文件" name="file">
          <el-form label-width="80px">
            <el-form-item label="文件">
              <input type="file" @change="onFile" />
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="form.text" type="textarea" :rows="3" placeholder="图片里有什么？可选" />
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存并分析</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="drawer" :title="active?.title || '随手记'" size="620px">
      <template v-if="active">
        <div class="detail-meta">
          <el-tag size="small" :type="statusType(active.status)">{{ statusText(active.status) }}</el-tag>
          <span>{{ kindText(active.kind) }}</span>
          <span>{{ fmt(active.created_at) }}</span>
        </div>
        <div v-if="active.url" class="detail-url">
          <a :href="active.url" target="_blank" rel="noopener">{{ active.url }}</a>
        </div>
        <h4>摘要</h4>
        <p class="detail-text">{{ active.summary || active.content || '等待分析…' }}</p>
        <template v-if="(active.key_points || []).length">
          <h4>关键点</h4>
          <ul class="detail-list"><li v-for="p in active.key_points" :key="p">{{ p }}</li></ul>
        </template>
        <template v-if="(active.people || []).length">
          <h4>人物</h4>
          <div class="capture-tags"><el-tag v-for="p in active.people" :key="p" size="small">{{ p }}</el-tag></div>
        </template>
        <template v-if="(active.tags || []).length">
          <h4>标签</h4>
          <div class="capture-tags"><el-tag v-for="t in active.tags" :key="t" size="small" effect="plain">{{ t }}</el-tag></div>
        </template>
        <el-divider />
        <div class="detail-actions">
          <el-button type="primary" @click="convert('note')">转笔记</el-button>
          <el-button @click="convert('todo')">转待办</el-button>
          <el-button @click="openEventConvert">转日程</el-button>
          <el-button @click="reanalyze">重新分析</el-button>
          <el-button type="danger" plain @click="remove">删除</el-button>
        </div>
      </template>
    </el-drawer>

    <el-dialog v-model="eventDialog" title="转为日程" width="460px">
      <el-form label-width="80px">
        <el-form-item label="开始时间">
          <el-date-picker v-model="eventStart" type="datetime" style="width:100%" />
        </el-form-item>
        <el-form-item label="结束时间">
          <el-date-picker v-model="eventEnd" type="datetime" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="eventDialog = false">取消</el-button>
        <el-button type="primary" @click="convert('event')">创建日程</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Collection, Plus, Refresh } from '@element-plus/icons-vue'
import client from '@/api/client'
import { formatBackendDate } from '@/utils/date'

const items = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)
const dialog = ref(false)
const drawer = ref(false)
const active = ref<any>(null)
const mode = ref('link')
const eventDialog = ref(false)
const eventStart = ref<Date | null>(null)
const eventEnd = ref<Date | null>(null)
let timer: number | undefined

const form = reactive({ url: '', text: '', title: '' })
const file = ref<File | null>(null)

const count = (status: string) => items.value.filter((x) => x.status === status).length
const fmt = (v: string | null) => (v ? formatBackendDate(v) : '—')
const kindText = (kind: string) => ({ link: '链接', article: '文章', image: '图片', text: '文本', file: '文件' } as any)[kind] || kind
const statusText = (status: string) => ({ inbox: '待处理', processing: '分析中', ready: '已分析', converted: '已转换', failed: '失败' } as any)[status] || status
const statusType = (status: string) => status === 'failed' ? 'danger' : status === 'ready' ? 'success' : status === 'processing' ? 'warning' : 'info'

async function load() {
  loading.value = true
  try {
    const res = await client.get('/captures')
    items.value = res.data?.items || []
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

function onFile(e: Event) {
  const input = e.target as HTMLInputElement
  file.value = input.files?.[0] || null
}

async function save() {
  saving.value = true
  try {
    if (mode.value === 'file') {
      if (!file.value) return ElMessage.warning('请选择文件')
      const data = new FormData()
      data.append('file', file.value)
      data.append('text', form.text)
      data.append('title', form.title)
      await client.post('/captures/upload', data, { headers: { 'Content-Type': 'multipart/form-data' } })
    } else if (mode.value === 'text') {
      await client.post('/captures', { kind: 'text', source: 'web', text: form.text, title: form.title })
    } else {
      await client.post('/captures', { kind: 'link', source: 'web', url: form.url, text: form.text, title: form.title })
    }
    dialog.value = false
    form.url = ''
    form.text = ''
    form.title = ''
    file.value = null
    await load()
    ElMessage.success('已收进随手记，正在分析')
    startPolling()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

function open(item: any) {
  active.value = item
  drawer.value = true
}

async function convert(target: string) {
  if (!active.value) return
  const params: any = {}
  if (target === 'event') {
    if (!eventStart.value) return ElMessage.warning('请选择开始时间')
    params.start_time = eventStart.value.toISOString()
    params.end_time = eventEnd.value?.toISOString()
  }
  try {
    await client.post(`/captures/${active.value.id}/convert`, { target, params })
    eventDialog.value = false
    drawer.value = false
    await load()
    ElMessage.success('已转换')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '转换失败')
  }
}

function openEventConvert() {
  eventStart.value = new Date()
  eventEnd.value = null
  eventDialog.value = true
}

async function reanalyze() {
  if (!active.value) return
  await client.post(`/captures/${active.value.id}/analyze`)
  ElMessage.success('已提交分析')
  startPolling()
}

async function remove() {
  if (!active.value) return
  await client.delete(`/captures/${active.value.id}`)
  drawer.value = false
  await load()
}

function startPolling() {
  if (timer) return
  timer = window.setInterval(async () => {
    await load()
    if (active.value) {
      const updated = items.value.find((x) => x.id === active.value.id)
      if (updated) active.value = updated
    }
    if (!items.value.some((x) => x.status === 'processing')) {
      window.clearInterval(timer)
      timer = undefined
    }
  }, 3000)
}

onMounted(load)
onUnmounted(() => { if (timer) window.clearInterval(timer) })
</script>

<style scoped>
.sub { color: #94a3b8; font-size: 12.5px; margin-top: 4px; }
.header-actions { display: flex; gap: 8px; }
.capture-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 14px; }
.capture-stat { background: #fff; border: 1px solid #eef0f4; border-radius: 12px; padding: 14px 16px; display: flex; flex-direction: column; gap: 4px; }
.capture-stat b { font-size: 22px; color: #111827; }
.capture-stat span { font-size: 11px; color: #94a3b8; }
.capture-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; min-height: 160px; }
.capture-card { border: 1px solid #eef0f4; border-radius: 12px; padding: 14px; cursor: pointer; background: #fff; transition: all .15s; }
.capture-card:hover { border-color: #c7d2fe; box-shadow: 0 8px 22px rgba(79, 70, 229, .08); }
.capture-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.capture-kind { font-size: 11px; color: #64748b; }
.capture-time { margin-left: auto; font-size: 10.5px; color: #94a3b8; }
.capture-title { font-size: 14px; font-weight: 700; color: #111827; line-height: 1.45; margin-bottom: 6px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.capture-summary { font-size: 12px; color: #64748b; line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.capture-tags { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 10px; }
.capture-empty { grid-column: 1 / -1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; color: #94a3b8; padding: 48px 0; }
.detail-meta { display: flex; align-items: center; gap: 10px; color: #94a3b8; font-size: 12px; }
.detail-url { margin: 12px 0; font-size: 12px; word-break: break-all; }
.detail-url a { color: #4f46e5; }
.detail-text { font-size: 13px; line-height: 1.8; color: #334155; white-space: pre-wrap; }
.detail-list { padding-left: 18px; color: #334155; font-size: 13px; line-height: 1.8; }
.detail-actions { display: flex; flex-wrap: wrap; gap: 8px; }
</style>
