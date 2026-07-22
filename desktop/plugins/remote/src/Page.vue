<script setup lang="ts">
import { ref } from 'vue'
defineProps<{ data: any; execute: (a: string, args?: any) => Promise<any>; refresh?: () => void; close: () => void }>()
const mode = ref<'menu' | 'host' | 'viewer'>('menu')
</script>
<template>
  <div class="page">
    <div class="header"><h2>远程控制</h2></div>
    <div v-if="mode === 'menu'" class="menu">
      <button class="card" @click="mode = 'host'">允许控制本机（被控端）</button>
      <button class="card" @click="mode = 'viewer'">控制其他设备（主控端）</button>
    </div>
    <div v-else-if="mode === 'host'">
      <p>被控端（Task 4 填充）</p>
      <button @click="mode = 'menu'">返回</button>
    </div>
    <div v-else>
      <p>主控端（Task 5 填充）</p>
      <button @click="mode = 'menu'">返回</button>
    </div>
  </div>
</template>
<style scoped>
.page { height:100vh; background:#f8f9fa; font-family:-apple-system,sans-serif; }
.header { padding:16px 24px; border-bottom:1px solid #e9ecef; }
.header h2 { margin:0; font-size:18px; }
.menu { padding:24px; display:flex; flex-direction:column; gap:12px; }
.card { padding:24px; border:1px solid #e9ecef; border-radius:12px; background:#fff; cursor:pointer; font-size:14px; text-align:left; }
.card:hover { border-color:#e91e63; }
</style>
