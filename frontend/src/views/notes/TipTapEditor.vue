<template>
  <div class="editor-wrapper" @click="onWrapperClick">
    <div class="toolbar" v-if="editor" @click.stop>
      <button @click="editor.chain().focus().toggleBold().run()" :class="{ active: editor.isActive('bold') }"><strong>B</strong></button>
      <button @click="editor.chain().focus().toggleItalic().run()" :class="{ active: editor.isActive('italic') }"><em>I</em></button>
      <button @click="editor.chain().focus().toggleUnderline().run()" :class="{ active: editor.isActive('underline') }"><u>U</u></button>
      <span class="sep">|</span>
      <button @click="editor.chain().focus().toggleHeading({ level: 1 }).run()" :class="{ active: editor.isActive('heading', { level: 1 }) }">H1</button>
      <button @click="editor.chain().focus().toggleHeading({ level: 2 }).run()" :class="{ active: editor.isActive('heading', { level: 2 }) }">H2</button>
      <button @click="editor.chain().focus().toggleHeading({ level: 3 }).run()" :class="{ active: editor.isActive('heading', { level: 3 }) }">H3</button>
      <span class="sep">|</span>
      <button @click="editor.chain().focus().toggleBulletList().run()" :class="{ active: editor.isActive('bulletList') }">≡</button>
      <button @click="editor.chain().focus().toggleOrderedList().run()" :class="{ active: editor.isActive('orderedList') }">#</button>
      <button @click="editor.chain().focus().toggleBlockquote().run()" :class="{ active: editor.isActive('blockquote') }">"</button>
      <span class="sep">|</span>
      <button @click="setLink" :class="{ active: editor.isActive('link') }">🔗</button>
      <span class="sep">|</span>
      <button @click="insertTable" title="插入表格">⊞</button>
      <template v-if="editor.isActive('table')">
        <button @click="editor.chain().focus().addColumnAfter().run()">＋列</button>
        <button @click="editor.chain().focus().addRowAfter().run()">＋行</button>
        <button @click="editor.chain().focus().deleteColumn().run()">－列</button>
        <button @click="editor.chain().focus().deleteRow().run()">－行</button>
        <button @click="editor.chain().focus().deleteTable().run()">✕</button>
      </template>

      <span class="sep">|</span>
      <button @click.stop="toggleFind" :class="{ active: findOpen }" title="查找替换">查找</button>
      <button @click.stop="exportMarkdown" title="导出 Markdown">导出</button>
      <button @click.stop="attachInputRef?.click()" title="插入附件">附件</button>

      <span class="sep">|</span>
      <button class="ai-toolbar-btn" :class="{ active: showAi }" @click.stop="triggerAi" title="AI 编辑 (Ctrl+Shift+I)">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 3c.5 0 1 .4 1 1 0 .5.4 1 1 1s1 .4 1 1c0 .5-.4 1-1 1s-1 .4-1 1c0 .5-.4 1-1 1s-1-.4-1-1c0-.5-.4-1-1-1s-1-.4-1-1c0-.5.4-1 1-1s1-.4 1-1c0-.5.4-1 1-1z"/><path d="M8 14c.5 0 1 .4 1 1 0 .5.4 1 1 1s1 .4 1 1-.4 1-1 1-1 .4-1 1-.4 1-1 1-1-.4-1-1-.4-1-1-1-1-.4-1-1 .4-1 1-1 1-.4 1-1 .4-1 1-1z"/><path d="M16 14c.5 0 1 .4 1 1 0 .5.4 1 1 1s1 .4 1 1-.4 1-1 1-1 .4-1 1-.4 1-1 1-1-.4-1-1-.4-1-1-1-1-.4-1-1 .4-1 1-1 1-.4 1-1 .4-1 1-1z"/></svg>
        AI
      </button>
    </div>

    <div v-if="findOpen" class="find-bar" @click.stop>
      <input ref="findInputRef" v-model="findQuery" class="find-input" placeholder="查找" @input="refreshMatches" @keydown.enter.prevent="findNext($event.shiftKey ? -1 : 1)" @keydown.esc.prevent="findOpen = false" />
      <input v-model="replaceQuery" class="find-input" placeholder="替换为" />
      <button @click="findNext(-1)">上一个</button>
      <button @click="findNext(1)">下一个</button>
      <button @click="replaceCurrent">替换</button>
      <button @click="replaceAll">全部替换</button>
      <span class="find-count">{{ findMatches.length ? `${findIndex + 1}/${findMatches.length}` : '0/0' }}</span>
      <button @click="findOpen = false">关闭</button>
    </div>

    <input ref="attachInputRef" type="file" style="display:none" @change="onAttachFile" />
    <editor-content :editor="editor" class="editor-content" style="min-height:300px" />
    <div class="editor-footer">
      <span>{{ charCount }} 字符 · {{ wordCount }} 词</span>
      <span v-if="saveState">{{ saveState }}</span>
    </div>

    <Teleport to="body">
      <div v-if="showAi" class="ai-overlay" @click="closeAi" @keydown.escape="closeAi"></div>
      <div v-if="showAi" ref="aiPopupRef" class="ai-popup" :style="aiPopupStyle" @click.stop>
        <div class="ai-popup-header">
          <span v-if="selectedText" class="ai-sel-hint">已选 {{ selectedText.length }} 字</span>
          <span v-else class="ai-sel-hint">光标处插入</span>
          <button class="ai-popup-close" @click="closeAi">✕</button>
        </div>

        <div class="ai-presets" v-if="!aiLoading">
          <button v-for="p in presets" :key="p.label" class="ai-preset-btn" @click="runPreset(p)">
            {{ p.label }}
          </button>
        </div>

        <div class="ai-popup-input-row">
          <input
            ref="aiInputRef"
            v-model="aiInstruction"
            class="ai-popup-input"
            :placeholder="selectedText ? '改写、翻译、润色…' : '写一段关于…'"
            @keydown.enter.prevent="submitAi"
            @keydown.escape="closeAi"
            :disabled="aiLoading"
          />
          <button class="ai-popup-submit" @click="submitAi" :disabled="aiLoading || !aiInstruction.trim()">
            {{ aiLoading ? '…' : '→' }}
          </button>
        </div>

        <div v-if="aiLoading" class="ai-popup-loading">
          <span class="ai-loader"></span>
          <span>AI 处理中…</span>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onBeforeUnmount, watch, nextTick } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import Link from '@tiptap/extension-link'
import Image from '@tiptap/extension-image'
import Placeholder from '@tiptap/extension-placeholder'
import { Table, TableRow, TableCell, TableHeader } from '@tiptap/extension-table'
import { renderToHTMLString } from '@tiptap/static-renderer/pm/html-string'
import { defaultMarkdownParser, defaultMarkdownSerializer } from 'prosemirror-markdown'
import client from '@/api/client'
import { apiUrl } from '@/api/base'

const props = defineProps<{ modelValue: string; title?: string; saveState?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const editorExtensions = [
  StarterKit.configure({ heading: { levels: [1, 2, 3] }, link: false, underline: false }),
  Underline,
  Link.configure({ openOnClick: false }),
  Image.configure({ inline: true }),
  Placeholder.configure({ placeholder: '开始写点什么...' }),
  Table.configure({ resizable: true }),
  TableRow,
  TableCell,
  TableHeader,
]

const findOpen = ref(false)
const findQuery = ref('')
const replaceQuery = ref('')
const findMatches = ref<{ from: number; to: number }[]>([])
const findIndex = ref(0)
const findInputRef = ref<HTMLInputElement | null>(null)
const attachInputRef = ref<HTMLInputElement | null>(null)
const charCount = ref(0)
const wordCount = ref(0)

const showAi = ref(false)
const aiInstruction = ref('')
const aiLoading = ref(false)
const selectedText = ref('')
const aiInputRef = ref<HTMLInputElement | null>(null)
const aiPopupRef = ref<HTMLDivElement | null>(null)
const aiPopupStyle = ref({ top: '0px', left: '0px' })
let aiConfig: any = null

const NODE_NAME_MAP: Record<string, string> = {
  horizontal_rule: 'horizontalRule',
  code_block: 'codeBlock',
  hard_break: 'hardBreak',
  bullet_list: 'bulletList',
  ordered_list: 'orderedList',
  list_item: 'listItem',
  table: 'table',
  table_cell: 'tableCell',
  table_row: 'tableRow',
  table_header: 'tableHeader',
}
const MARK_NAME_MAP: Record<string, string> = {
  strong: 'bold',
  em: 'italic',
}

function mapNodeNames(json: any): any {
  if (Array.isArray(json)) return json.map(mapNodeNames)
  if (json && typeof json === 'object') {
    const result: any = {}
    for (const key of Object.keys(json)) {
      if (key === 'type' && typeof json.type === 'string') {
        result.type = NODE_NAME_MAP[json.type] || json.type
      } else if (key === 'marks' && Array.isArray(json.marks)) {
        result.marks = json.marks.map((m: any) => {
          if (typeof m === 'string') return MARK_NAME_MAP[m] || m
          if (m && typeof m === 'object') return { ...m, type: MARK_NAME_MAP[m.type] || m.type }
          return m
        })
      } else {
        result[key] = mapNodeNames(json[key])
      }
    }
    return result
  }
  return json
}

const presets = [
  { label: '改写润色', prompt: 'Rewrite the following text to be more polished and natural. Keep the same meaning but improve the flow, word choice, and readability.' },
  { label: '翻译英文', prompt: 'Translate the following text into English.' },
  { label: '翻译中文', prompt: '将以下文本翻译成中文。' },
  { label: '概括要点', prompt: 'Summarize the following text into key points. Be concise.' },
  { label: '扩写内容', prompt: 'Expand on the following text. Add more detail, examples, and depth while keeping the same style.' },
  { label: '修正语法', prompt: 'Fix grammar, spelling, and punctuation issues in the following text. Keep the same meaning and style.' },
]

function loadAIConfig() {
  try {
    const raw = localStorage.getItem('ai_chat_config')
    if (raw) {
      aiConfig = JSON.parse(raw)
      return
    }
  } catch {}
  aiConfig = { mode: 'backend', apiKey: '', baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' }
}

function onWrapperClick() {
  if (!showAi.value) editor.value?.chain().focus().run()
}

function triggerAi() {
  if (!editor.value) return
  if (showAi.value) { closeAi(); return }
  loadAIConfig()
  const { from, to } = editor.value.state.selection
  if (from !== to) {
    selectedText.value = editor.value.state.doc.textBetween(from, to)
  } else {
    selectedText.value = ''
  }
  computePopupPosition()
  showAi.value = true
  aiInstruction.value = ''
  nextTick(() => aiInputRef.value?.focus())
}

function computePopupPosition() {
  if (!editor.value) return
  try {
    const coords = editor.value.view.coordsAtPos(editor.value.state.selection.from)
    if (coords) {
      const editorEl = editor.value.view.dom
      const editorRect = editorEl.getBoundingClientRect()
      aiPopupStyle.value = {
        top: `${Math.min(coords.bottom + 6, window.innerHeight - 180)}px`,
        left: `${Math.max(8, Math.min(coords.left, window.innerWidth - 360))}px`,
      }
    }
  } catch {}
}

function closeAi() {
  showAi.value = false
  editor.value?.chain().focus().run()
}

function getContent(): string {
  return defaultMarkdownSerializer.serialize(editor.value!.state.doc) || ''
}

function replaceContent(md: string) {
  if (!editor.value) return
  try {
    const doc = defaultMarkdownParser.parse(md)
    if (!doc) return
    const mapped = mapNodeNames(doc.toJSON())
    editor.value.commands.setContent({ content: [mapped] })
  } catch {}
}

async function submitAi() {
  if (!editor.value || !aiInstruction.value.trim()) return
  const text = selectedText.value || getContent()
  if (!text) return
  aiLoading.value = true
  try {
    const result = await callLLM(text, aiInstruction.value.trim(), aiConfig)
    if (result) {
      if (selectedText.value) {
        const { from, to } = editor.value.state.selection
        editor.value.chain().focus().deleteRange({ from, to }).insertContent(result).run()
      } else {
        replaceContent(result)
      }
      emit('update:modelValue', getContent())
      closeAi()
    }
  } catch (e: any) {
    log('error', e.message || 'AI 请求失败')
  }
  aiLoading.value = false
}

async function runPreset(preset: any) {
  if (!editor.value || !preset.prompt) return
  const text = selectedText.value || getContent()
  if (!text) return
  aiLoading.value = true
  try {
    const result = await callLLM(text, preset.prompt, aiConfig)
    if (result) {
      if (selectedText.value) {
        const { from, to } = editor.value.state.selection
        editor.value.chain().focus().deleteRange({ from, to }).insertContent(result).run()
      } else {
        replaceContent(result)
      }
      emit('update:modelValue', getContent())
      closeAi()
    }
  } catch (e: any) {
    log('error', e.message || 'AI 处理失败')
  }
  aiLoading.value = false
}

async function callLLM(content: string, instruction: string, cfg: any): Promise<string> {
  const system = 'You are a helpful writing assistant. Respond with ONLY the modified text, no explanations, no markdown formatting, no code blocks. Keep the same tone and style as the original unless instructed otherwise.'
  const userContent = `${instruction}\n\n---\n${content}`
  const messages = [
    { role: 'system', content: system },
    { role: 'user', content: userContent },
  ]
  if (cfg.mode === 'backend') {
    const res = await client.post('/chat', { message: userContent })
    return res.data?.reply || ''
  } else {
    const baseUrl = (cfg.baseUrl || 'https://api.openai.com/v1').replace(/\/+$/, '')
    const apiKey = cfg.apiKey || ''
    const res = await fetch(`${baseUrl}/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${apiKey}` },
      body: JSON.stringify({ model: cfg.model || 'gpt-4o-mini', messages, stream: false }),
    })
    const data = await res.json()
    return data?.choices?.[0]?.message?.content || ''
  }
}

function log(level: string, msg: string) {
  console[level === 'error' ? 'error' : 'log'](`[notes] ${msg}`)
}

function setLink() {
  if (!editor.value) return
  const prev = editor.value.getAttributes('link').href || ''
  const url = window.prompt('链接 URL:', prev)
  if (url === null) return
  if (url === '') { editor.value.chain().focus().unsetLink().run(); return }
  editor.value.chain().focus().setLink({ href: url }).run()
}

function insertTable() {
  editor.value?.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()
}

function toggleFind() {
  findOpen.value = !findOpen.value
  if (findOpen.value) {
    nextTick(() => {
      findInputRef.value?.focus()
      refreshMatches()
    })
  }
}

function updateStats() {
  const text = editor.value?.state.doc.textContent || ''
  charCount.value = text.replace(/\s/g, '').length
  const cjk = (text.match(/[\u4e00-\u9fff]/g) || []).length
  const latin = (text.match(/[A-Za-z0-9_]+/g) || []).length
  wordCount.value = cjk + latin
}

function collectMatches() {
  const ed = editor.value
  const q = findQuery.value.trim().toLowerCase()
  if (!ed || !q) return []
  const out: { from: number; to: number }[] = []
  ed.state.doc.descendants((node, pos) => {
    if (!node.isText || !node.text) return
    const text = node.text.toLowerCase()
    let idx = 0
    while ((idx = text.indexOf(q, idx)) !== -1) {
      out.push({ from: pos + idx, to: pos + idx + q.length })
      idx += q.length
    }
  })
  return out
}

function refreshMatches() {
  findMatches.value = collectMatches()
  if (findIndex.value >= findMatches.value.length) findIndex.value = 0
}

function findNext(dir = 1) {
  refreshMatches()
  if (!findMatches.value.length) return
  findIndex.value = (findIndex.value + dir + findMatches.value.length) % findMatches.value.length
  const m = findMatches.value[findIndex.value]
  editor.value?.chain().focus().setTextSelection({ from: m.from, to: m.to }).scrollIntoView().run()
}

function replaceCurrent() {
  if (!editor.value) return
  refreshMatches()
  if (!findMatches.value.length) return
  const m = findMatches.value[findIndex.value]
  editor.value.chain().focus().insertContentAt({ from: m.from, to: m.to }, replaceQuery.value).run()
  nextTick(refreshMatches)
}

function replaceAll() {
  if (!editor.value) return
  const matches = collectMatches()
  if (!matches.length) return
  const { state, view } = editor.value
  const tr = state.tr
  const replacement = replaceQuery.value
  for (let i = matches.length - 1; i >= 0; i--) {
    const m = matches[i]
    if (replacement) tr.replaceWith(m.from, m.to, state.schema.text(replacement))
    else tr.delete(m.from, m.to)
  }
  view.dispatch(tr)
  nextTick(refreshMatches)
}

function exportMarkdown() {
  if (!editor.value) return
  const md = defaultMarkdownSerializer.serialize(editor.value.state.doc)
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${(props.title || 'note').replace(/[\\\\/:*?"<>|]+/g, '_')}.md`
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}

function mdToHTML(md: string): string {
  try {
    const doc = defaultMarkdownParser.parse(md)
    if (!doc) return ''
    const mapped = mapNodeNames(doc.toJSON())
    return renderToHTMLString({ content: mapped, extensions: editorExtensions })
  } catch { return '' }
}

const editor = useEditor({
  extensions: editorExtensions,
  editorProps: {
    handlePaste,
    handleDrop,
  },
  onCreate: () => {
    updateStats()
  },
  onUpdate: ({ editor }) => {
    try {
      const md = defaultMarkdownSerializer.serialize(editor.state.doc)
      emit('update:modelValue', md || '')
    } catch {}
    updateStats()
    if (findOpen.value) refreshMatches()
  },
})

watch(() => props.modelValue, (val) => {
  if (!editor.value) return
  if (!val) {
    if (editor.value.state.doc.content.size > 1) editor.value.commands.setContent('')
    return
  }
  try {
    const currentMd = defaultMarkdownSerializer.serialize(editor.value.state.doc)
    if (currentMd === val) return
  } catch {}
  try {
    editor.value.commands.setContent(JSON.parse(val))
  } catch {
    const html = mdToHTML(val)
    if (html) editor.value.commands.setContent(html)
  }
}, { immediate: true })

async function uploadImage(file: File) {
  const url = await uploadFile(file)
  if (url) editor.value?.chain().focus().setImage({ src: url }).run()
}

async function insertAttachment(file: File) {
  const url = await uploadFile(file)
  if (!url) return
  editor.value?.chain().focus().insertContent({
    type: 'text',
    text: `📎 ${file.name}`,
    marks: [{ type: 'link', attrs: { href: url } }],
  }).run()
}

async function onAttachFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (file) await insertAttachment(file)
}

async function uploadFile(file: File): Promise<string | null> {
  try {
    const form = new FormData()
    form.append('file', file)
    const res = await client.post('/files/upload/note/direct', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const data = res.data
    if (!data?.object_key) return null
    return apiUrl(`/files/note/${data.object_key}`)
  } catch {
    return null
  }
}

function handlePaste(_view: any, event: ClipboardEvent) {
  const items = event.clipboardData?.items
  if (!items) return false
  for (const item of Array.from(items)) {
    if (item.type.startsWith('image/')) {
      const file = item.getAsFile()
      if (file) uploadImage(file)
      return true
    }
  }
  return false
}

function handleDrop(_view: any, event: DragEvent) {
  const files = event.dataTransfer?.files
  if (!files || files.length === 0) return false
  for (const file of Array.from(files)) {
    if (file.type.startsWith('image/')) uploadImage(file)
    else insertAttachment(file)
  }
  return true
}

onBeforeUnmount(() => {
  editor.value?.destroy()
})
</script>

<style scoped>
.editor-wrapper { border: 1px solid #dcdfe6; border-radius: 8px; overflow: hidden; position: relative; outline: none; }
.toolbar { display: flex; align-items: center; gap: 4px; padding: 8px 12px; border-bottom: 1px solid #dcdfe6; background: #fafafa; flex-wrap: wrap; }
.toolbar button { padding: 4px 8px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; background: transparent; color: #606266; }
.toolbar button:hover { background: #ecf5ff; color: #409EFF; }
.toolbar button.active { background: #409EFF; color: #fff; }
.toolbar .sep { color: #dcdfe6; margin: 0 4px; font-size: 12px; }
.find-bar { display: flex; align-items: center; gap: 6px; padding: 6px 12px; border-bottom: 1px solid #ebeef5; background: #f7f9fc; flex-wrap: wrap; font-size: 12px; }
.find-input { width: 150px; border: 1px solid #dcdfe6; border-radius: 4px; padding: 4px 6px; font-size: 12px; outline: none; }
.find-bar button { padding: 3px 7px; border: 1px solid #dcdfe6; background: #fff; border-radius: 4px; cursor: pointer; font-size: 12px; color: #606266; }
.find-bar button:hover { color: #409EFF; border-color: #409EFF; }
.find-count { color: #909399; min-width: 42px; text-align: center; }
.editor-footer { display: flex; justify-content: space-between; padding: 6px 12px; border-top: 1px solid #ebeef5; color: #909399; font-size: 12px; background: #fafafa; }
.editor-content { padding: 16px 20px; outline: none; font-size: 15px; line-height: 1.8; min-height: 300px; }
.editor-content :deep(.ProseMirror) { outline: none !important; border: none !important; }
.editor-content :deep(h1) { font-size: 1.8em; font-weight: 700; margin: 0.5em 0; }
.editor-content :deep(h2) { font-size: 1.4em; font-weight: 600; margin: 0.4em 0; }
.editor-content :deep(h3) { font-size: 1.15em; font-weight: 600; margin: 0.3em 0; }
.editor-content :deep(p) { margin: 0.3em 0; }
.editor-content :deep(ul), .editor-content :deep(ol) { padding-left: 1.5em; }
.editor-content :deep(blockquote) { border-left: 3px solid #409EFF; margin: 0.5em 0; padding: 0.3em 1em; color: #909399; }
.editor-content :deep(a) { color: #409EFF; text-decoration: underline; cursor: pointer; }
.editor-content :deep(img) { max-width: 100%; border-radius: 6px; margin: 0.5em 0; }
.editor-content :deep(table) { border-collapse: collapse; width: 100%; margin: 0.5em 0; }
.editor-content :deep(th), .editor-content :deep(td) { border: 1px solid #dcdfe6; padding: 8px 12px; text-align: left; }
.editor-content :deep(th) { background: #fafafa; font-weight: 600; }
.editor-content :deep(p.is-editor-empty:first-child::before) { content: attr(data-placeholder); float: left; color: #c0c4cc; pointer-events: none; height: 0; }
.ai-toolbar-btn { display: inline-flex; align-items: center; gap: 3px; }
.ai-toolbar-btn.active { background: #a855f7 !important; color: #fff !important; }
.ai-overlay { position: fixed; inset: 0; z-index: 999; }
.ai-popup { position: fixed; z-index: 1000; width: 340px; background: #fff; border-radius: 12px; box-shadow: 0 8px 32px rgba(0,0,0,0.15); border: 1px solid #e0e0e0; overflow: hidden; }
.ai-popup-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; border-bottom: 1px solid #f0f0f0; font-size: 12px; color: #666; }
.ai-popup-close { border: none; background: transparent; cursor: pointer; font-size: 14px; color: #999; padding: 2px 6px; border-radius: 4px; }
.ai-popup-close:hover { background: #f5f5f5; }
.ai-presets { display: flex; flex-wrap: wrap; gap: 4px; padding: 8px 10px; }
.ai-preset-btn { padding: 4px 10px; border: 1px solid #e0e0e0; border-radius: 14px; background: #fff; cursor: pointer; font-size: 11px; color: #666; white-space: nowrap; }
.ai-preset-btn:hover { border-color: #a855f7; color: #a855f7; background: #faf5ff; }
.ai-popup-input-row { display: flex; gap: 6px; padding: 6px 10px 10px; }
.ai-popup-input { flex: 1; padding: 8px 12px; border: 1px solid #e0e0e0; border-radius: 8px; font-size: 13px; outline: none; }
.ai-popup-input:focus { border-color: #a855f7; }
.ai-popup-submit { padding: 8px 14px; border: none; border-radius: 8px; background: #a855f7; color: #fff; cursor: pointer; font-size: 14px; }
.ai-popup-submit:disabled { opacity: 0.5; cursor: not-allowed; }
.ai-popup-loading { display: flex; align-items: center; gap: 8px; padding: 10px 14px; font-size: 12px; color: #999; }
.ai-loader { width: 14px; height: 14px; border: 2px solid #e0e0e0; border-top-color: #a855f7; border-radius: 50%; animation: ai-spin 0.6s linear infinite; }
@keyframes ai-spin { to { transform: rotate(360deg); } }
</style>
