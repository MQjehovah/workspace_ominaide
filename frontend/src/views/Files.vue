<template>
  <div class="page-wrapper">
    <div class="page-header files-header">
      <div>
        <h2>文件管理</h2>
        <div class="muted" v-if="!trashMode">
          当前目录：{{ currentPath }} · {{ store.total }} 项
        </div>
        <div class="muted" v-else>回收站 · {{ store.total }} 项</div>
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
        <el-button-group>
          <el-button :type="viewMode === 'grid' ? 'primary' : 'default'" :icon="Grid" @click="viewMode = 'grid'" />
          <el-button :type="viewMode === 'list' ? 'primary' : 'default'" :icon="List" @click="viewMode = 'list'" />
        </el-button-group>
      </div>
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

    <el-table v-else :data="store.files" stripe style="width:100%" @row-click="openItem">
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
            <el-dropdown trigger="click" @command="(cmd: string) => handleCommand(cmd, row)">
              <el-button text :icon="MoreFilled" />
              <template #dropdown>
                <el-dropdown-menu>
                  <template v-if="trashMode">
                    <el-dropdown-item command="restore" :icon="RefreshLeft">还原</el-dropdown-item>
                    <el-dropdown-item command="permanent" :icon="Delete" divided>彻底删除</el-dropdown-item>
                  </template>
                  <template v-else>
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
        <div v-else class="preview-center muted">该类型暂不支持在线预览</div>
        <div class="preview-actions">
          <el-button type="primary" :icon="Download" @click="downloadFile(previewFileItem)">下载</el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useFileStore, type FileItem } from '@/stores/core/file'
import { apiUrl } from '@/api/base'
import client from '@/api/client'
import { formatBackendDate } from '@/utils/date'
import {
  Delete, Document, Download, Edit, Folder, FolderAdd, Grid, Headset, List, Loading,
  MoreFilled, Picture, Rank, Reading, RefreshLeft, Search, Star, StarFilled, Upload, VideoCamera,
} from '@element-plus/icons-vue'

const store = useFileStore()
const viewMode = ref<'grid' | 'list'>('grid')
const previewVisible = ref(false)
const previewFileItem = ref<FileItem | null>(null)
const previewSrc = ref('')
const searchText = ref('')
const currentPath = ref('/')
const trashMode = ref(false)
let searchTimer: any = null

function fmtTime(value?: string | null) {
  return value ? formatBackendDate(value) : '—'
}

const pathSegments = computed(() => currentPath.value.split('/').filter(Boolean))
const previewMime = computed(() => previewFileItem.value?.mime_type || '')
const isImage = computed(() => previewMime.value.startsWith('image/'))
const isAudio = computed(() => previewMime.value.startsWith('audio/'))
const isVideo = computed(() => previewMime.value.startsWith('video/'))
const isPdf = computed(() => previewMime.value.includes('pdf'))

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
}

async function toggleTrash() {
  trashMode.value = !trashMode.value
  if (trashMode.value) {
    currentPath.value = '/'
    searchText.value = ''
  }
  store.page = 1
  await loadFiles()
}

async function createFolder() {
  try {
    const { value } = await ElMessageBox.prompt('文件夹名称', '新建文件夹', { inputPattern: /\S+/, inputErrorMessage: '名称不能为空' })
    await store.createFolder(value.trim(), currentPath.value)
    ElMessage.success('文件夹已创建')
    await loadFiles()
  } catch { /* cancelled */ }
}

async function handleUpload(options: any) {
  const { file, onProgress, onSuccess, onError } = options
  try {
    const { upload_url, file_id } = await store.getUploadUrl(file.name, currentPath.value)
    const xhr = new XMLHttpRequest()
    xhr.upload.onprogress = (e) => {
      if (e.total) onProgress({ percent: Math.round((e.loaded / e.total) * 100) })
    }
    await new Promise<void>((resolve, reject) => {
      xhr.onload = () => xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`上传失败: ${xhr.status}`))
      xhr.onerror = () => reject(new Error('上传失败'))
      xhr.open('PUT', upload_url)
      xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream')
      xhr.send(file)
    })
    await store.confirmUpload(file_id)
    ElMessage.success(`已上传 ${file.name}`)
    await loadFiles()
    onSuccess?.()
  } catch (err: any) {
    ElMessage.error(err?.message || '上传失败')
    onError?.(err)
  }
}

async function handleCommand(cmd: string, file: FileItem) {
  if (cmd === 'rename') {
    try {
      const { value } = await ElMessageBox.prompt('新名称', '重命名', { inputValue: file.original_name, inputPattern: /\S+/, inputErrorMessage: '名称不能为空' })
      await store.renameFile(file.id, value.trim())
      ElMessage.success('已重命名')
      await loadFiles()
    } catch { /* cancelled */ }
  } else if (cmd === 'move') {
    try {
      const target = file.is_folder
        ? (file.folder_path || '/')
        : currentPath.value
      const { value } = await ElMessageBox.prompt('目标文件夹路径，例如 /项目/2026', '移动到', { inputValue: target })
      await store.moveFile(file.id, value.trim())
      ElMessage.success('已移动')
      await loadFiles()
    } catch { /* cancelled */ }
  } else if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm(`确定把「${file.original_name}」移到回收站？`, '删除', { type: 'warning' })
      await store.deleteFile(file.id)
      ElMessage.success('已移入回收站')
      await loadFiles()
    } catch { /* cancelled */ }
  } else if (cmd === 'restore') {
    await store.restoreFile(file.id)
    ElMessage.success('已还原')
    await loadFiles()
  } else if (cmd === 'permanent') {
    try {
      await ElMessageBox.confirm(`彻底删除「${file.original_name}」？此操作不可恢复。`, '彻底删除', { type: 'error' })
      await store.deletePermanent(file.id)
      ElMessage.success('已彻底删除')
      await loadFiles()
    } catch { /* cancelled */ }
  } else if (cmd === 'kb') {
    try {
      const res = await client.post('/plugins/notes/import/library', { file_id: file.id }, { timeout: 180000 })
      ElMessage.success(`已加入知识库：${res.data?.title || file.original_name}`)
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || '加入知识库失败')
    }
  } else if (cmd === 'download') {
    downloadFile(file)
  }
}

function streamSrc(file: FileItem): string {
  const token = localStorage.getItem('token') || ''
  return apiUrl(`/files/${file.id}/stream?token=${encodeURIComponent(token)}`)
}

async function previewFile(file: FileItem) {
  previewFileItem.value = file
  previewVisible.value = true
  previewSrc.value = ''
  const mime = file.mime_type || ''
  if (mime.startsWith('image/') || mime.includes('pdf')) {
    try {
      const res = await clientDownloadUrl(file.id)
      previewSrc.value = res || streamSrc(file)
    } catch {
      previewSrc.value = streamSrc(file)
    }
  } else if (mime.startsWith('audio/') || mime.startsWith('video/')) {
    previewSrc.value = streamSrc(file)
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

onMounted(loadFiles)
</script>

<style scoped>
.files-header { display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:10px; }
.header-actions { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
.muted { color:#909399; font-size:12px; }
.crumb-bar { margin:8px 0 12px; }
.loading-box { text-align:center; padding:40px; }
.file-card { margin-bottom:12px; cursor:pointer; position:relative; }
.file-card-body { text-align:center; padding:16px 4px 4px; }
.file-icon.folder, .name-cell .folder { color:#e6a23c; }
.file-name { font-size:13px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.file-meta { font-size:12px; color:#909399; margin-top:4px; }
.card-actions { position:absolute; top:6px; right:6px; display:flex; gap:2px; }
.name-cell { display:flex; align-items:center; gap:8px; }
.pager { display:flex; justify-content:center; margin-top:16px; }
.preview-center { text-align:center; min-height:40px; }
.preview-actions { text-align:center; margin-top:12px; }
</style>
