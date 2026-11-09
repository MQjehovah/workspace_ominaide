<template>
  <div class="page-wrapper">
    <div class="page-header desktop-header">
      <div>
        <h2>桌面端管理</h2>
        <p>版本发布、自动更新与插件市场</p>
      </div>
      <el-button :icon="Refresh" @click="load">刷新</el-button>
    </div>

    <el-tabs v-model="tab" class="cap-tabs">
      <el-tab-pane label="版本管理" name="versions">
        <div class="platform-bar">
          <el-radio-group v-model="platform" @change="onPlatformChange">
            <el-radio-button label="mac">macOS</el-radio-button>
            <el-radio-button label="windows">Windows</el-radio-button>
          </el-radio-group>
          <span class="platform-hint">
            更新地址：<code>{{ feedUrl }}</code>
            <el-button link type="primary" @click="copyFeed">复制</el-button>
          </span>
        </div>

        <div class="release-grid">
          <div class="release-card">
            <div class="release-label">当前版本</div>
            <div class="release-value">{{ summary.version || '未发布' }}</div>
            <div class="release-sub">{{ summary.has_feed ? '更新源已就绪' : '尚未上传更新元数据' }}</div>
          </div>
          <div class="release-card">
            <div class="release-label">发布文件</div>
            <div class="release-value">{{ summary.files?.length || 0 }}</div>
            <div class="release-sub">安装包 + blockmap + yml</div>
          </div>
          <div class="release-card">
            <div class="release-label">占用空间</div>
            <div class="release-value">{{ formatSize(summary.total_size || 0) }}</div>
            <div class="release-sub">{{ platform === 'mac' ? 'DMG / ZIP' : 'EXE' }}</div>
          </div>
          <div class="release-card accent">
            <div class="release-label">状态</div>
            <div class="release-value" :class="{ ok: summary.has_feed }">{{ summary.has_feed ? '可更新' : '待发布' }}</div>
            <div class="release-sub">{{ platform === 'mac' ? 'latest-mac.yml' : 'latest.yml' }}</div>
          </div>
        </div>

        <div class="page-card" style="margin-top:14px">
          <div class="page-card-body">
            <div class="upload-row">
              <div>
                <div class="upload-title">上传发布产物</div>
                <div class="upload-sub">
                  先上传安装包和 blockmap，最后上传 {{ platform === 'mac' ? 'latest-mac.yml' : 'latest.yml' }} 生效
                </div>
              </div>
              <el-upload
                :http-request="handleUpload"
                :show-file-list="false"
                :accept="uploadAccept"
                multiple
              >
                <el-button type="primary">选择文件上传</el-button>
              </el-upload>
            </div>

            <el-table :data="summary.files || []" size="small" stripe v-loading="loading" empty-text="暂无发布文件">
              <el-table-column prop="name" label="文件名" min-width="320" show-overflow-tooltip />
              <el-table-column label="大小" width="120">
                <template #default="{ row }">{{ formatSize(row.size) }}</template>
              </el-table-column>
              <el-table-column label="更新时间" width="190">
                <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="150" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" @click="download(row)">下载</el-button>
                  <el-popconfirm title="确定删除该文件？" @confirm="remove(row)">
                    <template #reference>
                      <el-button link type="danger">删除</el-button>
                    </template>
                  </el-popconfirm>
                </template>
              </el-table-column>
            </el-table>

            <div class="publish-tip">
              <span>命令行发布：</span>
              <code>OMNIAIDE_TOKEN=&lt;admin-token&gt; npm run publish:release -- --platform {{ platform }}</code>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="插件管理" name="plugins">
        <div class="page-card">
          <div class="page-card-body">
            <DesktopPluginMarket />
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import client from '@/api/client'
import { apiUrl } from '@/api/base'
import DesktopPluginMarket from '@/components/DesktopPluginMarket.vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const tab = ref(route.query.tab === 'plugins' ? 'plugins' : 'versions')
const platform = ref<'mac' | 'windows'>('mac')
const loading = ref(false)
const summaries = ref<Record<string, any>>({})

const summary = computed(() => summaries.value[platform.value] || {
  version: null,
  has_feed: false,
  files: [],
  total_size: 0,
})

const uploadAccept = computed(() => platform.value === 'mac'
  ? '.dmg,.zip,.blockmap,.yml,.yaml'
  : '.exe,.zip,.blockmap,.yml,.yaml')

const feedUrl = computed(() => `${window.location.origin}${apiUrl(summary.value.feed_url || `/desktop/releases/${platform.value}/latest`)}`)

async function load() {
  loading.value = true
  try {
    const { data } = await client.get('/desktop/releases/platforms')
    const next: Record<string, any> = {}
    for (const item of data.platforms || []) next[item.platform] = item
    summaries.value = next
  } catch {
    ElMessage.error('加载桌面端版本失败')
  } finally {
    loading.value = false
  }
}

function onPlatformChange() {
  // summary is computed from the selected platform
}

async function handleUpload(options: any) {
  const form = new FormData()
  form.append('file', options.file)
  try {
    await client.post('/desktop/releases/upload', form, {
      params: { platform: platform.value },
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    ElMessage.success(`${options.file.name} 上传成功`)
    await load()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || `${options.file.name} 上传失败`)
  }
}

function download(row: any) {
  window.open(`${apiUrl(`/desktop/releases/${platform.value}/${row.name}`)}`, '_blank')
}

async function remove(row: any) {
  try {
    await client.delete(`/desktop/releases/${platform.value}/${encodeURIComponent(row.name)}`)
    ElMessage.success('已删除')
    await load()
  } catch {
    ElMessage.error('删除失败')
  }
}

async function copyFeed() {
  try {
    await navigator.clipboard.writeText(feedUrl.value)
    ElMessage.success('更新地址已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

function formatSize(value: number) {
  if (!value) return '0 B'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`
  return `${(value / 1024 / 1024 / 1024).toFixed(2)} GB`
}

function formatTime(value: string) {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 19)
}

onMounted(load)
</script>

<style scoped>
.desktop-header p { color: #909399; font-size: 13px; margin-top: 4px; }
.platform-bar { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 14px; }
.platform-hint { font-size: 12px; color: #909399; display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.platform-hint code { background: #f4f5f7; padding: 2px 6px; border-radius: 4px; color: #4f46e5; font-size: 11px; word-break: break-all; }
.release-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.release-card { background: #fff; border: 1px solid #ebeef5; border-radius: 12px; padding: 14px 16px; }
.release-card.accent { background: linear-gradient(135deg, #eef2ff, #f5f3ff); border-color: #ddd6fe; }
.release-label { font-size: 11px; color: #909399; }
.release-value { margin-top: 5px; font-size: 22px; font-weight: 800; color: #1f2937; font-variant-numeric: tabular-nums; }
.release-value.ok { color: #4338ca; }
.release-sub { margin-top: 3px; font-size: 11px; color: #a0a6b3; }
.upload-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 14px; flex-wrap: wrap; }
.upload-title { font-size: 14px; font-weight: 600; color: #303133; }
.upload-sub { margin-top: 3px; font-size: 11px; color: #909399; }
.publish-tip { margin-top: 12px; font-size: 11px; color: #909399; background: #f8f9fb; border-radius: 8px; padding: 8px 10px; }
.publish-tip code { color: #4f46e5; }
@media (max-width: 900px) {
  .release-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
