<template>
  <el-dialog
    :model-value="modelValue"
    width="min(560px, calc(100vw - 24px))"
    append-to-body
    class="notification-detail"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <template #header>
      <div class="detail-head">
        <span class="detail-title">{{ notification?.title || '通知' }}</span>
        <span class="detail-time">{{ fmt(notification?.created_at) }}</span>
      </div>
    </template>

    <div class="detail-body">{{ notification?.body || '这条通知没有正文。' }}</div>

    <template #footer>
      <div class="detail-actions">
        <el-button @click="emit('update:modelValue', false)">关闭</el-button>
        <el-button v-if="canOpen" type="primary" @click="open">打开相关页面</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatBackendDate } from '@/utils/date'

const props = defineProps<{
  modelValue: boolean
  notification: any
}>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  open: []
}>()

function fmt(value?: string) {
  return value ? formatBackendDate(value) : ''
}

const canOpen = computed(() => {
  const link = String(props.notification?.link || '')
  return !!link && link !== '/' && link !== '/notifications'
})

function open() {
  emit('open')
  emit('update:modelValue', false)
}
</script>

<style scoped>
.detail-head { display: flex; flex-direction: column; gap: 4px; padding-right: 24px; }
.detail-title { font-size: 16px; font-weight: 600; color: #111827; line-height: 1.45; }
.detail-time { font-size: 11.5px; color: #94a3b8; }
.detail-body {
  max-height: min(56vh, 460px);
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13.5px;
  line-height: 1.8;
  color: #334155;
  padding: 2px 2px 6px;
}
.detail-actions { display: flex; justify-content: flex-end; gap: 8px; }
</style>
