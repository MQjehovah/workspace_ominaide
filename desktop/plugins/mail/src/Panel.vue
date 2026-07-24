<template>
  <div class="panel">
    <div class="panel-hd">
      <span class="title">邮件</span>
    </div>
    <div v-if="data?.items?.length" class="list">
      <div v-for="(item, i) in data.items" :key="i" class="item" @click="openPage">
        <div class="item-title">{{ item.title }}</div>
        <div class="item-sub">{{ item.subtitle }}</div>
      </div>
    </div>
    <div v-else class="empty">暂无邮件</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ data: any; execute: Function; openPage: Function }>()
</script>

<style scoped>
.panel { padding: 8px 12px; font-size: 12px; }
.panel-hd { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.title { font-weight: 600; font-size: 13px; color: #1a1a2e; }
.list { display: flex; flex-direction: column; gap: 6px; }
.item { cursor: pointer; padding: 6px 8px; border-radius: 6px; background: #f8f9fa; }
.item:hover { background: #e8f4fd; }
.item-title { font-size: 12px; color: #333; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.item-sub { font-size: 11px; color: #999; }
.empty { text-align: center; color: #999; padding: 20px; font-size: 12px; }
</style>
