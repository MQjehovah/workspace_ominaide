<template>
  <div>
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px">
      <h2 style="margin:0">文件管理</h2>
      <div style="display:flex; gap:8px">
        <el-upload
          :http-request="handleUpload"
          :show-file-list="false"
          :multiple="true"
          drag
        >
          <el-button type="primary" :icon="Upload">上传文件</el-button>
        </el-upload>
        <el-button-group>
          <el-button :type="viewMode === 'grid' ? 'primary' : 'default'" :icon="Grid" @click="viewMode = 'grid'" />
          <el-button :type="viewMode === 'list' ? 'primary' : 'default'" :icon="List" @click="viewMode = 'list'" />
        </el-button-group>
      </div>
    </div>

    <div v-if="store.loading" style="text-align:center; padding:40px">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
    </div>

    <!-- Grid View -->
    <template v-else-if="viewMode === 'grid'">
      <el-row :gutter="12">
        <el-col v-for="file in store.files" :key="file.id" :span="6" :xs="12" :sm="8" :md="6" :lg="4">
          <el-card shadow="hover" style="margin-bottom:12px; cursor:pointer" @click="previewFile(file)">
            <div style="text-align:center; padding:16px">
              <el-icon :size="48" style="margin-bottom:8px">
                <component :is="getIconComponent(file.mime_type)" />
              </el-icon>
              <div style="font-size:13px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">
                {{ file.original_name }}
              </div>
              <div style="font-size:12px; color:#909399; margin-top:4px">
                {{ store.formatSize(file.size) }}
              </div>
            </div>
            <div style="position:absolute; top:8px; right:8px">
              <el-button
                :icon="file.is_favorite ? StarFilled : Star"
                :type="file.is_favorite ? 'warning' : 'default'"
                text
                size="small"
                @click.stop="store.toggleFavorite(file.id)"
              />
            </div>
          </el-card>
        </el-col>
      </el-row>
    </template>

    <!-- List View -->
    <el-table v-else :data="store.files" stripe style="width:100%" @row-click="previewFile">
      <el-table-column prop="original_name" label="名称" min-width="200">
        <template #default="{ row }">
          <div style="display:flex; align-items:center; gap:8px">
            <el-icon><component :is="getIconComponent(row.mime_type)" /></el-icon>
            <span>{{ row.original_name }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="size" label="大小" width="100">
        <template #default="{ row }">{{ store.formatSize(row.size) }}</template>
      </el-table-column>
      <el-table-column prop="mime_type" label="类型" width="120" />
      <el-table-column prop="created_at" label="创建时间" width="180" />
      <el-table-column width="80">
        <template #default="{ row }">
          <el-button
            :icon="row.is_favorite ? StarFilled : Star"
            :type="row.is_favorite ? 'warning' : 'default'"
            text
            @click.stop="store.toggleFavorite(row.id)"
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- Pagination -->
    <div style="display:flex; justify-content:center; margin-top:16px" v-if="store.total > store.pageSize">
      <el-pagination
        v-model:current-page="store.page"
        :page-size="store.pageSize"
        :total="store.total"
        layout="prev, pager, next"
        @current-change="store.fetchFiles()"
      />
    </div>

    <!-- File Preview Dialog -->
    <el-dialog v-model="previewVisible" :title="previewFileItem?.original_name" width="60%">
      <div v-if="previewFileItem">
        <p><strong>类型:</strong> {{ previewFileItem.mime_type }}</p>
        <p><strong>大小:</strong> {{ store.formatSize(previewFileItem.size) }}</p>
        <p><strong>创建时间:</strong> {{ previewFileItem.created_at }}</p>
        <div v-if="previewFileItem.mime_type?.startsWith('image/')" style="text-align:center">
          <img :src="previewSrc" style="max-width:100%; max-height:500px" />
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useFileStore, FileItem } from '@/stores/core/file'
import { Upload, Grid, List, Loading, StarFilled, Star } from '@element-plus/icons-vue'
import {
  Document, Picture, VideoCamera, Headset, Reading, FolderDelete
} from '@element-plus/icons-vue'
import client from '@/api/client'

const route = useRoute()
const store = useFileStore()
const viewMode = ref<'grid' | 'list'>('grid')
const previewVisible = ref(false)
const previewFileItem = ref<FileItem | null>(null)
const previewSrc = ref('')

const iconMap: Record<string, any> = {
  Document, Picture, VideoCamera, Headset, Reading, FolderDelete, StarFilled, Star
}

function getIconComponent(mime: string | null) {
  const name = store.getFileIcon(mime)
  return iconMap[name] || Document
}

async function handleUpload(options: any) {
  const { file, onProgress, onSuccess, onError } = options
  try {
    const { upload_url, file_id } = await store.getUploadUrl(file.name)
    const xhr = new XMLHttpRequest()
    xhr.upload.onprogress = (e) => {
      if (e.total) onProgress({ percent: Math.round((e.loaded / e.total) * 100) })
    }
    await new Promise<void>((resolve, reject) => {
      xhr.onload = () => {
        if (xhr.status === 200) resolve()
        else reject(new Error(`Upload failed: ${xhr.status}`))
      }
      xhr.onerror = () => reject(new Error('Upload failed'))
      xhr.open('PUT', upload_url)
      xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream')
      xhr.send(file)
    })
    await store.confirmUpload(file_id)
    await store.fetchFiles()
    onSuccess?.()
  } catch (err: any) {
    onError?.(err)
  }
}

async function previewFile(file: FileItem) {
  previewFileItem.value = file
  previewVisible.value = true
  if (file.mime_type?.startsWith('image/')) {
    const res = await client.get(`/files/${file.id}/download-url`)
    previewSrc.value = res.data.download_url
  }
}

watch(() => route.query.workspace_id, (val) => {
  if (val) {
    store.currentWorkspaceId = Number(val)
    store.fetchFiles()
  }
})

onMounted(() => {
  if (route.query.workspace_id) {
    store.currentWorkspaceId = Number(route.query.workspace_id)
  }
  store.fetchFiles()
})
</script>
