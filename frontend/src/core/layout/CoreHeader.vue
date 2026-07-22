<template>
  <div class="header">
    <div class="header-left">
      <button class="toggle-btn" @click="$emit('toggle-sidebar')">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
      </button>
      <span class="breadcrumb">{{ route.name }}</span>
    </div>
    <div class="header-right">
      <el-dropdown v-if="auth.user" trigger="click">
        <div class="user-info">
          <el-avatar :size="28">{{ auth.user.username[0]?.toUpperCase() }}</el-avatar>
          <span class="user-name">{{ auth.user.username }}</span>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="router.push('/settings')">
              <el-icon><Setting /></el-icon>设置
            </el-dropdown-item>
            <el-dropdown-item divided @click="auth.logout(); router.push('/login')" style="color:#f56c6c">
              <el-icon><SwitchButton /></el-icon>退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { Setting, SwitchButton } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

defineEmits<{ 'toggle-sidebar': [] }>()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
</script>

<style scoped>
.header { height: var(--header-height); display: flex; align-items: center; justify-content: space-between; padding: 0 20px; background: #fff; border-bottom: 1px solid var(--color-border); flex-shrink: 0; }
.header-left { display: flex; align-items: center; gap: 12px; }
.toggle-btn { width: 36px; height: 36px; border: none; border-radius: 8px; background: transparent; cursor: pointer; display: flex; align-items: center; justify-content: center; color: #666; }
.toggle-btn:hover { background: #f5f5f5; color: #333; }
.breadcrumb { font-size: 14px; font-weight: 500; color: #1a1a2e; }
.header-right { display: flex; align-items: center; gap: 12px; }
.user-info { display: flex; align-items: center; gap: 8px; cursor: pointer; padding: 4px 8px; border-radius: 8px; }
.user-info:hover { background: #f5f5f5; }
.user-name { font-size: 13px; color: #333; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
