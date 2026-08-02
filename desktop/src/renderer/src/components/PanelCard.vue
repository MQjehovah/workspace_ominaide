<template>
  <div class="neu-card">
    <div class="panel-hd">
      <span class="panel-icon">{{ defaultIcon }}</span>
      <div class="panel-hd-text">
        <span class="panel-title">{{ data.title }}</span>
        <span v-if="data.subtitle" class="panel-subtitle">{{ data.subtitle }}</span>
      </div>
      <button v-if="hasPage" class="panel-arrow" @click.stop="openPage">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="m9 18 6-6-6-6"/></svg>
      </button>
    </div>
    <div v-if="data.description" class="panel-desc">{{ data.description }}</div>

    <!-- Icon grid layout (phone-style app tiles) -->
    <div v-if="data.itemsLayout === 'grid' && data.items?.length" class="panel-grid">
      <div
        v-for="(item, idx) in data.items"
        :key="idx"
        class="grid-tile"
        :class="{ clickable: !!item.action }"
        :title="item.subtitle || item.title"
        @click="handleItemClick(item)"
      >
        <div class="grid-icon" :style="{ background: item.color || '#6366f1' }">
          <span>{{ item.icon || '🔗' }}</span>
        </div>
        <div class="grid-label">{{ item.title }}</div>
      </div>
    </div>

    <div v-if="data.itemsLayout !== 'grid' && data.items?.length" class="panel-items">
      <div
        v-for="(item, idx) in data.items"
        :key="idx"
        class="panel-item"
        :class="{ clickable: !!item.action }"
        @click="handleItemClick(item)"
      >
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
    player: '🎵', remote: '🖥️', rss: '📡', schedule: '📅',
    screenshot: '📸', todo: '✅', notifications: '🔔', everything: '🔍',
    activity: '📊', translator: '🌐', sysmonitor: '🖥️', pomodoro: '🍅',
    quicklinks: '⚡',
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
.neu-card {
  --neu-bg: #e4e9f0;
  --neu-light: #ffffff;
  --neu-dark: #c3c9d4;
  background: var(--neu-bg);
  border-radius: 14px;
  padding: 4px;
  box-shadow:
    7px 7px 14px rgba(163, 177, 198, 0.55),
    -7px -7px 14px rgba(255, 255, 255, 0.75);
  transition: box-shadow 0.15s ease;
}
.neu-card:hover {
  box-shadow:
    9px 9px 18px rgba(163, 177, 198, 0.6),
    -9px -9px 18px rgba(255, 255, 255, 0.85);
}

.panel-hd { display: flex; align-items: center; gap: 10px; padding: 12px 14px 6px; }
.panel-icon {
  width: 38px; height: 38px; border-radius: 12px; flex-shrink: 0;
  background: var(--neu-bg);
  display: flex; align-items: center; justify-content: center;
  font-size: 18px;
  box-shadow:
    inset 3px 3px 6px rgba(163, 177, 198, 0.55),
    inset -3px -3px 6px rgba(255, 255, 255, 0.8);
}
.panel-hd-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.panel-title { font-size: 14px; font-weight: 700; color: #3a4256; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; letter-spacing: 0.2px; }
.panel-subtitle { font-size: 11px; color: #8a94a8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.panel-arrow {
  width: 28px; height: 28px; border: none; border-radius: 50%; flex-shrink: 0;
  background: var(--neu-bg); color: #8a94a8; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  box-shadow:
    3px 3px 6px rgba(163, 177, 198, 0.55),
    -3px -3px 6px rgba(255, 255, 255, 0.8);
  transition: all 0.12s;
}
.panel-arrow:hover { color: #3a4256; transform: translateX(2px); }
.panel-arrow:active {
  box-shadow:
    inset 3px 3px 6px rgba(163, 177, 198, 0.6),
    inset -3px -3px 6px rgba(255, 255, 255, 0.8);
}

.panel-desc { padding: 2px 16px 8px; font-size: 11px; color: #8a94a8; line-height: 1.5; }

/* Icon grid layout */
.panel-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; padding: 4px 14px 14px; }
.grid-tile { display: flex; flex-direction: column; align-items: center; gap: 4px; cursor: default; }
.grid-tile.clickable { cursor: pointer; }
.grid-icon {
  width: 46px; height: 46px; border-radius: 14px; display: flex; align-items: center; justify-content: center;
  font-size: 22px; box-shadow: 4px 4px 8px rgba(163,177,198,0.45), -4px -4px 8px rgba(255,255,255,0.8);
  transition: transform 0.1s;
}
.grid-tile.clickable:hover .grid-icon { transform: scale(1.06); }
.grid-tile.clickable:active .grid-icon { transform: scale(0.95); }
.grid-label { font-size: 10px; color: #4a5268; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: center; }

.panel-items { padding: 2px 10px 10px; display: flex; flex-direction: column; gap: 4px; }
.panel-item {
  display: flex; flex-direction: column; gap: 2px;
  padding: 7px 10px; border-radius: 9px; transition: background 0.12s, box-shadow 0.12s;
}
.panel-item.clickable { cursor: pointer; }
.panel-item.clickable:hover {
  box-shadow:
    inset 3px 3px 6px rgba(163, 177, 198, 0.4),
    inset -3px -3px 6px rgba(255, 255, 255, 0.7);
}
.panel-item.clickable:active {
  box-shadow:
    inset 4px 4px 8px rgba(163, 177, 198, 0.55),
    inset -4px -4px 8px rgba(255, 255, 255, 0.8);
}
.pi-title { font-size: 12px; font-weight: 500; color: #4a5268; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pi-subtitle { font-size: 10px; color: #8a94a8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.panel-switches { padding: 2px 16px 6px; display: flex; flex-direction: column; gap: 4px; }
.panel-switch-row { display: flex; align-items: center; justify-content: space-between; padding: 6px 0; }
.ps-label { font-size: 12px; color: #4a5268; }
.switch-toggle { position: relative; width: 40px; height: 22px; flex-shrink: 0; }
.switch-toggle input { opacity: 0; width: 0; height: 0; }
.switch-slider {
  position: absolute; inset: 0; border-radius: 11px; cursor: pointer; transition: background 0.2s;
  background: var(--neu-bg);
  box-shadow:
    inset 2px 2px 4px rgba(163, 177, 198, 0.55),
    inset -2px -2px 4px rgba(255, 255, 255, 0.8);
}
.switch-slider::before {
  content: ''; position: absolute; left: 3px; top: 3px; width: 16px; height: 16px; border-radius: 8px;
  background: #f5f7fa; transition: transform 0.2s;
  box-shadow: 2px 2px 4px rgba(163, 177, 198, 0.6);
}
.switch-toggle input:checked + .switch-slider {
  background: linear-gradient(145deg, #5b6ee1, #4f46e5);
  box-shadow:
    inset 2px 2px 4px rgba(0, 0, 0, 0.15),
    inset -2px -2px 4px rgba(255, 255, 255, 0.2);
}
.switch-toggle input:checked + .switch-slider::before { transform: translateX(18px); background: #fff; }

.panel-buttons { display: flex; gap: 8px; padding: 6px 14px 12px; }
.panel-btn {
  flex: 1; padding: 8px 0; font-size: 12px; font-weight: 600; color: #4a5268;
  border: none; border-radius: 10px; cursor: pointer; text-align: center;
  background: var(--neu-bg);
  box-shadow:
    4px 4px 8px rgba(163, 177, 198, 0.55),
    -4px -4px 8px rgba(255, 255, 255, 0.8);
  transition: all 0.12s;
}
.panel-btn:hover { color: #4f46e5; }
.panel-btn:active {
  box-shadow:
    inset 4px 4px 8px rgba(163, 177, 198, 0.6),
    inset -4px -4px 8px rgba(255, 255, 255, 0.8);
}
</style>
