<template>
  <el-container style="height:100vh">
    <CoreSidebar :collapsed="sidebarCollapsed" @toggle="sidebarCollapsed = !sidebarCollapsed" />
    <el-container>
      <CoreHeader @toggle-sidebar="sidebarCollapsed = !sidebarCollapsed" />
      <el-main style="background:#f5f7fa; padding:20px">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import CoreSidebar from './CoreSidebar.vue'
import CoreHeader from './CoreHeader.vue'
const sidebarCollapsed = ref(false)
</script>
