<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'

interface ActionItem {
  key: string
  id: string
  title: string
  description?: string
  icon?: string
  pluginId: string
}

const text = ref('')
const actions = ref<ActionItem[]>([])
const selectedIndex = ref(0)
const running = ref('')
const message = ref('')
const error = ref('')
const cardRef = ref<HTMLElement | null>(null)

const preview = computed(() => {
  const t = text.value.replace(/\s+/g, ' ').trim()
  return t.length > 160 ? t.slice(0, 160) + '…' : t
})

function resizeToContent() {
  nextTick(() => {
    const el = cardRef.value
    if (!el) return
    const height = Math.ceil(el.getBoundingClientRect().height) + 12
    window.mqbox?.selection?.resize(height)
  })
}

async function run(action: ActionItem) {
  if (running.value) return
  running.value = action.key
  error.value = ''
  message.value = ''
  try {
    const result: any = await window.mqbox?.selection?.run(action.key)
    if (!result) {
      window.mqbox?.selection?.close()
      return
    }
    if (result.error) {
      error.value = String(result.error)
    } else if (result.message) {
      message.value = String(result.message)
    } else {
      window.mqbox?.selection?.close()
    }
  } catch (e: any) {
    error.value = e?.message || String(e)
  } finally {
    running.value = ''
    resizeToContent()
  }
}

function close() {
  window.mqbox?.selection?.close()
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.preventDefault()
    close()
  } else if (e.key === 'ArrowDown') {
    e.preventDefault()
    if (actions.value.length) selectedIndex.value = (selectedIndex.value + 1) % actions.value.length
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    if (actions.value.length) selectedIndex.value = (selectedIndex.value - 1 + actions.value.length) % actions.value.length
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const action = actions.value[selectedIndex.value]
    if (action) run(action)
  }
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  window.mqbox?.selection?.onInit((data: { text: string; actions: ActionItem[] }) => {
    text.value = data?.text || ''
    actions.value = data?.actions || []
    selectedIndex.value = 0
    message.value = ''
    error.value = ''
    resizeToContent()
  })
  // Ask once on load in case the init event fired before the listener attached.
  resizeToContent()
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="sel-root">
    <div ref="cardRef" class="sel-card">
      <div class="sel-head">
        <span class="sel-badge">划词</span>
        <span class="sel-preview">{{ preview || '未读取到文本' }}</span>
        <button class="sel-close" title="关闭 (Esc)" @click="close">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div v-if="actions.length" class="sel-actions">
        <button
          v-for="(action, idx) in actions"
          :key="action.key"
          class="sel-action"
          :class="{ active: idx === selectedIndex }"
          @mouseenter="selectedIndex = idx"
          @click="run(action)"
        >
          <span class="sel-icon">{{ action.icon || '⚡' }}</span>
          <span class="sel-texts">
            <span class="sel-title">{{ action.title }}</span>
            <span v-if="action.description" class="sel-desc">{{ action.description }}</span>
          </span>
          <span v-if="running === action.key" class="sel-spin"></span>
        </button>
      </div>
      <div v-else class="sel-empty">
        还没有插件注册划词动作
      </div>

      <div v-if="message" class="sel-msg">{{ message }}</div>
      <div v-if="error" class="sel-err">{{ error }}</div>

      <div class="sel-foot">
        <span>↑↓ 选择</span>
        <span>Enter 执行</span>
        <span>Esc 关闭</span>
      </div>
    </div>
  </div>
</template>

<style>
body, html { margin: 0; padding: 0; background: transparent !important; overflow: hidden; }
#app { background: transparent !important; }
</style>

<style scoped>
.sel-root {
  width: 100vw;
  padding: 6px;
  box-sizing: border-box;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif;
}
.sel-card {
  background: #ffffff;
  border-radius: 14px;
  box-shadow: 0 12px 32px rgba(20, 26, 45, 0.22), 0 2px 6px rgba(20, 26, 45, 0.12);
  border: 1px solid rgba(20, 26, 45, 0.06);
  overflow: hidden;
}
.sel-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px 8px;
  border-bottom: 1px solid #eef1f6;
}
.sel-badge {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  color: #4f46e5;
  background: #eef0ff;
  border-radius: 6px;
  padding: 2px 6px;
  letter-spacing: 0.4px;
}
.sel-preview {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: #4a5268;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sel-close {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 50%;
  background: #f1f3f8;
  color: #8a94a8;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.sel-close:hover { background: #e6e9f2; color: #3a4256; }
.sel-actions { padding: 6px; display: flex; flex-direction: column; gap: 2px; }
.sel-action {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  border: none;
  background: transparent;
  border-radius: 9px;
  padding: 8px 10px;
  cursor: pointer;
  text-align: left;
}
.sel-action.active { background: #f3f4ff; }
.sel-icon { font-size: 15px; width: 20px; text-align: center; flex-shrink: 0; }
.sel-texts { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.sel-title { font-size: 12.5px; font-weight: 600; color: #3a4256; }
.sel-desc { font-size: 10.5px; color: #8a94a8; }
.sel-spin {
  width: 13px; height: 13px; border-radius: 50%;
  border: 2px solid #dfe3ee; border-top-color: #4f46e5;
  animation: sel-spin 0.7s linear infinite;
  flex-shrink: 0;
}
@keyframes sel-spin { to { transform: rotate(360deg); } }
.sel-empty { padding: 14px 16px; font-size: 12px; color: #8a94a8; }
.sel-msg { padding: 8px 14px; font-size: 11.5px; color: #2b7a4b; background: #f1fbf4; border-top: 1px solid #e4f5ea; }
.sel-err { padding: 8px 14px; font-size: 11.5px; color: #b3261e; background: #fdf2f2; border-top: 1px solid #f8dede; }
.sel-foot {
  display: flex;
  gap: 12px;
  padding: 7px 14px 9px;
  font-size: 10px;
  color: #a3abbd;
  border-top: 1px solid #f3f5f9;
  background: #fafbfd;
}
</style>
