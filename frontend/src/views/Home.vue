<template>
  <el-container style="height:100vh">
    <el-header style="display:flex; align-items:center; justify-content:space-between; background:#fff; border-bottom:1px solid #dcdfe6">
      <span style="font-size:18px; font-weight:600">OmniAide</span>
      <el-dropdown v-if="auth.user">
        <span style="cursor:pointer">{{ auth.user.username }}</span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="auth.logout(); router.push('/login')">退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </el-header>
    <el-main>
      <h2>欢迎回来{{ auth.user?.username ? '，' + auth.user.username : '' }}</h2>
      <p style="color:#909399">Phase 0 基础设施搭建完成。下一步：文件管理与待办事项。</p>
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
onMounted(() => {
  if (!auth.user) auth.fetchUser()
})
</script>
