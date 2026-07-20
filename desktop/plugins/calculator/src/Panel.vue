<script setup lang="ts">
import { ref } from 'vue'
const expr = ref('')
const result = ref<string | null>(null)
function calc() {
  if (!expr.value.trim()) return
  try { result.value = String(Function('"use strict"; return (' + expr.value + ')')()) }
  catch { result.value = '错误' }
}
</script>

<template>
  <div class="panel">
    <div class="panel-hd">
      <div class="panel-icon purple">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/>
          <rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/>
        </svg>
      </div>
      <div class="panel-info"><span class="panel-title">计算器</span></div>
    </div>
    <div class="calc-row">
      <input v-model="expr" type="text" class="calc-input" placeholder="输入表达式..." @keyup.enter="calc" />
      <button class="calc-btn" @click="calc">=</button>
    </div>
    <div v-if="result !== null" class="calc-result">= {{ result }}</div>
  </div>
</template>

<style scoped>
.panel { background:#fff; border-radius:10px; border:1px solid #e8e8e8; padding:12px; }
.panel-hd { display:flex; align-items:center; gap:10px; margin-bottom:10px; }
.panel-icon { width:32px; height:32px; border-radius:8px; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.panel-icon.purple { background:#f3e5f5; }
.panel-icon svg { width:16px; height:16px; color:#9C27B0; }
.panel-info { flex:1; }
.panel-title { font-size:13px; font-weight:600; color:#1e1e1e; }
.calc-row { display:flex; gap:6px; }
.calc-input { flex:1; height:36px; border-radius:8px; border:1px solid #e0e0e0; padding:0 10px; font-size:13px; outline:none; }
.calc-input:focus { border-color:#9C27B0; }
.calc-btn { width:36px; height:36px; border-radius:8px; border:none; background:#9C27B0; color:#fff; font-size:16px; cursor:pointer; }
.calc-btn:hover { background:#7b1fa2; }
.calc-result { margin-top:6px; font-size:14px; color:#9C27B0; font-family:monospace; }
</style>
