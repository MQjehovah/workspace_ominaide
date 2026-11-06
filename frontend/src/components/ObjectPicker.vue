<template>
  <el-dialog
    :model-value="modelValue"
    title="引用业务对象"
    width="min(680px, calc(100vw - 24px))"
    append-to-body
    @update:model-value="(value: boolean) => emit('update:modelValue', value)"
    @open="load"
  >
    <div class="picker-search">
      <el-input
        v-model="query"
        placeholder="搜索日程、邮件、资讯、笔记、待办、文件、项目"
        clearable
        :prefix-icon="Search"
        @keyup.enter="load"
        @clear="load"
      />
      <el-button type="primary" :loading="loading" @click="load">搜索</el-button>
    </div>

    <div class="type-row">
      <button
        v-for="item in typeOptions"
        :key="item.value"
        class="type-pill"
        :class="{ active: activeType === item.value }"
        @click="activeType = item.value; load()"
      >
        {{ item.label }}
      </button>
    </div>

    <div v-loading="loading" class="picker-results">
      <div v-if="!loading && !items.length" class="picker-empty">没有找到匹配对象</div>
      <button v-for="item in items" :key="`${item.type}:${item.id}`" class="object-row" @click="choose(item)">
        <span class="object-badge">{{ item.source_label || typeLabel(item.type) }}</span>
        <span class="object-main">
          <span class="object-title">{{ item.title }}</span>
          <span class="object-sub">{{ item.subtitle }}</span>
        </span>
        <span class="object-action">引用</span>
      </button>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import client from '@/api/client'

defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  select: [item: any]
}>()

const query = ref('')
const activeType = ref('')
const loading = ref(false)
const items = ref<any[]>([])

const typeOptions = [
  { label: '全部', value: '' },
  { label: '日程', value: 'schedule_event' },
  { label: '邮件', value: 'mail_message' },
  { label: '资讯', value: 'rss_entry' },
  { label: '笔记', value: 'note' },
  { label: '待办', value: 'todo' },
  { label: '文件', value: 'file' },
  { label: '项目', value: 'project' },
]

function typeLabel(type: string) {
  return typeOptions.find((item) => item.value === type)?.label || type
}

async function load() {
  loading.value = true
  try {
    const { data } = await client.get('/objects/search', {
      params: {
        q: query.value.trim(),
        types: activeType.value || undefined,
        limit: 30,
      },
    })
    items.value = data.items || []
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

function choose(item: any) {
  emit('select', item)
  emit('update:modelValue', false)
}

onMounted(load)
</script>

<style scoped>
.picker-search { display: flex; gap: 8px; }
.type-row { display: flex; gap: 6px; flex-wrap: wrap; margin: 12px 0; }
.type-pill {
  border: 1px solid #e2e8f0; background: #fff; color: #64748b;
  border-radius: 999px; padding: 4px 12px; font-size: 12px; cursor: pointer;
}
.type-pill.active { border-color: #c7d2fe; background: #eef2ff; color: #4f46e5; font-weight: 600; }
.picker-results { max-height: 46vh; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; }
.picker-empty { padding: 36px 0; text-align: center; color: #a0a8b8; font-size: 13px; }
.object-row {
  display: flex; align-items: center; gap: 10px; width: 100%; text-align: left;
  border: 1px solid #eef1f7; background: #fbfcff; border-radius: 10px;
  padding: 9px 12px; cursor: pointer; transition: border-color .15s, background .15s;
}
.object-row:hover { border-color: #c7d2fe; background: #f7f9ff; }
.object-badge {
  flex-shrink: 0; font-size: 10.5px; color: #4f46e5; background: #eef2ff;
  border-radius: 999px; padding: 2px 8px;
}
.object-main { min-width: 0; display: flex; flex-direction: column; gap: 2px; flex: 1; }
.object-title { font-size: 13px; color: #1f2937; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.object-sub { font-size: 11px; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.object-action { font-size: 11.5px; color: #4f46e5; flex-shrink: 0; }
</style>
