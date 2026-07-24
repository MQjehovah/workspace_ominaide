<template>
  <div class="panel-card">
    <div class="panel-hd">
      <span class="panel-icon">{{ defaultIcon }}</span>
      <div class="panel-hd-text">
        <span class="panel-title">{{ data.title }}</span>
        <span v-if="data.subtitle" class="panel-subtitle">{{ data.subtitle }}</span>
      </div>
      <button v-if="hasPage" class="panel-arrow" @click.stop="openPage">›</button>
    </div>
    <div v-if="data.description" class="panel-desc">{{ data.description }}</div>
    <div v-if="data.items?.length" class="panel-items">
      <div v-for="(item, idx) in data.items" :key="idx" class="panel-item" :class="{ clickable: !!item.action }" @click="handleItemClick(item)">
        <span class="pi-title">{{ item.title }}</span>
        <span v-if="item.subtitle" class="pi-subtitle">{{ item.subtitle }}</span>
      </div>
    </div>
    <div v-if="data.switches?.length" class="panel-switches">
      <div v-for="(sw, idx) in data.switches" :key="idx" class="panel-switch-row">
        <span class="ps-label">{{ sw.label }}</span>
        <label class="switch-toggle">
          <input type="checkbox" :checked="sw.value" @change="handleSwitch(sw, ($event.target as HTMLInputElement).checked)">
          <span class="switch-slider"></span>
        </label>
      </div>
    </div>
    <div v-if="data.buttons?.length" class="panel-buttons">
      <button v-for="(btn, idx) in data.buttons" :key="idx" class="panel-btn" @click.stop="execute(btn.command)">{{ btn.label }}</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PanelData, PanelItem } from '../../shared/types'

const props = defineProps<{
  pluginId: string
  data: PanelData
  hasPage: boolean
}>()

const emit = defineEmits<{
  execute: [command: string, args?: unknown]
  openPage: []
}>()

const defaultIcon = computed(() => {
  const icons: Record<string, string> = {
    assistant: '💬', calculator: '🔢', 'clipboard-history': '📋', files: '📁', notes: '📝',
    player: '🎵', 'quick-notes': '⚡', remote: '🖥️', rss: '📡', schedule: '📅',
    screenshot: '📸', todo: '✅', notifications: '🔔', everything: '🔍',
  }
  return icons[props.pluginId] || '🔌'
})

function execute(command: string) {
  emit('execute', command)
}

function openPage() {
  emit('openPage')
}

function handleItemClick(item: PanelItem) {
  if (item.action) emit('execute', item.action, item.actionArgs)
}

function handleSwitch(sw: any, newVal: boolean) {
  emit('execute', sw.command, sw.commandArgs)
}
</script>

<style scoped>
.panel-card { background:#fff; border-radius:10px; border:1px solid #edf2f7; overflow:hidden; transition:box-shadow 0.15s, border-color 0.15s; }
.panel-card:hover { border-color:#e2e8f0; box-shadow:0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.03); }
.panel-hd { display:flex; align-items:center; gap:10px; padding:12px 14px; }
.panel-icon { width:36px; height:36px; border-radius:9px; background:#eef0f4; display:flex; align-items:center; justify-content:center; font-size:17px; flex-shrink:0; }
.panel-hd-text { flex:1; min-width:0; display:flex; flex-direction:column; gap:1px; }
.panel-title { font-size:14px; font-weight:600; color:#1a202c; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.panel-subtitle { font-size:11px; color:#a0aec0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.panel-arrow { width:26px; height:26px; border:none; border-radius:8px; background:transparent; color:#cbd5e0; font-size:20px; line-height:26px; text-align:center; cursor:pointer; flex-shrink:0; display:flex; align-items:center; justify-content:center; transition:all 0.12s; }
.panel-arrow:hover { background:#edf2f7; color:#4a5568; }
.panel-desc { padding:0 14px 12px; font-size:11px; color:#a0aec0; line-height:1.5; }
.panel-items { padding:0 0 4px; border-top:1px solid #f0f4f8; }
.panel-item { display:flex; flex-direction:column; gap:2px; padding:8px 14px; transition:background 0.1s; }
.panel-item.clickable { cursor:pointer; }
.panel-item.clickable:hover { background:#f7fafc; }
.panel-item.clickable:active { background:#edf2f7; }
.pi-title { font-size:12px; font-weight:500; color:#2d3748; }
.pi-subtitle { font-size:10px; color:#a0aec0; }
.panel-switches { border-top:1px solid #f0f4f8; padding:4px 14px; }
.panel-switch-row { display:flex; align-items:center; justify-content:space-between; padding:7px 0; }
.ps-label { font-size:12px; color:#2d3748; }
.switch-toggle { position:relative; width:36px; height:20px; flex-shrink:0; }
.switch-toggle input { opacity:0; width:0; height:0; }
.switch-slider { position:absolute; inset:0; background:#e2e8f0; border-radius:10px; cursor:pointer; transition:background .2s; }
.switch-slider::before { content:''; position:absolute; left:2px; top:2px; width:16px; height:16px; border-radius:8px; background:#fff; transition:transform .2s; box-shadow:0 1px 2px rgba(0,0,0,0.1); }
.switch-toggle input:checked + .switch-slider { background:#4f46e5; }
.switch-toggle input:checked + .switch-slider::before { transform:translateX(16px); }
.panel-buttons { display:flex; gap:6px; padding:8px 14px 12px; border-top:1px solid #f0f4f8; min-height:40px; }
.panel-btn { flex:1; padding:7px 0; font-size:12px; font-weight:500; border-radius:7px; border:1px solid #e2e8f0; background:#fff; color:#4a5568; cursor:pointer; text-align:center; transition:all 0.12s; }
.panel-btn:hover { background:#f7fafc; border-color:#cbd5e0; color:#2d3748; }
.panel-btn:active { background:#edf2f7; }
</style>
