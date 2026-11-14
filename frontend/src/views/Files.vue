<template>
  <div class="page-wrapper">
    <div class="page-header files-header">
      <div>
        <h2>文件管理</h2>
        <div class="muted" v-if="!trashMode">
          当前目录：{{ currentPath }} · {{ store.total }} 项
          <span v-if="store.stats"> · 已用 {{ store.formatSize(store.stats.active_size) }}</span>
        </div>
        <div class="muted" v-else>
          回收站 · {{ store.total }} 项
          <span v-if="store.stats"> · {{ store.formatSize(store.stats.trash_size) }}</span>
        </div>
      </div>
      <div class="header-actions">
        <el-input
          v-model="searchText"
          placeholder="搜索文件名..."
          clearable
          style="width:200px"
          :prefix-icon="Search"
          @input="onSearchInput"
          @keyup.enter="doSearch"
        />
        <el-select v-model="store.sortBy" style="width:120px" @change="applySort">
          <el-option label="修改时间" value="updated_at" />
          <el-option label="名称" value="name" />
          <el-option label="大小" value="size" />
          <el-option label="创建时间" value="created_at" />
        </el-select>
        <el-button :icon="Sort" @click="toggleSortOrder">{{ store.sortOrder === 'asc' ? '升序' : '降序' }}</el-button>
        <el-button v-if="!trashMode" :icon="FolderAdd" @click="createFolder">新建文件夹</el-button>
        <el-upload
          v-if="!trashMode"
          :http-request="handleUpload"
          :show-file-list="false"
          :multiple="true"
        >
          <el-button type="primary" :icon="Upload">上传文件</el-button>
        </el-upload>
        <el-button :type="trashMode ? 'warning' : 'default'" :icon="Delete" @click="toggleTrash">
          {{ trashMode ? '返回文件' : '回收站' }}
        </el-button>
        <el-button v-if="trashMode" type="danger" plain :icon="DeleteFilled" @click="emptyTrash">清空回收站</el-button>
        <el-button-group>
          <el-button :type="viewMode === 'grid' ? 'primary' : 'default'" :icon="Grid" @click="viewMode = 'grid'" />
          <el-button :type="viewMode === 'list' ? 'primary' : 'default'" :icon="List" @click="viewMode = 'list'" />
        </el-button-group>
      </div>
    </div>

    <div v-if="uploads.length" class="upload-queue">
      <div v-for="item in uploads" :key="item.id" class="upload-row">
        <span class="upload-name" :title="item.name">{{ item.name }}</span>
        <el-progress
          class="upload-progress"
          :percentage="item.percent"
          :status="item.status || undefined"
          :stroke-width="8"
        />
        <span class="upload-size">
          {{ store.formatSize(item.loaded || 0) }} / {{ store.formatSize(item.total || 0) }}
        </span>
        <span v-if="item.phase === 'processing'" class="upload-processing">处理中…</span>
        <el-button v-else-if="!item.status" size="small" text @click="cancelUpload(item)">取消</el-button>
      </div>
    </div>

    <div v-if="selectedIds.length" class="batch-bar">
      <span class="batch-count">已选 {{ selectedIds.length }} 项</span>
      <el-button size="small" @click="clearSelection">取消选择</el-button>
      <template v-if="trashMode">
        <el-button size="small" type="primary" plain :icon="RefreshLeft" @click="batchRestore">还原</el-button>
        <el-button size="small" type="danger" plain :icon="Delete" @click="batchPermanent">彻底删除</el-button>
      </template>
      <template v-else>
        <el-button size="small" :icon="Rank" @click="openBatchMove">移动</el-button>
        <el-button size="small" type="danger" plain :icon="Delete" @click="batchDelete">移入回收站</el-button>
      </template>
    </div>

    <div v-if="!trashMode && !searchText.trim()" class="crumb-bar">
      <el-breadcrumb separator="/">
        <el-breadcrumb-item>
          <a href="#" @click.prevent="navigateTo('/')">全部文件</a>
        </el-breadcrumb-item>
        <el-breadcrumb-item v-for="(seg, i) in pathSegments" :key="i">
          <a href="#" @click.prevent="navigateTo(segmentPath(i))">{{ seg }}</a>
        </el-breadcrumb-item>
      </el-breadcrumb>
    </div>

    <div v-if="store.loading" class="loading-box">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
    </div>

    <template v-else-if="viewMode === 'grid'">
      <el-row :gutter="12">
        <el-col v-for="file in store.files" :key="file.id" :span="6" :xs="12" :sm="8" :md="6" :lg="4">
          <el-card shadow="hover" class="file-card" @click="openItem(file)">
            <div class="file-check" @click.stop>
              <el-checkbox
                :model-value="selectedIds.includes(file.id)"
                @change="toggleSelect(file.id)"
              />
            </div>
            <div class="file-card-body">
              <el-icon :size="48" class="file-icon" :class="{ folder: file.is_folder }">
                <component :is="getIconComponent(file)" />
              </el-icon>
              <div class="file-name" :title="file.original_name">{{ file.original_name }}</div>
              <div class="file-meta">
                {{ file.is_folder ? '文件夹' : store.formatSize(file.size) }}
              </div>
            </div>
            <div class="card-actions" @click.stop>
              <el-button
                v-if="!file.is_folder && !trashMode"
                :icon="file.is_favorite ? StarFilled : Star"
                :type="file.is_favorite ? 'warning' : 'default'"
                text
                size="small"
                @click="store.toggleFavorite(file.id)"
              />
              <el-dropdown trigger="click" @command="(cmd: string) => handleCommand(cmd, file)">
                <el-button text size="small" :icon="MoreFilled" />
                <template #dropdown>
                  <el-dropdown-menu>
                    <template v-if="trashMode">
                      <el-dropdown-item command="restore" :icon="RefreshLeft">还原</el-dropdown-item>
                      <el-dropdown-item command="permanent" :icon="Delete" divided>彻底删除</el-dropdown-item>
                    </template>
                    <template v-else>
                      <el-dropdown-item command="share" :icon="Share" v-if="!file.is_folder">分享链接</el-dropdown-item>
                      <el-dropdown-item command="rename" :icon="Edit">重命名</el-dropdown-item>
                      <el-dropdown-item command="move" :icon="Rank">移动</el-dropdown-item>
                      <el-dropdown-item command="kb" :icon="Reading" v-if="canImportKb(file)">加入知识库</el-dropdown-item>
                      <el-dropdown-item command="download" :icon="Download" v-if="!file.is_folder">下载</el-dropdown-item>
                      <el-dropdown-item command="delete" :icon="Delete" divided>移到回收站</el-dropdown-item>
                    </template>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </el-card>
        </el-col>
      </el-row>
      <el-empty v-if="!store.files.length" :description="trashMode ? '回收站为空' : '这个目录还是空的'" :image-size="70" />
    </template>

    <el-table
      v-else
      ref="tableRef"
      :data="store.files"
      row-key="id"
      stripe
      style="width:100%"
      @row-click="openItem"
      @selection-change="onTableSelection"
    >
      <el-table-column type="selection" width="42" />
      <el-table-column prop="original_name" label="名称" min-width="240">
        <template #default="{ row }">
          <div class="name-cell">
            <el-icon :class="{ folder: row.is_folder }"><component :is="getIconComponent(row)" /></el-icon>
            <span>{{ row.original_name }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="大小" width="110">
        <template #default="{ row }">{{ row.is_folder ? '—' : store.formatSize(row.size) }}</template>
      </el-table-column>
      <el-table-column prop="mime_type" label="类型" width="150" show-overflow-tooltip />
      <el-table-column label="修改时间" width="170">
        <template #default="{ row }">{{ fmtTime(row.updated_at || row.created_at) }}</template>
      </el-table-column>
      <el-table-column width="150" fixed="right">
        <template #default="{ row }">
          <div @click.stop>
            <el-button
              v-if="!row.is_folder && !trashMode"
              :icon="row.is_favorite ? StarFilled : Star"
              :type="row.is_favorite ? 'warning' : 'default'"
              text
              @click="store.toggleFavorite(row.id)"
            />
            <el-button
              v-if="!row.is_folder"
              :icon="View"
              text
              title="预览"
              @click="previewFile(row)"
            />
            <el-dropdown trigger="click" @command="(cmd: string) => handleCommand(cmd, row)">
              <el-button text :icon="MoreFilled" />
              <template #dropdown>
                <el-dropdown-menu>
                  <template v-if="trashMode">
                    <el-dropdown-item command="restore" :icon="RefreshLeft">还原</el-dropdown-item>
                    <el-dropdown-item command="permanent" :icon="Delete" divided>彻底删除</el-dropdown-item>
                  </template>
                  <template v-else>
                    <el-dropdown-item command="share" :icon="Share" v-if="!row.is_folder">分享链接</el-dropdown-item>
                    <el-dropdown-item command="rename" :icon="Edit">重命名</el-dropdown-item>
                    <el-dropdown-item command="move" :icon="Rank">移动</el-dropdown-item>
                    <el-dropdown-item command="kb" :icon="Reading" v-if="canImportKb(row)">加入知识库</el-dropdown-item>
                    <el-dropdown-item command="download" :icon="Download" v-if="!row.is_folder">下载</el-dropdown-item>
                    <el-dropdown-item command="delete" :icon="Delete" divided>移到回收站</el-dropdown-item>
                  </template>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager" v-if="store.total > store.pageSize">
      <el-pagination
        v-model:current-page="store.page"
        :page-size="store.pageSize"
        :total="store.total"
        layout="prev, pager, next"
        @current-change="loadFiles"
      />
    </div>

    <el-dialog v-model="moveVisible" title="移动到" width="540px">
      <div class="move-picker">
        <div class="move-path">
          <el-button v-if="movePath !== '/'" link @click="moveUp">上一级</el-button>
          <code>{{ movePath }}</code>
        </div>
        <el-scrollbar height="320px">
          <div v-if="moveLoading" class="move-empty">加载中…</div>
          <div v-else-if="moveFolders.length === 0" class="move-empty">没有子文件夹</div>
          <div
            v-for="folder in moveFolders"
            :key="folder.id"
            class="move-folder"
            @click="enterMoveFolder(folder)"
          >
            <el-icon><Folder /></el-icon>
            <span>{{ folder.original_name }}</span>
          </div>
        </el-scrollbar>
      </div>
      <template #footer>
        <el-button @click="moveVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmMove">移动到这里</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="previewVisible" :title="previewFileItem?.original_name" width="60%">
      <div v-if="previewFileItem">
        <p class="muted">
          {{ previewFileItem.mime_type }} · {{ store.formatSize(previewFileItem.size) }} ·
          {{ fmtTime(previewFileItem.updated_at || previewFileItem.created_at) }}
        </p>
        <div v-if="isImage" class="preview-center">
          <img :src="previewSrc" style="max-width:100%; max-height:500px" />
        </div>
        <div v-else-if="isAudio" class="preview-center">
          <audio controls autoplay style="width:100%" :src="previewSrc"></audio>
        </div>
        <div v-else-if="isVideo" class="preview-center">
          <video controls autoplay style="max-width:100%; max-height:500px" :src="previewSrc"></video>
        </div>
        <iframe v-else-if="isPdf" :src="previewSrc" style="width:100%; height:70vh; border:0"></iframe>
        <div v-else-if="textLoading" class="preview-center muted">正在加载预览…</div>
        <div v-else-if="isMarkdown" class="markdown-preview" v-html="renderedText"></div>
        <pre v-else-if="isText" class="text-preview">{{ textContent }}</pre>
        <div v-else class="preview-center muted">该类型暂不支持在线预览，可下载后查看。</div>
        <div v-if="textError" class="preview-center muted">{{ textError }}</div>
        <div class="preview-actions">
          <el-button type="primary" :icon="Download" @click="downloadFile(previewFileItem)">下载</el-button>
          <el-button plain @click="askAssistant(previewFileItem)">让助手处理</el-button>
        </div>
        <div class="file-comments">
          <ObjectComments type="file" :object-id="previewFileItem.id" :title="previewFileItem.original_name" />
        </div>
      </div>
    </el-dialog>

    <el-dialog v-model="shareVisible" title="分享文件" width="520px">
      <div v-if="shareFile" class="share-dialog">
        <p class="muted">{{ shareFile.original_name }} · {{ store.formatSize(shareFile.size) }}</p>
        <div class="share-expiry">
          <el-radio-group v-model="shareExpiry" @change="generateShare">
            <el-radio-button :label="1">1 小时</el-radio-button>
            <el-radio-button :label="24">24 小时</el-radio-button>
            <el-radio-button :label="168">7 天</el-radio-button>
            <el-radio-button :label="720">30 天</el-radio-button>
          </el-radio-group>
        </div>
        <div v-if="shareLoading" class="muted" style="padding:12px 0">正在生成链接…</div>
        <el-input v-else v-model="shareUrl" readonly placeholder="生成失败">
          <template #append>
            <el-button @click="copyShare" :disabled="!shareUrl">复制</el-button>
          </template>
        </el-input>
        <p v-if="shareError" class="share-error">{{ shareError }}</p>
        <p class="muted" style="margin-top:10px">
          任何拿到链接的人都能访问该文件，链接将在 {{ shareExpiryLabel }}后失效。
        </p>
      </div>
      <template #footer>
        <el-button :disabled="!shareUrl" @click="openShareInBrowser">浏览器打开</el-button>
        <el-button @click="generateShare">重新生成</el-button>
        <el-button type="primary" @click="shareVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import { useFileStore, type FileItem } from '@/stores/core/file'
import { apiUrl } from '@/api/base'
import client from '@/api/client'
import { formatBackendDate } from '@/utils/date'
import ObjectComments from '@/components/ObjectComments.vue'
import {
  Delete, DeleteFilled, Document, Download, Edit, Folder, FolderAdd, Grid, Headset, List, Loading,
  MoreFilled, Picture, Rank, Reading, RefreshLeft, Search, Share, Sort, Star, StarFilled, Upload, VideoCamera, View,
} from '@element-plus/icons-vue'

const store = useFileStore()
const route = useRoute()
const router = useRouter()
const viewMode = ref<'grid' | 'list'>('grid')
const previewVisible = ref(false)
const previewFileItem = ref<FileItem | null>(null)
const previewSrc = ref('')
const searchText = ref('')
const currentPath = ref('/')
const trashMode = ref(false)
const moveVisible = ref(false)
const moveTarget = ref<FileItem | null>(null)
const movePath = ref('/')
const moveFolders = ref<FileItem[]>([])
const moveLoading = ref(false)
interface UploadTask {
  id: number
  name: string
  percent: number
  loaded: number
  total: number
  status: '' | 'success' | 'exception'
  phase: 'uploading' | 'processing'
  xhr?: XMLHttpRequest
}
const uploads = ref<UploadTask[]>([])
let uploadSeq = 0
let searchTimer: any = null

const selectedIds = ref<number[]>([])
const tableRef = ref<any>(null)
const batchMoveIds = ref<number[]>([])

const shareVisible = ref(false)
const shareFile = ref<FileItem | null>(null)
const shareExpiry = ref(24 * 7)
const shareUrl = ref('')
const shareLoading = ref(false)
const shareError = ref('')
const shareExpiryLabel = computed(() => ({ 1: '1 小时', 24: '24 小时', 168: '7 天', 720: '30 天' } as Record<number, string>)[shareExpiry.value] || '')

function fmtTime(value?: string | null) {
  return value ? formatBackendDate(value) : '—'
}

const pathSegments = computed(() => currentPath.value.split('/').filter(Boolean))
const previewMime = computed(() => previewFileItem.value?.mime_type || '')
const previewName = computed(() => previewFileItem.value?.original_name || '')
const previewExt = computed(() => (previewName.value.split('.').pop() || '').toLowerCase())
const imageExts = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg', 'avif', 'ico', 'tif', 'tiff'])
const audioExts = new Set(['mp3', 'wav', 'm4a', 'aac', 'flac', 'ogg', 'opus', 'weba', 'wma'])
const videoExts = new Set(['mp4', 'webm', 'mov', 'm4v', 'ogv', 'avi', 'mkv', 'wmv'])
const isImage = computed(() => previewMime.value.startsWith('image/') || imageExts.has(previewExt.value))
const isAudio = computed(() => previewMime.value.startsWith('audio/') || audioExts.has(previewExt.value))
const isVideo = computed(() => previewMime.value.startsWith('video/') || videoExts.has(previewExt.value))
const isPdf = computed(() => previewMime.value.includes('pdf') || previewExt.value === 'pdf')
const isMarkdown = computed(() => isTextFile(previewFileItem.value) && /\.(md|markdown)$/i.test(previewName.value))
const isText = computed(() => isTextFile(previewFileItem.value))
const textContent = ref('')
const textLoading = ref(false)
const textError = ref('')
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
const renderedText = computed(() => DOMPurify.sanitize(md.render(textContent.value || '')))

function isTextFile(file: FileItem | null): boolean {
  if (!file || file.is_folder) return false
  const mime = (file.mime_type || '').toLowerCase()
  if (mime.startsWith('text/')) return true
  if (/\.(md|markdown|txt|log|csv|tsv|json|jsonl|xml|yaml|yml|ini|conf|toml|sql|py|js|ts|tsx|jsx|vue|java|go|rs|c|cpp|h|hpp|css|scss|sh|bat|ps1|html|htm)$/i.test(file.original_name)) {
    return true
  }
  return false
}

const iconMap: Record<string, any> = {
  Document, Picture, VideoCamera, Headset, Reading, Folder,
}

function getIconComponent(file: FileItem) {
  if (file.is_folder) return Folder
  return iconMap[store.getFileIcon(file.mime_type)] || Document
}

function canImportKb(file: FileItem) {
  if (file.is_folder) return false
  const mime = (file.mime_type || '').toLowerCase()
  if (mime.startsWith('audio/') || mime.startsWith('video/') || mime.startsWith('text/')) return true
  if (mime.includes('pdf') || mime.includes('word') || mime.includes('wordprocessingml')
    || mime.includes('spreadsheetml') || mime.includes('presentationml')) return true
  return /\.(pdf|docx|xlsx|xlsm|pptx|txt|md|markdown|html|htm|mp3|wav|m4a|aac|flac|ogg|opus|webm|mp4)$/i.test(file.original_name)
}

function segmentPath(index: number) {
  return '/' + pathSegments.value.slice(0, index + 1).join('/')
}

function normalizePath(path: string) {
  if (!path.startsWith('/')) path = '/' + path
  path = path.replace(/\/+/g, '/').replace(/\/$/, '')
  return path || '/'
}

function openItem(file: FileItem) {
  if (file.is_folder) {
    const base = file.folder_path || currentPath.value
    navigateTo(normalizePath(`${base}/${file.original_name}`))
  } else {
    previewFile(file)
  }
}

function navigateTo(path: string) {
  currentPath.value = normalizePath(path)
  searchText.value = ''
  store.search = ''
  store.page = 1
  loadFiles()
}

function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(doSearch, 350)
}

function doSearch() {
  store.page = 1
  loadFiles()
}

async function loadFiles() {
  const q = searchText.value.trim()
  store.search = q
  const folder = q || trashMode.value ? undefined : currentPath.value
  await store.fetchFiles({
    status: trashMode.value ? 'trash' : 'active',
    page: store.page,
    search: q || undefined,
    folder_path: folder,
  })
  clearSelection()
  await store.fetchStats().catch(() => {})
}

function applySort() {
  store.page = 1
  loadFiles()
}

function toggleSortOrder() {
  store.sortOrder = store.sortOrder === 'asc' ? 'desc' : 'asc'
  applySort()
}

function onTableSelection(rows: FileItem[]) {
  selectedIds.value = rows.map(row => row.id)
}

function toggleSelect(id: number) {
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) selectedIds.value.splice(idx, 1)
  else selectedIds.value.push(id)
}

function clearSelection() {
  selectedIds.value = []
  tableRef.value?.clearSelection?.()
}

async function batchDelete() {
  if (!selectedIds.value.length) return
  try {
    await ElMessageBox.confirm(`把选中的 ${selectedIds.value.length} 项移到回收站？`, '批量删除', { type: 'warning' })
  } catch { return }
  try {
    const res = await store.batchTrash(selectedIds.value)
    ElMessage.success(`已移入回收站 ${res.success} 项${res.failed.length ? `，${res.failed.length} 项失败` : ''}`)
    await loadFiles()
  } catch (err: any) { showError(err, '批量删除失败') }
}

async function batchRestore() {
  if (!selectedIds.value.length) return
  try {
    const res = await store.batchRestore(selectedIds.value)
    ElMessage.success(`已还原 ${res.success} 项${res.failed.length ? `，${res.failed.length} 项失败` : ''}`)
    await loadFiles()
  } catch (err: any) { showError(err, '批量还原失败') }
}

async function batchPermanent() {
  if (!selectedIds.value.length) return
  try {
    await ElMessageBox.confirm(`彻底删除选中的 ${selectedIds.value.length} 项？此操作不可恢复。`, '彻底删除', { type: 'error' })
  } catch { return }
  try {
    const res = await store.batchPermanent(selectedIds.value)
    ElMessage.success(`已彻底删除 ${res.success} 项${res.failed.length ? `，${res.failed.length} 项失败` : ''}`)
    await loadFiles()
  } catch (err: any) { showError(err, '批量删除失败') }
}

async function emptyTrash() {
  try {
    await ElMessageBox.confirm('清空回收站？所有项目将被彻底删除，不可恢复。', '清空回收站', { type: 'error' })
  } catch { return }
  try {
    const res = await store.emptyTrash()
    ElMessage.success(`已清空回收站（${res.removed} 项）`)
    await loadFiles()
  } catch (err: any) { showError(err, '清空回收站失败') }
}

async function openShare(file: FileItem) {
  shareFile.value = file
  shareExpiry.value = 24 * 7
  shareVisible.value = true
  await generateShare()
}

async function generateShare() {
  if (!shareFile.value) return
  shareLoading.value = true
  shareError.value = ''
  shareUrl.value = ''
  try {
    const res = await client.post(`/files/${shareFile.value.id}/share?expires_hours=${shareExpiry.value}`)
    shareUrl.value = res.data?.url || ''
    if (!shareUrl.value) shareError.value = '生成失败：文件服务可能未配置'
  } catch (e: any) {
    shareError.value = e?.response?.data?.detail || e?.message || '生成分享链接失败'
  } finally {
    shareLoading.value = false
  }
}

async function copyShare() {
  if (!shareUrl.value) return
  try {
    await navigator.clipboard.writeText(shareUrl.value)
    ElMessage.success('链接已复制')
  } catch {
    ElMessage.error('复制失败，请手动选择链接')
  }
}

function openShareInBrowser() {
  if (shareUrl.value) window.open(shareUrl.value, '_blank')
}

async function toggleTrash() {
  trashMode.value = !trashMode.value
  if (trashMode.value) {
    currentPath.value = '/'
    searchText.value = ''
  }
  store.page = 1
  clearSelection()
  await loadFiles()
}

function isCancel(err: any) {
  return err === 'cancel' || err === 'close'
}

function showError(err: any, fallback: string) {
  if (isCancel(err)) return
  ElMessage.error(err?.response?.data?.detail || err?.message || fallback)
}

async function createFolder() {
  try {
    const { value } = await ElMessageBox.prompt('文件夹名称', '新建文件夹', { inputPattern: /\S+/, inputErrorMessage: '名称不能为空' })
    await store.createFolder(value.trim(), currentPath.value)
    ElMessage.success('文件夹已创建')
    await loadFiles()
  } catch (err: any) { showError(err, '创建文件夹失败') }
}

async function handleUpload(options: any) {
  const { file, onProgress, onSuccess, onError } = options
  const task: UploadTask = {
    id: ++uploadSeq,
    name: file.name,
    percent: 0,
    loaded: 0,
    total: file.size || 0,
    status: '',
    phase: 'uploading',
  }
  uploads.value.push(task)
  const update = (patch: Partial<UploadTask>) => {
    const target = uploads.value.find(item => item.id === task.id)
    if (target) Object.assign(target, patch)
  }
  const clearSoon = (delay: number) => {
    setTimeout(() => {
      uploads.value = uploads.value.filter(item => item.id !== task.id)
    }, delay)
  }
  const track = (xhr: XMLHttpRequest) => {
    task.xhr = xhr
    xhr.upload.onprogress = (e) => {
      if (!e.total) return
      const percent = Math.round((e.loaded / e.total) * 100)
      update({ percent, loaded: e.loaded, total: e.total, phase: percent >= 100 ? 'processing' : 'uploading' })
      onProgress?.({ percent })
    }
  }
  const uploadDirect = () => new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    track(xhr)
    const form = new FormData()
    form.append('file', file)
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve()
      else reject(new Error(`上传失败: ${xhr.status} ${String(xhr.responseText || '').slice(0, 120)}`))
    }
    xhr.onerror = () => reject(new Error('上传失败：网络错误'))
    xhr.onabort = () => reject(new Error('已取消上传'))
    xhr.open('POST', apiUrl(`/files/upload/direct?folder_path=${encodeURIComponent(currentPath.value)}`))
    xhr.setRequestHeader('Authorization', `Bearer ${localStorage.getItem('token') || ''}`)
    xhr.send(form)
  })

  try {
    // Prefer the presigned PUT (faster), but fall back to the backend proxy
    // when MinIO is not publicly reachable — which is the default here.
    let uploadUrl = ''
    let fileId = 0
    try {
      const info = await store.getUploadUrl(file.name, currentPath.value)
      uploadUrl = info.upload_url || ''
      fileId = info.file_id
    } catch { /* fall back to direct upload */ }

    if (uploadUrl) {
      const xhr = new XMLHttpRequest()
      track(xhr)
      await new Promise<void>((resolve, reject) => {
        xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`上传失败: ${xhr.status}`)))
        xhr.onerror = () => reject(new Error('上传失败'))
        xhr.onabort = () => reject(new Error('已取消上传'))
        xhr.open('PUT', uploadUrl)
        xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream')
        xhr.send(file)
      })
      update({ percent: 100 })
      await store.confirmUpload(fileId)
    } else {
      await uploadDirect()
    }

    update({ percent: 100, loaded: task.total, status: 'success' })
    ElMessage.success(`已上传 ${file.name}`)
    await loadFiles()
    clearSoon(2500)
    onSuccess?.()
  } catch (err: any) {
    update({ status: 'exception' })
    if (task.xhr) task.xhr = undefined
    const message = err?.message || '上传失败'
    if (message.includes('已取消')) {
      ElMessage.info(`已取消 ${file.name}`)
      clearSoon(1200)
    } else {
      ElMessage.error(message)
      clearSoon(5000)
    }
    onError?.(err)
  }
}

function cancelUpload(task: UploadTask) {
  try { task.xhr?.abort() } catch { /* ignore */ }
  uploads.value = uploads.value.filter(item => item.id !== task.id)
}

function normalizeFolder(path: string | null | undefined): string {
  const parts = (path || '/').split('/').filter(Boolean)
  return '/' + parts.join('/')
}

function joinFolder(parent: string, name: string): string {
  const base = normalizeFolder(parent)
  return base === '/' ? `/${name}` : `${base}/${name}`
}

async function loadMoveFolders(path: string) {
  moveLoading.value = true
  try {
    const res = await client.get('/files', {
      params: {
        page_size: 200,
        status: 'active',
        folder_path: normalizeFolder(path),
        is_folder: true,
      },
    })
    moveFolders.value = res.data.files || []
  } catch (err: any) {
    showError(err, '加载文件夹失败')
    moveFolders.value = []
  } finally {
    moveLoading.value = false
  }
}

async function openMove(file: FileItem) {
  batchMoveIds.value = []
  moveTarget.value = file
  movePath.value = normalizeFolder(file.is_folder ? (file.folder_path || '/') : currentPath.value)
  moveVisible.value = true
  await loadMoveFolders(movePath.value)
}

async function openBatchMove() {
  if (!selectedIds.value.length) return
  batchMoveIds.value = [...selectedIds.value]
  moveTarget.value = null
  movePath.value = normalizeFolder(currentPath.value)
  moveVisible.value = true
  await loadMoveFolders(movePath.value)
}

async function enterMoveFolder(folder: FileItem) {
  movePath.value = joinFolder(movePath.value, folder.original_name)
  await loadMoveFolders(movePath.value)
}

async function moveUp() {
  if (movePath.value === '/') return
  const parts = movePath.value.split('/').filter(Boolean)
  parts.pop()
  movePath.value = '/' + parts.join('/')
  await loadMoveFolders(movePath.value)
}

async function confirmMove() {
  const target = normalizeFolder(movePath.value)
  const targetPath = target === '/' ? '/' : `${target}/`

  if (batchMoveIds.value.length) {
    try {
      const res = await store.batchMove(batchMoveIds.value, targetPath)
      ElMessage.success(`已移动 ${res.success} 项${res.failed.length ? `，${res.failed.length} 项失败` : ''}`)
      batchMoveIds.value = []
      moveVisible.value = false
      await loadFiles()
    } catch (err: any) {
      showError(err, '移动失败')
    }
    return
  }

  const file = moveTarget.value
  if (!file) return
  if (target === normalizeFolder(file.folder_path)) {
    moveVisible.value = false
    return
  }
  if (file.is_folder) {
    const source = joinFolder(file.folder_path || '/', file.original_name)
    if (target === source || target.startsWith(`${source}/`)) {
      ElMessage.warning('不能移动到自身或子目录')
      return
    }
  }
  try {
    await store.moveFile(file.id, targetPath)
    ElMessage.success('已移动')
    moveVisible.value = false
    await loadFiles()
  } catch (err: any) {
    showError(err, '移动失败')
  }
}

async function handleCommand(cmd: string, file: FileItem) {
  if (cmd === 'rename') {
    try {
      const { value } = await ElMessageBox.prompt('新名称', '重命名', { inputValue: file.original_name, inputPattern: /\S+/, inputErrorMessage: '名称不能为空' })
      await store.renameFile(file.id, value.trim())
      ElMessage.success('已重命名')
      await loadFiles()
    } catch (err: any) { showError(err, '重命名失败') }
  } else if (cmd === 'move') {
    await openMove(file)
  } else if (cmd === 'delete') {
    try {
      const suffix = file.is_folder ? '及其中的所有内容' : ''
      await ElMessageBox.confirm(`确定把「${file.original_name}」${suffix}移到回收站？`, '删除', { type: 'warning' })
      await store.deleteFile(file.id)
      ElMessage.success('已移入回收站')
      await loadFiles()
    } catch (err: any) { showError(err, '删除失败') }
  } else if (cmd === 'restore') {
    try {
      await store.restoreFile(file.id)
      ElMessage.success('已还原')
      await loadFiles()
    } catch (err: any) { showError(err, '还原失败') }
  } else if (cmd === 'permanent') {
    try {
      const suffix = file.is_folder ? '及其中的所有内容' : ''
      await ElMessageBox.confirm(`彻底删除「${file.original_name}」${suffix}？此操作不可恢复。`, '彻底删除', { type: 'error' })
      await store.deletePermanent(file.id)
      ElMessage.success('已彻底删除')
      await loadFiles()
    } catch (err: any) { showError(err, '彻底删除失败') }
  } else if (cmd === 'kb') {
    try {
      const res = await client.post('/plugins/notes/import/library', { file_id: file.id }, { timeout: 180000 })
      ElMessage.success(`已加入知识库：${res.data?.title || file.original_name}`)
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || '加入知识库失败')
    }
  } else if (cmd === 'download') {
    downloadFile(file)
  } else if (cmd === 'share') {
    await openShare(file)
  }
}

function streamSrc(file: FileItem): string {
  const token = localStorage.getItem('token') || ''
  return apiUrl(`/files/${file.id}/stream?token=${encodeURIComponent(token)}`)
}

function askAssistant(file: FileItem | null) {
  if (!file?.id) return
  router.push({ path: '/chat', query: { ref: `file:${file.id}` } })
}

async function previewFile(file: FileItem) {
  previewFileItem.value = file
  previewVisible.value = true
  previewSrc.value = ''
  textContent.value = ''
  textError.value = ''
  textLoading.value = false
  if (isTextFile(file)) {
    textLoading.value = true
    try {
      const res = await client.get(`/files/${file.id}/download`, { responseType: 'blob' })
      const blob = res.data as Blob
      const sliced = blob.size > 1_000_000 ? blob.slice(0, 1_000_000) : blob
      textContent.value = await sliced.text()
      if (blob.size > 1_000_000) {
        textContent.value += '\n\n…（文件过大，仅显示前 1MB）'
      }
    } catch {
      textError.value = '文本预览加载失败，请下载查看。'
    } finally {
      textLoading.value = false
    }
    return
  }
  if (isImage.value || isPdf.value || isAudio.value || isVideo.value) {
    // The authenticated stream endpoint works for every media type and avoids
    // a second presign request (and the race when switching files quickly).
    previewSrc.value = streamSrc(file)
    return
  }
}

async function clientDownloadUrl(fileId: number): Promise<string | null> {
  const res = await client.get(`/files/${fileId}/download-url`)
  return res.data?.download_url || null
}

async function downloadFile(file: FileItem) {
  let objectUrl = ''
  try {
    let href = await clientDownloadUrl(file.id)
    if (!href) {
      // MinIO is private: download through the authenticated API as a blob.
      const res = await client.get(`/files/${file.id}/download`, { responseType: 'blob' })
      objectUrl = URL.createObjectURL(res.data)
      href = objectUrl
    }
    const a = document.createElement('a')
    a.href = href
    a.download = file.original_name
    document.body.appendChild(a)
    a.click()
    a.remove()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '下载失败')
  } finally {
    if (objectUrl) setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
  }
}

onMounted(async () => {
  await loadFiles()
  await store.fetchStats().catch(() => {})
  const id = Number(route.query.file)
  if (Number.isFinite(id) && id > 0) {
    try {
      const { data } = await client.get(`/files/${id}`)
      previewFile(data)
    } catch { /* ignore invalid deep link */ }
  }
})
</script>

<style scoped>
.files-header { display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:10px; }
.header-actions { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
.muted { color:#909399; font-size:12px; }
.crumb-bar { margin:8px 0 12px; }
.loading-box { text-align:center; padding:40px; }
.file-card { margin-bottom:12px; cursor:pointer; position:relative; }
.file-check { position:absolute; top:6px; left:8px; z-index:2; }
.batch-bar {
  display:flex; align-items:center; gap:8px; margin: 0 0 12px; padding:8px 12px;
  background:#eef4ff; border:1px solid #d6e4ff; border-radius:8px;
}
.batch-count { font-size:13px; color:#3b6fd4; margin-right:4px; }
.share-dialog .share-expiry { margin: 12px 0; }
.share-error { color:#c0392b; font-size:12px; margin-top:8px; }
.file-card-body { text-align:center; padding:16px 4px 4px; }
.file-icon.folder, .name-cell .folder { color:#e6a23c; }
.file-name { font-size:13px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.file-meta { font-size:12px; color:#909399; margin-top:4px; }
.card-actions { position:absolute; top:6px; right:6px; display:flex; gap:2px; }
.name-cell { display:flex; align-items:center; gap:8px; }
.move-picker { display: flex; flex-direction: column; gap: 8px; }
.move-path { display: flex; align-items: center; gap: 8px; padding: 6px 8px; background: var(--el-fill-color-lighter); border-radius: 6px; }
.move-path code { font-size: 12px; }
.move-folder { display: flex; align-items: center; gap: 8px; padding: 9px 10px; border-radius: 6px; cursor: pointer; }
.move-folder:hover { background: var(--el-fill-color-light); }
.move-empty { padding: 24px; text-align: center; color: var(--el-text-color-secondary); }
.pager { display:flex; justify-content:center; margin-top:16px; }
.preview-center { text-align:center; min-height:40px; }
.text-preview {
  max-height: 62vh; overflow: auto; margin: 0; padding: 14px;
  background: #0f172a; color: #e2e8f0; border-radius: 10px;
  font-size: 12.5px; line-height: 1.65; white-space: pre-wrap; word-break: break-word;
}
.markdown-preview {
  max-height: 62vh; overflow: auto; padding: 4px 6px;
  font-size: 13.5px; line-height: 1.75; color: #334155;
}
.markdown-preview :deep(h1), .markdown-preview :deep(h2), .markdown-preview :deep(h3) { color: #111827; }
.markdown-preview :deep(pre) { background: #0f172a; color: #e2e8f0; padding: 12px; border-radius: 8px; overflow: auto; }
.markdown-preview :deep(code) { background: #f1f5f9; padding: 1px 5px; border-radius: 4px; }
.markdown-preview :deep(table) { border-collapse: collapse; width: 100%; }
.markdown-preview :deep(th), .markdown-preview :deep(td) { border: 1px solid #e2e8f0; padding: 6px 8px; }
.preview-actions { text-align:center; margin-top:12px; }
.file-comments { margin-top: 18px; padding-top: 14px; border-top: 1px solid #eef1f7; }
.upload-queue {
  margin: 0 0 12px; padding: 8px 12px; border-radius: 8px;
  background: #f5f7fa; border: 1px solid #e4e7ed;
}
.upload-row { display: flex; align-items: center; gap: 12px; padding: 4px 0; }
.upload-name {
  width: 220px; max-width: 40vw; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; font-size: 13px; color: #303133;
}
.upload-progress { flex: 1; }
.upload-size { width: 110px; text-align: right; font-size: 11px; color: #909399; white-space: nowrap; }
.upload-processing { font-size: 11px; color: #409eff; white-space: nowrap; }
</style>
