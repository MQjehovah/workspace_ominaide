<template>
  <div class="plugin-page">
    <div class="header">
      <el-button text @click="close">{{ pluginId }}</el-button>
      <el-button text @click="close">✕</el-button>
    </div>
    <div class="content">
      <p style="color:#909399;text-align:center;padding:40px">插件页面: {{ pluginId }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const params = new URLSearchParams(window.location.search)
const pluginId = ref(params.get('pluginId') || '')

function close() { window.close() }
</script>

<style scoped>
.plugin-page { height:100vh; display:flex; flex-direction:column; }
.header { display:flex; justify-content:space-between; padding:10px 16px; border-bottom:1px solid #e4e7ed; -webkit-app-region:drag; }
.content { flex:1; overflow-y:auto; }
</style>
