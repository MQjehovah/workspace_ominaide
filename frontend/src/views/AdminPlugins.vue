<template>
  <div class="page-wrapper">
    <div class="page-header"><h2>插件管理</h2></div>
    <div class="page-card">
      <div class="page-card-body">
        <el-table :data="plugins" stripe style="width:100%" v-loading="loading">
          <el-table-column prop="name" label="名称" min-width="140" />
          <el-table-column prop="title" label="标题" min-width="160" />
          <el-table-column prop="version" label="版本" width="100" />
          <el-table-column label="启用" width="80">
            <template #default="{ row }">
              <el-switch
                :model-value="row.enabled"
                :loading="togglingName === row.name"
                @change="(val: boolean) => toggleEnabled(row, val)"
              />
            </template>
          </el-table-column>
          <el-table-column prop="installed_at" label="安装时间" width="180" />
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import client from '@/api/client'
import { ElMessage } from 'element-plus'

interface PluginItem {
  name: string
  title: string
  version: string
  enabled: boolean
  installed_at: string
}

const plugins = ref<PluginItem[]>([])
const loading = ref(false)
const togglingName = ref<string | null>(null)

async function fetchPlugins() {
  loading.value = true
  try {
    const res = await client.get('/plugins')
    plugins.value = res.data
  } finally {
    loading.value = false
  }
}

async function toggleEnabled(row: PluginItem, val: boolean) {
  togglingName.value = row.name
  try {
    const res = await client.post(`/plugins/${row.name}/toggle`)
    row.enabled = res.data.enabled
    ElMessage.success(res.data.enabled ? '插件已启用' : '插件已禁用')
  } catch {
    ElMessage.error('操作失败')
  } finally {
    togglingName.value = null
  }
}

onMounted(fetchPlugins)
</script>
