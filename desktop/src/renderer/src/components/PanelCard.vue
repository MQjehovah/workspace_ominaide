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

    <!-- Rich blocks: progress, charts, inline forms -->
    <div v-if="data.progress?.length" class="panel-progress">
      <div v-for="(p, idx) in data.progress" :key="'p-' + idx" class="progress-row">
        <div class="progress-head">
          <span class="progress-label">{{ p.label || '进度' }}</span>
          <span class="progress-value">{{ p.value }}{{ p.max ? ' / ' + p.max : '' }}{{ p.hint ? ' · ' + p.hint : '' }}</span>
        </div>
        <div class="progress-track">
          <div
            class="progress-fill"
            :class="'tone-' + (p.tone || 'default')"
            :style="{ width: progressPercent(p) + '%' }"
          ></div>
        </div>
      </div>
    </div>

    <div v-if="data.charts?.length" class="panel-charts">
      <div v-for="(chart, idx) in data.charts" :key="'c-' + idx" class="chart-block">
        <div class="chart-label">{{ chart.label || '' }}</div>
        <svg v-if="chart.type === 'line'" class="chart-line" viewBox="0 0 100 40" preserveAspectRatio="none">
          <polyline :points="chartPoints(chart)" fill="none" stroke="#4f46e5" stroke-width="1.6" vector-effect="non-scaling-stroke" />
        </svg>
        <div v-else class="chart-bars">
          <div v-for="(v, i) in chart.values" :key="i" class="chart-bar-wrap" :title="`${chart.labels[i] || ''}: ${v}${chart.unit || ''}`">
            <div class="chart-bar" :style="{ height: barHeight(chart, v) + '%' }"></div>
          </div>
        </div>
        <div class="chart-axis">
          <span v-for="(label, i) in chart.labels" :key="i" class="chart-tick">{{ label }}</span>
        </div>
      </div>
    </div>

    <div v-if="data.forms?.length" class="panel-forms">
      <form
        v-for="(form, fi) in data.forms"
        :key="'f-' + fi"
        class="panel-form"
        @submit.prevent="submitForm(form, fi)"
      >
        <div v-for="field in form.fields" :key="field.key" class="form-row">
          <label class="form-label">{{ field.label || field.key }}</label>
          <textarea
            v-if="field.type === 'textarea'"
            v-model="formValues[String(fi)][field.key]"
            class="form-input form-textarea"
            :placeholder="field.placeholder"
          ></textarea>
          <select
            v-else-if="field.type === 'select'"
            v-model="formValues[String(fi)][field.key]"
            class="form-input"
          >
            <option v-for="opt in field.options || []" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
          <label v-else-if="field.type === 'switch'" class="form-switch">
            <input type="checkbox" v-model="formValues[String(fi)][field.key]" />
            <span class="switch-slider"></span>
          </label>
          <input
            v-else
            v-model="formValues[String(fi)][field.key]"
            class="form-input"
            :type="field.type === 'number' ? 'number' : 'text'"
            :placeholder="field.placeholder"
          />
        </div>
        <button class="panel-btn form-submit" type="submit">{{ form.submitLabel || '提交' }}</button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import type { PanelData, PanelItem, PanelForm, PanelChart } from '../../shared/types'

const props = defineProps<{
  pluginId: string
  data: PanelData
  hasPage: boolean
}>()

const emit = defineEmits<{
  execute: [command: string, args?: unknown]
  openPage: []
}>()

const formValues = reactive<Record<string, Record<string, any>>>({})

function initForms() {
  for (const key of Object.keys(formValues)) delete formValues[key]
  const forms = props.data.forms || []
  forms.forEach((form, fi) => {
    const values: Record<string, any> = {}
    for (const field of form.fields || []) {
      if (field.value !== undefined) {
        values[field.key] = field.value
      } else if (field.type === 'switch') {
        values[field.key] = false
      } else if (field.type === 'number') {
        values[field.key] = 0
      } else if (field.type === 'select') {
        values[field.key] = field.options?.[0]?.value ?? ''
      } else {
        values[field.key] = ''
      }
    }
    formValues[String(fi)] = values
  })
}

watch(() => props.data, initForms, { immediate: true, deep: true })

function submitForm(form: PanelForm, index: number) {
  emit('execute', form.command, { ...(form.commandArgs || {}), ...(formValues[String(index)] || {}) })
}

function progressPercent(p: { value: number; max?: number }) {
  const max = p.max && p.max > 0 ? p.max : 100
  return Math.max(0, Math.min(100, Math.round((p.value / max) * 100)))
}

function barHeight(chart: PanelChart, value: number) {
  const max = Math.max(...chart.values, 1)
  return Math.max(4, Math.round((value / max) * 100))
}

function chartPoints(chart: PanelChart) {
  const values = chart.values || []
  if (values.length === 0) return ''
  const max = Math.max(...values, 1)
  const step = values.length > 1 ? 100 / (values.length - 1) : 0
  return values
    .map((v, i) => `${(i * step).toFixed(2)},${(38 - (v / max) * 34).toFixed(2)}`)
    .join(' ')
}

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

/* Rich blocks */
.panel-progress { padding: 2px 16px 8px; display: flex; flex-direction: column; gap: 8px; }
.progress-head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 4px; }
.progress-label { font-size: 11.5px; color: #4a5268; font-weight: 500; }
.progress-value { font-size: 10px; color: #8a94a8; white-space: nowrap; }
.progress-track {
  height: 8px; border-radius: 4px; overflow: hidden; background: var(--neu-bg);
  box-shadow: inset 2px 2px 4px rgba(163, 177, 198, 0.5), inset -2px -2px 4px rgba(255, 255, 255, 0.8);
}
.progress-fill { height: 100%; border-radius: 4px; transition: width 0.3s ease; background: linear-gradient(90deg, #6d7cf0, #4f46e5); }
.progress-fill.tone-success { background: linear-gradient(90deg, #34d399, #059669); }
.progress-fill.tone-warning { background: linear-gradient(90deg, #fbbf24, #d97706); }
.progress-fill.tone-danger { background: linear-gradient(90deg, #f87171, #dc2626); }

.panel-charts { padding: 2px 16px 10px; display: flex; flex-direction: column; gap: 10px; }
.chart-block { display: flex; flex-direction: column; gap: 4px; }
.chart-label { font-size: 10.5px; color: #8a94a8; }
.chart-bars { display: flex; align-items: flex-end; gap: 4px; height: 44px; }
.chart-bar-wrap { flex: 1; display: flex; align-items: flex-end; height: 100%; }
.chart-bar { width: 100%; border-radius: 3px 3px 1px 1px; background: linear-gradient(180deg, #8b95f7, #4f46e5); min-height: 2px; }
.chart-line { width: 100%; height: 44px; }
.chart-axis { display: flex; gap: 4px; }
.chart-tick { flex: 1; font-size: 9px; color: #a3abbd; text-align: center; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }

.panel-forms { padding: 2px 14px 12px; display: flex; flex-direction: column; gap: 10px; }
.panel-form { display: flex; flex-direction: column; gap: 8px; padding: 10px; border-radius: 10px; background: var(--neu-bg); box-shadow: inset 3px 3px 6px rgba(163, 177, 198, 0.4), inset -3px -3px 6px rgba(255, 255, 255, 0.75); }
.form-row { display: flex; align-items: center; gap: 8px; }
.form-label { flex-shrink: 0; width: 64px; font-size: 11px; color: #6b7488; }
.form-input {
  flex: 1; min-width: 0; padding: 6px 9px; font-size: 11.5px; color: #3a4256;
  border: none; border-radius: 7px; outline: none; background: #f7f9fc;
  box-shadow: inset 1px 1px 2px rgba(163, 177, 198, 0.35);
}
.form-input:focus { background: #fff; box-shadow: inset 0 0 0 1px #c7cff5; }
.form-textarea { min-height: 52px; resize: vertical; }
.form-switch { position: relative; width: 40px; height: 22px; flex-shrink: 0; }
.form-switch input { opacity: 0; width: 0; height: 0; }
.form-switch input:checked + .switch-slider {
  background: linear-gradient(145deg, #5b6ee1, #4f46e5);
}
.form-switch input:checked + .switch-slider::before { transform: translateX(18px); background: #fff; }
.form-submit { align-self: flex-end; flex: none; padding: 6px 16px; }
</style>
