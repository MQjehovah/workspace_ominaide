<template>
  <div>
    <h2>用户管理</h2>
    <el-table :data="users" stripe style="width:100%" v-loading="loading">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="username" label="用户名" min-width="140" />
      <el-table-column prop="email" label="邮箱" min-width="200" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-switch
            :model-value="row.is_active"
            :loading="togglingId === row.id"
            @change="(val: boolean) => toggleActive(row, val)"
          />
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="180" />
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import client from '@/api/client'
import { ElMessage } from 'element-plus'

interface AdminUser {
  id: number
  username: string
  email: string
  is_active: boolean
  created_at: string | null
}

const users = ref<AdminUser[]>([])
const loading = ref(false)
const togglingId = ref<number | null>(null)

async function fetchUsers() {
  loading.value = true
  try {
    const res = await client.get('/auth/users')
    users.value = res.data
  } finally {
    loading.value = false
  }
}

async function toggleActive(row: AdminUser, val: boolean) {
  togglingId.value = row.id
  try {
    await client.put(`/auth/users/${row.id}/toggle-active`, { is_active: val })
    row.is_active = val
    ElMessage.success(val ? '用户已启用' : '用户已禁用')
  } catch {
    ElMessage.error('操作失败')
  } finally {
    togglingId.value = null
  }
}

onMounted(fetchUsers)
</script>
