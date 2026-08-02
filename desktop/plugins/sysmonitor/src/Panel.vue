<template>
  <div class="panel">
    <div class="panel-hd"><span class="title">系统监控</span><button class="open-btn" @click="openPage">›</button></div>
    <div class="items" v-if="data?.items?.length">
      <div v-for="(item, i) in data.items" :key="i" class="row">
        <span class="label">{{ item.title }}</span>
        <span class="val">{{ item.subtitle }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ data: any; execute: Function; openPage: Function }>()
</script>

<style scoped>
.panel { padding: 8px 12px; font-size: 12px; }
.panel-hd { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.title { font-weight: 600; font-size: 13px; color: #1a1a2e; }
.open-btn { width: 24px; height: 24px; border: none; border-radius: 6px; background: transparent; color: #ccc; cursor: pointer; font-size: 18px; line-height: 1; }
.open-btn:hover { background: #f5f5f5; color: #666; }
.items { display: flex; flex-direction: column; gap: 3px; }
.row { display: flex; justify-content: space-between; align-items: center; }
.label { color: #909399; }
.val { color: #333; font-weight: 600; }
</style>
