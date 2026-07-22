<script setup lang="ts">
defineProps<{ data: any; execute: (a: string, args?: any) => Promise<any>; openPage: () => void; refresh: () => Promise<void> }>()
const api = (window as any).mqbox?.api
</script>
<template>
  <div class="panel">
    <div class="panel-hd"><span class="title">AI 助理</span><button class="panel-arrow" @click="openPage">›</button></div>
    <p style="font-size:11px;color:#909399">Ctrl+Shift+A 呼出助理 · 语音对话 · 自然语言操作</p>
  </div>
</template>
<style scoped>
.panel { background:#fff; border-radius:10px; border:1px solid #e8e8e8; padding:12px; }
.panel-hd { display:flex;align-items:center;justify-content:space-between;margin-bottom:6px; }
.title { font-size:13px;font-weight:600; }
.panel-arrow { width:24px;height:24px;border:none;border-radius:6px;background:transparent;color:#ccc;cursor:pointer;font-size:18px;line-height:1;display:flex;align-items:center;justify-content:center; }
.panel-arrow:hover { background:#f5f5f5;color:#666; }
</style>
