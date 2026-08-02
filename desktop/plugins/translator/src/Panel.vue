<template>
  <div class="panel">
    <div class="panel-hd"><span class="title">翻译助手</span><button class="open-btn" @click="openPage">›</button></div>
    <div class="desc">中英日韩法德西俄，输入即译</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ data: any; execute: Function; openPage: Function }>()
</script>

<style scoped>
.panel { padding: 8px 12px; font-size: 12px; }
.panel-hd { display: flex; justify-content: space-between; align-items: center; }
.title { font-weight: 600; font-size: 13px; color: #1a1a2e; }
.open-btn { width: 24px; height: 24px; border: none; border-radius: 6px; background: transparent; color: #ccc; cursor: pointer; font-size: 18px; line-height: 1; }
.open-btn:hover { background: #f5f5f5; color: #666; }
.desc { margin-top: 6px; font-size: 11px; color: #909399; }
</style>
