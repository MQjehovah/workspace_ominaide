<template>
  <el-header style="display:flex; align-items:center; justify-content:space-between; background:#fff; border-bottom:1px solid #dcdfe6; padding:0 20px; height:56px">
    <div style="display:flex; align-items:center">
      <el-button :icon="Expand" text @click="$emit('toggle-sidebar')" />
    </div>
    <div style="display:flex; align-items:center; gap:12px">
      <el-dropdown v-if="auth.user">
        <span style="cursor:pointer; display:flex; align-items:center; gap:4px">
          {{ auth.user.username }}
          <el-icon><ArrowDown /></el-icon>
        </span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="auth.logout(); router.push('/login')">退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </el-header>
</template>

<script setup lang="ts">
import { Expand, ArrowDown } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

defineEmits<{ 'toggle-sidebar': [] }>()
const router = useRouter()
const auth = useAuthStore()
</script>
