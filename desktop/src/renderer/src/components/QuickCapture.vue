<template>
  <div class="qc-root" @keydown.esc="close">
    <div class="qc-head">
      <span class="qc-title">快速记录</span>
      <button class="qc-close" @click="close">✕</button>
    </div>
    <textarea
      ref="inputRef"
      v-model="text"
      class="qc-input"
      placeholder="记点什么…  Ctrl+Enter 保存到笔记，Ctrl+Shift+Enter 创建待办"
      @keydown="onKeydown"
    />
    <div class="qc-foot">
      <span class="qc-status" :class="{ error: !!error }">{{ status || error }}</span>
      <div class="qc-actions">
        <button class="qc-btn" @click="saveTodo" :disabled="busy || !text.trim()">创建待办</button>
        <button class="qc-btn primary" @click="saveNote" :disabled="busy || !text.trim()">
          {{ busy ? '保存中…' : '保存到笔记' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'

const text = ref('')
const status = ref('')
const error = ref('')
const busy = ref(false)
const inputRef = ref<HTMLTextAreaElement | null>(null)

function close() {
  window.mqbox.window.hide()
}

function noteTitle() {
  const first = text.value.trim().split('\n')[0] || '快速记录'
  return first.slice(0, 40)
}

function toProseMirror(value: string) {
  const paragraphs = value.split('\n').map(line => {
    const node: any = { type: 'paragraph' }
    if (line) node.content = [{ type: 'text', text: line }]
    return node
  })
  return JSON.stringify({ type: 'doc', content: paragraphs })
}

async function saveNote() {
  if (!text.value.trim() || busy.value) return
  busy.value = true
  error.value = ''
  try {
    await window.mqbox.api.post('/plugins/notes', {
      title: noteTitle(),
      content: toProseMirror(text.value.trim()),
    })
    status.value = '已保存到笔记'
    text.value = ''
    setTimeout(close, 500)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '保存失败'
  } finally {
    busy.value = false
  }
}

async function saveTodo() {
  if (!text.value.trim() || busy.value) return
  busy.value = true
  error.value = ''
  try {
    await window.mqbox.api.post('/plugins/todo/items', {
      title: noteTitle(),
      description: text.value.trim(),
      status: 'pending',
      priority: 0,
    })
    status.value = '已创建待办'
    text.value = ''
    setTimeout(close, 500)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '创建失败'
  } finally {
    busy.value = false
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    close()
  } else if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    if (event.shiftKey) saveTodo()
    else saveNote()
  }
}

onMounted(() => {
  nextTick(() => inputRef.value?.focus())
})
</script>

<style scoped>
.qc-root {
  box-sizing: border-box;
  width: 100vw;
  height: 100vh;
  background: #161922;
  color: #e6e9ef;
  border: 1px solid #2b3140;
  border-radius: 14px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.qc-head { display: flex; align-items: center; justify-content: space-between; -webkit-app-region: drag; }
.qc-title { font-size: 13px; font-weight: 600; letter-spacing: .5px; color: #aab3c5; }
.qc-close { -webkit-app-region: no-drag; border: none; background: transparent; color: #7d879c; cursor: pointer; font-size: 14px; }
.qc-input {
  flex: 1;
  resize: none;
  border: none;
  outline: none;
  background: #1d2130;
  color: #e6e9ef;
  border-radius: 10px;
  padding: 12px 14px;
  font-size: 14px;
  line-height: 1.7;
  font-family: inherit;
}
.qc-input::placeholder { color: #6b7488; }
.qc-foot { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.qc-status { font-size: 11px; color: #63d29a; }
.qc-status.error { color: #ff6b6b; }
.qc-actions { display: flex; gap: 8px; }
.qc-btn {
  border: 1px solid #343b4d;
  background: #232838;
  color: #cfd6e6;
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
}
.qc-btn:hover { background: #2b3144; }
.qc-btn.primary { background: #3b82f6; border-color: #3b82f6; color: #fff; }
.qc-btn.primary:hover { background: #2f6fd8; }
.qc-btn:disabled { opacity: .45; cursor: default; }
</style>
