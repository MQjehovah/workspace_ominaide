<script setup lang="ts">
defineProps<{ data: any; execute: (a: string, args?: any) => Promise<any>; openPage: () => void; refresh: () => Promise<void> }>()
</script>
<template>
  <div class="panel">
    <div class="panel-hd"><span class="title">远程控制</span></div>
    <button class="btn" @click="openPage">打开远程控制</button>
  </div>
</template>
<style scoped>
.panel { background:#fff; border-radius:10px; border:1px solid #e8e8e8; padding:12px; }
.panel-hd { margin-bottom:8px; }
.title { font-size:13px; font-weight:600; }
.btn { width:100%; padding:8px; border:none; border-radius:8px; background:#fce4ec; color:#e91e63; font-size:12px; cursor:pointer; }
.btn:hover { background:#f8bbd0; }
</style>
