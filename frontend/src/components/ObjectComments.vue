<template>
  <div class="object-comments">
    <div class="comments-head">
      <div class="comments-title">
        评论与材料
        <span v-if="items.length" class="count">{{ items.length }}</span>
      </div>
      <el-button link type="primary" size="small" :loading="loading" @click="load">刷新</el-button>
    </div>

    <div v-if="loading && !items.length" class="empty">加载中…</div>
    <div v-else-if="!items.length" class="empty">还没有评论，写下第一条备注或材料。</div>

    <div
      v-for="c in flat"
      :key="c.id"
      class="comment"
      :class="{ reply: c.depth > 0 }"
      :style="{ marginLeft: `${Math.min(c.depth, 4) * 16}px` }"
    >
      <div class="comment-head">
        <span class="author" :class="c.author">{{ c.author === 'assistant' ? '助手' : '我' }}</span>
        <span v-if="c.kind !== 'comment'" class="kind" :class="c.kind">{{ kindLabel(c.kind) }}</span>
        <span class="time">{{ fmt(c.created_at) }}</span>
        <span class="actions">
          <el-button link size="small" @click="startReply(c)">回复</el-button>
          <el-button link size="small" type="danger" @click="remove(c)">删除</el-button>
        </span>
      </div>
      <div v-if="c.title" class="comment-title">{{ c.title }}</div>
      <div class="comment-content" v-html="render(c.content)"></div>
      <div v-if="c.session_id" class="comment-source">来自对话 {{ c.session_id }}</div>

      <div v-if="replyTo === c.id" class="reply-box">
        <el-input
          v-model="replyContent"
          type="textarea"
          :rows="2"
          :placeholder="`回复 ${c.author === 'assistant' ? '助手' : '我'}`"
        />
        <div class="composer-actions">
          <el-button size="small" @click="cancelReply">取消</el-button>
          <el-button size="small" type="primary" :loading="submitting" :disabled="!replyContent.trim()" @click="submitReply(c)">
            回复
          </el-button>
        </div>
      </div>
    </div>

    <div class="composer">
      <el-input
        v-model="content"
        type="textarea"
        :rows="3"
        resize="vertical"
        placeholder="写备注、评论，或保存材料…"
      />
      <div class="composer-actions">
        <el-select v-model="kind" size="small" class="kind-select">
          <el-option label="评论" value="comment" />
          <el-option label="备注" value="note" />
        </el-select>
        <el-button type="primary" size="small" :loading="submitting" :disabled="!content.trim()" @click="submitRoot">
          发表
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import client from '@/api/client'
import { formatBackendDate } from '@/utils/date'

const props = defineProps<{
  type: string
  objectId: number
  title?: string
}>()
const emit = defineEmits<{ changed: [count: number] }>()

interface CommentItem {
  id: number
  parent_id: number | null
  root_id: number | null
  kind: string
  title?: string | null
  content: string
  author: string
  session_id?: string | null
  created_at?: string
}

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
const items = ref<CommentItem[]>([])
const loading = ref(false)
const submitting = ref(false)
const content = ref('')
const kind = ref<'comment' | 'note'>('comment')
const replyTo = ref<number | null>(null)
const replyContent = ref('')

const flat = computed(() => {
  const byParent = new Map<number | null, CommentItem[]>()
  const ids = new Set(items.value.map((item) => item.id))
  for (const item of items.value) {
    const parent = item.parent_id && ids.has(item.parent_id) ? item.parent_id : null
    if (!byParent.has(parent)) byParent.set(parent, [])
    byParent.get(parent)!.push(item)
  }
  const out: Array<CommentItem & { depth: number }> = []
  const walk = (parent: number | null, depth: number) => {
    for (const item of byParent.get(parent) || []) {
      out.push({ ...item, depth })
      walk(item.id, depth + 1)
    }
  }
  walk(null, 0)
  return out
})

function render(value: string) {
  return DOMPurify.sanitize(md.render(value || ''))
}

function fmt(value?: string) {
  return value ? formatBackendDate(value) : ''
}

function kindLabel(value: string) {
  return ({ comment: '评论', note: '备注', material: '材料', ai_summary: 'AI 摘要' } as Record<string, string>)[value] || value
}

async function load() {
  if (!props.type || !props.objectId) return
  loading.value = true
  try {
    const { data } = await client.get(`/objects/${props.type}/${props.objectId}/comments`)
    items.value = data.items || []
    emit('changed', items.value.length)
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

async function submitRoot() {
  const text = content.value.trim()
  if (!text) return
  submitting.value = true
  try {
    await client.post(`/objects/${props.type}/${props.objectId}/comments`, {
      kind: kind.value,
      content: text,
    })
    content.value = ''
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '发表失败')
  } finally {
    submitting.value = false
  }
}

function startReply(item: CommentItem) {
  replyTo.value = item.id
  replyContent.value = ''
}

function cancelReply() {
  replyTo.value = null
  replyContent.value = ''
}

async function submitReply(item: CommentItem) {
  const text = replyContent.value.trim()
  if (!text) return
  submitting.value = true
  try {
    await client.post(`/objects/${props.type}/${props.objectId}/comments`, {
      kind: 'comment',
      content: text,
      parent_id: item.id,
    })
    cancelReply()
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '回复失败')
  } finally {
    submitting.value = false
  }
}

async function remove(item: CommentItem) {
  try {
    await ElMessageBox.confirm('删除这条评论？回复会保留。', '删除评论', { type: 'warning' })
  } catch {
    return
  }
  try {
    await client.delete(`/objects/comments/${item.id}`)
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

watch(() => [props.type, props.objectId], load)
onMounted(load)
</script>

<style scoped>
.object-comments { display: flex; flex-direction: column; gap: 10px; }
.comments-head { display: flex; align-items: center; justify-content: space-between; }
.comments-title { font-size: 13px; font-weight: 600; color: #1f2937; display: flex; align-items: center; gap: 8px; }
.count { font-size: 11px; font-weight: 500; color: #4f46e5; background: #eef2ff; border-radius: 999px; padding: 1px 7px; }
.empty { padding: 18px 0; text-align: center; font-size: 12px; color: #a0a8b8; }
.comment {
  padding: 10px 12px; border-radius: 10px; background: #f8faff;
  border: 1px solid #edf1fa;
}
.comment.reply { background: #fff; border-left: 2px solid #dbe3f5; }
.comment-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.author { font-size: 11.5px; font-weight: 600; color: #4f46e5; }
.author.assistant { color: #7c3aed; }
.kind { font-size: 10.5px; padding: 1px 7px; border-radius: 999px; background: #eef2ff; color: #4f46e5; }
.kind.material { background: #ecfdf5; color: #059669; }
.kind.note { background: #fffbeb; color: #b45309; }
.time { font-size: 11px; color: #9aa3b2; }
.actions { margin-left: auto; display: flex; gap: 2px; }
.comment-title { margin-top: 6px; font-size: 13px; font-weight: 600; color: #111827; }
.comment-content { margin-top: 5px; font-size: 13px; line-height: 1.7; color: #334155; word-break: break-word; }
.comment-content :deep(p) { margin: 0 0 6px; }
.comment-content :deep(p:last-child) { margin-bottom: 0; }
.comment-content :deep(pre) { background: #0f172a; color: #e2e8f0; padding: 10px; border-radius: 8px; overflow: auto; }
.comment-source { margin-top: 6px; font-size: 10.5px; color: #a0a8b8; }
.reply-box { margin-top: 8px; display: flex; flex-direction: column; gap: 6px; }
.composer { border-top: 1px solid #eef1f7; padding-top: 10px; display: flex; flex-direction: column; gap: 8px; }
.composer-actions { display: flex; justify-content: flex-end; align-items: center; gap: 8px; }
.kind-select { width: 100px; }
</style>
