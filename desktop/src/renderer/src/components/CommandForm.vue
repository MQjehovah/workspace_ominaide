<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'

interface Field {
  name: string
  label?: string
  type?: 'text' | 'textarea' | 'number' | 'select' | 'switch'
  placeholder?: string
  required?: boolean
  default?: string | number | boolean
  options?: Array<{ label: string; value: string | number | boolean }>
}

const title = ref('输入参数')
const fields = ref<Field[]>([])
const values = reactive<Record<string, any>>({})
const error = ref('')
const cardRef = ref<HTMLElement | null>(null)

function resizeToContent() {
  nextTick(() => {
    const el = cardRef.value
    if (!el) return
    window.mqbox?.commandForm?.resize(Math.ceil(el.getBoundingClientRect().height) + 4)
  })
}

function init(data: any) {
  title.value = data?.title || '输入参数'
  fields.value = Array.isArray(data?.arguments) ? data.arguments : []
  for (const key of Object.keys(values)) delete values[key]
  for (const field of fields.value) {
    if (data?.initial && data.initial[field.name] !== undefined) values[field.name] = data.initial[field.name]
    else if (field.default !== undefined) values[field.name] = field.default
    else if (field.type === 'switch') values[field.name] = false
    else if (field.type === 'number') values[field.name] = ''
    else values[field.name] = ''
  }
  error.value = ''
  resizeToContent()
  nextTick(() => (document.querySelector('.cf-input') as HTMLInputElement | null)?.focus())
}

function submit() {
  for (const field of fields.value) {
    if (!field.required) continue
    const value = values[field.name]
    if (value === undefined || value === null || String(value).trim() === '') {
      error.value = `请填写「${field.label || field.name}」`
      return
    }
  }
  const out: Record<string, any> = {}
  for (const field of fields.value) {
    const value = values[field.name]
    out[field.name] = field.type === 'number' && value !== '' ? Number(value) : value
  }
  window.mqbox?.commandForm?.submit(out)
}

function cancel() {
  window.mqbox?.commandForm?.cancel()
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.preventDefault()
    cancel()
  }
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  window.mqbox?.commandForm?.onInit(init)
})

onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="cf-root">
    <div ref="cardRef" class="cf-card">
      <div class="cf-head">
        <span class="cf-title">{{ title }}</span>
        <button class="cf-close" title="取消 (Esc)" @click="cancel">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      <form class="cf-body" @submit.prevent="submit">
        <div v-for="field in fields" :key="field.name" class="cf-row">
          <label class="cf-label">
            {{ field.label || field.name }}
            <span v-if="field.required" class="cf-required">*</span>
          </label>
          <textarea
            v-if="field.type === 'textarea'"
            v-model="values[field.name]"
            class="cf-input cf-textarea"
            :placeholder="field.placeholder"
          ></textarea>
          <select
            v-else-if="field.type === 'select'"
            v-model="values[field.name]"
            class="cf-input"
          >
            <option v-for="opt in field.options || []" :key="String(opt.value)" :value="opt.value">{{ opt.label }}</option>
          </select>
          <label v-else-if="field.type === 'switch'" class="cf-switch">
            <input v-model="values[field.name]" type="checkbox" />
            <span class="cf-switch-slider"></span>
          </label>
          <input
            v-else
            v-model="values[field.name]"
            class="cf-input"
            :type="field.type === 'number' ? 'number' : 'text'"
            :placeholder="field.placeholder"
          />
        </div>

        <div v-if="error" class="cf-error">{{ error }}</div>

        <div class="cf-footer">
          <button type="button" class="cf-btn" @click="cancel">取消</button>
          <button type="submit" class="cf-btn primary">执行</button>
        </div>
      </form>
    </div>
  </div>
</template>

<style>
body, html { margin: 0; padding: 0; background: #ffffff !important; overflow: hidden; }
#app { background: #ffffff !important; }
</style>

<style scoped>
.cf-root { width: 100vw; height: 100vh; padding: 8px; box-sizing: border-box; background: #fff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif; }
.cf-card { height: 100%; display: flex; flex-direction: column; border-radius: 12px; border: 1px solid #e9ecf2; overflow: hidden; }
.cf-head { display: flex; align-items: center; gap: 8px; padding: 12px 16px; border-bottom: 1px solid #eef1f6; -webkit-app-region: drag; }
.cf-title { flex: 1; font-size: 13px; font-weight: 600; color: #2f3542; }
.cf-close { width: 22px; height: 22px; border: none; border-radius: 50%; background: #f1f3f8; color: #8a94a8; cursor: pointer; display: flex; align-items: center; justify-content: center; -webkit-app-region: no-drag; }
.cf-close:hover { background: #e6e9f2; color: #3a4256; }
.cf-body { padding: 14px 16px 16px; overflow-y: auto; }
.cf-row { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.cf-label { font-size: 12px; color: #5b6478; }
.cf-required { color: #d32f2f; margin-left: 2px; }
.cf-input { width: 100%; box-sizing: border-box; height: 34px; border: 1px solid #dde1ea; border-radius: 7px; padding: 0 10px; font-size: 12.5px; color: #2f3542; outline: none; background: #fbfcfe; }
.cf-input:focus { border-color: #7c8cf0; background: #fff; }
.cf-textarea { height: 84px; padding: 8px 10px; resize: vertical; }
.cf-switch { position: relative; width: 40px; height: 22px; }
.cf-switch input { opacity: 0; width: 0; height: 0; }
.cf-switch-slider { position: absolute; inset: 0; border-radius: 11px; background: #d8dce6; cursor: pointer; transition: background 0.2s; }
.cf-switch-slider::before { content: ''; position: absolute; left: 3px; top: 3px; width: 16px; height: 16px; border-radius: 8px; background: #fff; transition: transform 0.2s; box-shadow: 1px 1px 3px rgba(0,0,0,0.15); }
.cf-switch input:checked + .cf-switch-slider { background: #5b6ee1; }
.cf-switch input:checked + .cf-switch-slider::before { transform: translateX(18px); }
.cf-error { color: #c62828; font-size: 11.5px; margin: 2px 0 10px; }
.cf-footer { display: flex; justify-content: flex-end; gap: 8px; padding-top: 4px; }
.cf-btn { border: 1px solid #e0e4ec; background: #fff; color: #5b6478; border-radius: 7px; padding: 7px 16px; font-size: 12.5px; cursor: pointer; }
.cf-btn:hover { border-color: #b9c3d6; color: #2f3542; }
.cf-btn.primary { background: #5b6ee1; border-color: #5b6ee1; color: #fff; }
.cf-btn.primary:hover { background: #4f5fd6; }
</style>
