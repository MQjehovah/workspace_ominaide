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
      <button class="ai-toolbar-btn" :class="{ active: showAi }" @click.stop="triggerAi" title="AI 编辑 (Ctrl+Shift+I)">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 3c.5 0 1 .4 1 1 0 .5.4 1 1 1s1 .4 1 1c0 .5-.4 1-1 1s-1 .4-1 1c0 .5-.4 1-1 1s-1-.4-1-1c0-.5-.4-1-1-1s-1-.4-1-1c0-.5.4-1 1-1s1-.4 1-1c0-.5.4-1 1-1z"/><path d="M8 14c.5 0 1 .4 1 1 0 .5.4 1 1 1s1 .4 1 1-.4 1-1 1-1 .4-1 1-.4 1-1 1-1-.4-1-1-.4-1-1-1-1-.4-1-1 .4-1 1-1 1-.4 1-1 .4-1 1-1z"/><path d="M16 14c.5 0 1 .4 1 1 0 .5.4 1 1 1s1 .4 1 1-.4 1-1 1-1 .4-1 1-.4 1-1 1-1-.4-1-1-.4-1-1-1-1-.4-1-1 .4-1 1-1 1-.4 1-1 .4-1 1-1z"/></svg>
        AI
      </button>
    </div>

    <editor-content :editor="editor" class="editor-content" style="min-height:300px" />

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

const props = defineProps<{ modelValue: string }>()
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

async function serverUrl(): Promise<string> {
  try { return await (window as any).mqbox?.config?.get('serverUrl') || 'http://localhost:8000' } catch { return 'http://localhost:8000' }
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
      return
    }
  } catch {}
  aiPopupStyle.value = { top: '180px', left: '16px' }
}

function closeAi() {
  showAi.value = false
  aiInstruction.value = ''
  selectedText.value = ''
  editor.value?.chain().focus().run()
}

function runPreset(p: typeof presets[0]) {
  aiInstruction.value = p.prompt
  submitAi()
}

function log(level: string, msg: string) {
  try { (window as any).mqbox?.log?.write?.('notes', level, msg) } catch {}
  console.log(`[notes] ${msg}`)
}

async function submitAi() {
  const instruction = aiInstruction.value.trim()
  if (!instruction || aiLoading.value || !editor.value) return
  aiLoading.value = true
  const { from, to } = editor.value.state.selection
  const hadSelection = from !== to
  log('info', `AI submit: instruction="${instruction.slice(0, 40)}..." selection="${selectedText.value.slice(0, 30)}..."`)
  try {
    const result = await callAI(instruction, selectedText.value)
    log('info', `AI result length=${result.length} preview="${result.slice(0, 60)}"`)
    applyToEditor(result || '')
  } catch (e: any) {
    log('error', `AI error: ${e?.message || e}`)
    const errMsg = e?.message || String(e)
    if (hadSelection) {
      editor.value.chain().focus().deleteSelection().insertContent(`*[AI Error: ${errMsg}]*`).run()
    } else {
      editor.value.chain().focus().insertContent(`*[AI Error: ${errMsg}]*`).run()
    }
  } finally {
    aiLoading.value = false
    closeAi()
  }
}

async function callAI(instruction: string, selection: string): Promise<string> {
  loadAIConfig()
  const cfg = aiConfig
  log('info', `callAI mode=${cfg.mode} backend="${cfg.baseUrl}" model="${cfg.model}"`)
  let systemPrompt: string
  let userMsg: string

  if (selection) {
    systemPrompt = 'You are an AI writing assistant integrated into a text editor. The user has selected text and given an instruction. Modify ONLY the selected text according to the instruction. Return ONLY the modified text — no explanations, no markdown code blocks, no extra formatting. Preserve the original tone and style unless instructed otherwise.'
    userMsg = `SELECTED TEXT:\n${selection}\n\nINSTRUCTION: ${instruction}`
  } else {
    systemPrompt = 'You are an AI writing assistant. The user tells you what to write. Generate the content they asked for. Return ONLY the content — no explanations, no markdown code blocks, no meta commentary.'
    userMsg = instruction
  }

  if (cfg.mode === 'backend') {
    const tk = (await (window as any).mqbox?.config?.get('token')) || ''
    const su = await serverUrl()
    log('info', `fetch POST ${su}/api/chat`)
    const r = await fetch(`${su}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tk}` },
      body: JSON.stringify({ message: userMsg, history: [] }),
    })
    if (!r.ok) throw new Error(`API ${r.status} ${r.statusText}`)
    const data = await r.json()
    log('info', `backend reply type=${typeof data.reply} val="${String(data.reply).slice(0, 60)}"`)
    return (data.reply || data.response || '').trim()
  } else {
    const apiKey = cfg.apiKey || localStorage.getItem('ai_api_key') || ''
    const baseUrl = (cfg.baseUrl || 'https://api.openai.com/v1').replace(/\/+$/, '')
    const model = cfg.model || 'gpt-4o-mini'
    const r = await fetch(`${cfg.baseUrl}/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${cfg.apiKey}` },
      body: JSON.stringify({
        model: cfg.model,
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userMsg },
        ],
        temperature: 0.7,
      }),
    })
    if (!r.ok) throw new Error(`API ${r.status} ${r.statusText}`)
    const data = await r.json()
    if (data.error) throw new Error(data.error.message || JSON.stringify(data.error))
    return (data.choices?.[0]?.message?.content || '').trim()
  }
}

function applyToEditor(text: string) {
  if (!editor.value) { log('warn', 'applyToEditor: no editor'); return }
  if (!text) { log('warn', 'applyToEditor: empty text'); return }
  let clean = text.replace(/^```[\w]*\n?/, '').replace(/\n?```$/, '').trim()
  if (!clean) { log('warn', 'applyToEditor: clean is empty'); return }
  log('info', `applyToEditor: "${clean.slice(0, 80)}"`)

  const { state, view, schema } = editor.value
  const { from, to } = state.selection

  // Parse markdown using prosemirror-markdown (default schema)
  const mdDoc = defaultMarkdownParser.parse(clean)
  if (mdDoc && mdDoc.content.size > 0) {
    // Convert node names from ProseMirror convention to TipTap convention
    try {
      const mapped = mapNodeNames(mdDoc.toJSON())
      const parsed = schema.nodeFromJSON(mapped)
      if (parsed.content.size > 0) {
        log('info', `applyToEditor: nodeFromJSON ok, ${parsed.content.size} nodes`)
        const tr = state.tr.replaceWith(from, to, parsed.content)
        view.dispatch(tr)
        return
      }
    } catch (e: any) {
      log('warn', `applyToEditor: nodeFromJSON failed: ${e.message}`)
    }
  }

  // Fallback: HTML route
  const html = mdToHTML(clean)
  if (html) {
    log('info', `applyToEditor: html fallback "${html.slice(0, 100)}"`)
    const { from: f, to: t } = editor.value.state.selection
    editor.value.commands.insertContentAt({ from: f, to: t }, html)
  } else {
    log('warn', 'applyToEditor: plain text fallback')
    const { from: f, to: t } = editor.value.state.selection
    editor.value.commands.insertContentAt({ from: f, to: t }, clean)
  }
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
  content: '',
  extensions: editorExtensions,
  editorProps: {
    handlePaste: (view, event) => {
      const items = event.clipboardData?.items
      if (!items) return
      for (const item of Array.from(items)) {
        if (item.kind !== 'file') continue
        event.preventDefault()
        const file = item.getAsFile()
        if (!file) continue
        if (item.type.startsWith('image/')) uploadImage(file)
        else uploadFile(file)
        return true
      }
    },
    handleDrop: (view, event) => {
      const files = event.dataTransfer?.files
      if (!files || files.length === 0) return
      event.preventDefault()
      for (const file of Array.from(files)) {
        if (file.type.startsWith('image/')) uploadImage(file)
        else uploadFile(file)
      }
      return true
    },
  },
  onUpdate: ({ editor }) => {
    try {
      const md = defaultMarkdownSerializer.serialize(editor.state.doc)
      emit('update:modelValue', md || '')
    } catch {}
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

async function uploadFileViaApi(file: File): Promise<string | null> {
  try {
    const serverUrl = await (window as any).mqbox?.config?.get('serverUrl') || 'http://localhost:8000'
    const token = await (window as any).mqbox?.config?.get('token') || ''
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${serverUrl}/api/files/upload/note/direct`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    })
    const data = await res.json()
    if (!data?.object_key) return null
    return `${serverUrl}/api/files/note/${data.object_key}`
  } catch { return null }
}

async function uploadImage(file: File) {
  const url = await uploadFileViaApi(file)
  if (url) editor.value?.chain().focus().setImage({ src: url }).run()
}

async function uploadFile(file: File) {
  const url = await uploadFileViaApi(file)
  if (url) {
    editor.value?.chain().focus().insertContent(`📎 ${file.name}`).run()
  }
}

function setLink() {
  if (!editor.value) return
  const prev = editor.value.getAttributes('link').href || ''
  const url = window.prompt('输入链接 URL:', prev)
  if (url === null) return
  if (url === '') { editor.value.chain().focus().unsetLink().run(); return }
  editor.value.chain().focus().setLink({ href: url }).run()
}

function insertTable() {
  editor.value?.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()
}

onBeforeUnmount(() => editor.value?.destroy())
</script>

<style scoped>
.editor-wrapper {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 6px 12px;
  border-bottom: 1px solid #e2e8f0;
  background: #fafbfc;
  flex-wrap: wrap;
}
.toolbar button {
  padding: 4px 7px;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  font-size: 12px;
  background: transparent;
  color: #64748b;
  transition: all 0.12s;
}
.toolbar button:hover { background: #eef2f6; color: #334155; }
.toolbar button.active { background: #e0e7ff; color: #4f46e5; }
.sep { color: #cbd5e1; margin: 0 2px; font-size: 12px; user-select: none; }

.ai-toolbar-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-weight: 600;
}
.ai-toolbar-btn.active { background: #f3e8ff !important; color: #7c3aed !important; }

.editor-content {
  flex: 1;
  padding: 20px 24px;
  overflow-y: auto;
  outline: none;
  font-size: 15px;
  line-height: 1.75;
  color: #1e293b;
}
.editor-content :deep(.ProseMirror) {
  outline: none !important;
  border: none !important;
  box-shadow: none !important;
  min-height: 280px;
}
.editor-content :deep(.ProseMirror p.is-editor-empty:first-child::before) {
  color: #94a3b8;
  content: attr(data-placeholder);
  float: left;
  height: 0;
  pointer-events: none;
}
.editor-content :deep(h1) { font-size: 1.7em; font-weight: 700; margin: 0.5em 0 0.3em; color: #0f172a; }
.editor-content :deep(h2) { font-size: 1.4em; font-weight: 600; margin: 0.4em 0 0.25em; color: #1e293b; }
.editor-content :deep(h3) { font-size: 1.15em; font-weight: 600; margin: 0.35em 0 0.2em; color: #334155; }
.editor-content :deep(p) { margin: 0.35em 0; }
.editor-content :deep(ul), .editor-content :deep(ol) { padding-left: 1.6em; margin: 0.3em 0; }
.editor-content :deep(li) { margin: 0.15em 0; }
.editor-content :deep(blockquote) {
  border-left: 3px solid #a5b4fc;
  margin: 0.5em 0;
  padding: 0.3em 1em 0.3em 1.2em;
  color: #64748b;
  background: #f8fafc;
  border-radius: 0 6px 6px 0;
}
.editor-content :deep(a) { color: #4f46e5; text-decoration: underline; text-underline-offset: 2px; }
.editor-content :deep(img) { max-width: 100%; border-radius: 8px; margin: 0.5em 0; }
.editor-content :deep(code) {
  background: #f1f5f9;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.85em;
  color: #e11d48;
}
.editor-content :deep(pre) {
  background: #1e293b;
  color: #e2e8f0;
  padding: 14px 16px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.6;
  margin: 0.5em 0;
}
.editor-content :deep(pre code) { background: none; color: inherit; padding: 0; }
.editor-content :deep(table) { border-collapse: collapse; width: 100%; margin: 0.5em 0; font-size: 13px; }
.editor-content :deep(th), .editor-content :deep(td) { border: 1px solid #d0d5dd; padding: 8px 12px; text-align: left; min-width: 60px; }
.editor-content :deep(th) { background: #f8fafc; font-weight: 600; }
.editor-content :deep(td p) { margin: 0; }
.editor-content :deep(.selectedCell) { background: #eef2ff; }
.editor-content :deep(hr) { margin: 1em 0; border: none; border-top: 1px solid #e2e8f0; }

/* AI Popup */
.ai-overlay {
  position: fixed;
  inset: 0;
  z-index: 999;
  background: transparent;
}

.ai-popup {
  position: fixed;
  z-index: 1000;
  width: 340px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  box-shadow: 0 8px 30px rgba(0,0,0,0.12);
  overflow: hidden;
}

.ai-popup-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid #f1f5f9;
}
.ai-sel-hint { font-size: 11px; color: #94a3b8; }
.ai-popup-close { width: 22px; height: 22px; border: none; border-radius: 5px; background: transparent; color: #94a3b8; cursor: pointer; font-size: 13px; display: flex; align-items: center; justify-content: center; }
.ai-popup-close:hover { background: #f1f5f9; color: #475569; }

.ai-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 8px 14px;
  border-bottom: 1px solid #f1f5f9;
}
.ai-preset-btn {
  padding: 4px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: #fafbfc;
  color: #475569;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.12s;
  white-space: nowrap;
}
.ai-preset-btn:hover { border-color: #a5b4fc; background: #eef2ff; color: #4f46e5; }

.ai-popup-input-row {
  display: flex;
  gap: 6px;
  padding: 10px 14px;
}
.ai-popup-input {
  flex: 1;
  height: 36px;
  padding: 0 12px;
  border: 1px solid #d0d5dd;
  border-radius: 8px;
  font-size: 13px;
  outline: none;
  transition: border-color 0.12s;
}
.ai-popup-input:focus { border-color: #7c3aed; box-shadow: 0 0 0 2px rgba(124,58,237,0.12); }
.ai-popup-submit {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 8px;
  background: #7c3aed;
  color: #fff;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.12s;
}
.ai-popup-submit:hover { background: #6d28d9; }
.ai-popup-submit:disabled { opacity: 0.5; cursor: default; }

.ai-popup-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px 12px;
  font-size: 11px;
  color: #94a3b8;
}
.ai-loader {
  width: 14px;
  height: 14px;
  border: 2px solid #e2e8f0;
  border-top-color: #7c3aed;
  border-radius: 50%;
  animation: ai-spin 0.6s linear infinite;
}
@keyframes ai-spin { to { transform: rotate(360deg); } }
</style>
