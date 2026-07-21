<template>
  <div class="editor-wrapper" @click="focus">
    <div class="toolbar" v-if="editor">
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
        <button @click="editor.chain().focus().addColumnAfter().run()" title="插入列">＋列</button>
        <button @click="editor.chain().focus().addRowAfter().run()" title="插入行">＋行</button>
        <button @click="editor.chain().focus().deleteColumn().run()" title="删除列">－列</button>
        <button @click="editor.chain().focus().deleteRow().run()" title="删除行">－行</button>
        <button @click="editor.chain().focus().deleteTable().run()" title="删除表格">✕</button>
      </template>
    </div>
    <editor-content :editor="editor" class="editor-content" style="min-height:300px" />
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, watch } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import Link from '@tiptap/extension-link'
import Image from '@tiptap/extension-image'
import Placeholder from '@tiptap/extension-placeholder'
import { Table, TableRow, TableCell, TableHeader } from '@tiptap/extension-table'
import { renderToHTMLString } from '@tiptap/static-renderer/pm/html-string'
import { defaultMarkdownParser } from 'prosemirror-markdown'

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

function mdToHTML(md: string): string {
  try {
    const doc = defaultMarkdownParser.parse(md)
    if (!doc) return ''
    return renderToHTMLString({ content: doc.toJSON(), extensions: editorExtensions })
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
        if (item.type.startsWith('image/')) {
          uploadImage(file)
        } else {
          uploadFile(file)
        }
        return true
      }
    },
    handleDrop: (view, event) => {
      const files = event.dataTransfer?.files
      if (!files || files.length === 0) return
      event.preventDefault()
      for (const file of Array.from(files)) {
        if (file.type.startsWith('image/')) {
          uploadImage(file)
        } else {
          uploadFile(file)
        }
      }
      return true
    },
  },
  onUpdate: ({ editor }) => {
    emit('update:modelValue', JSON.stringify(editor.getJSON()))
  },
})

watch(() => props.modelValue, (val) => {
  if (!editor.value || !val) return
  const currentJson = JSON.stringify(editor.value.getJSON())
  if (currentJson === val) return
  try {
    editor.value.commands.setContent(JSON.parse(val))
  } catch {
    const html = mdToHTML(val)
    if (html) editor.value.commands.setContent(html)
  }
})

async function uploadFileViaApi(file: File, isImage: boolean): Promise<string | null> {
  try {
    const serverUrl = await window.mqbox?.config.get('serverUrl') || 'http://localhost:8000'
    const token = await window.mqbox?.config.get('token') || ''
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
  const url = await uploadFileViaApi(file, true)
  if (url) editor.value?.chain().focus().setImage({ src: url }).run()
}

async function uploadFile(file: File) {
  const fileUrl = await uploadFileViaApi(file, false)
  if (fileUrl) {
    const linkHtml = `<a href="${fileUrl}">📎 ${file.name}</a>`
    editor.value?.chain().focus().insertContent(linkHtml).run()
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

function focus() { editor.value?.chain().focus().run() }

onBeforeUnmount(() => editor.value?.destroy())
</script>

<style scoped>
.editor-wrapper { border:1px solid #e0e0e0; border-radius:8px; overflow:hidden; display:flex; flex-direction:column; height:100%; }
.toolbar { display:flex; align-items:center; gap:4px; padding:6px 12px; border-bottom:1px solid #e0e0e0; background:#fafafa; flex-wrap:wrap; }
.toolbar button { padding:3px 8px; border:none; border-radius:4px; cursor:pointer; font-size:12px; background:transparent; color:#666; }
.toolbar button:hover { background:#ecf5ff; color:#409EFF; }
.toolbar button.active { background:#409EFF; color:#fff; }
.sep { color:#e0e0e0; margin:0 4px; font-size:12px; }
.editor-content { flex:1; padding:16px 20px; overflow-y:auto; outline:none; font-size:14px; line-height:1.8; }
.editor-content :deep(.ProseMirror) { outline:none !important; border:none !important; box-shadow:none !important; }
.editor-content :deep(h1) { font-size:1.6em; font-weight:700; margin:0.4em 0; }
.editor-content :deep(h2) { font-size:1.3em; font-weight:600; margin:0.3em 0; }
.editor-content :deep(h3) { font-size:1.1em; font-weight:600; margin:0.3em 0; }
.editor-content :deep(p) { margin:0.3em 0; }
.editor-content :deep(ul), .editor-content :deep(ol) { padding-left:1.5em; }
.editor-content :deep(blockquote) { border-left:3px solid #409EFF; margin:0.5em 0; padding:0.3em 1em; color:#909399; }
.editor-content :deep(a) { color:#409EFF; text-decoration:underline; }
.editor-content :deep(img) { max-width:100%; border-radius:6px; margin:0.5em 0; }

.editor-content :deep(table) { border-collapse:collapse; width:100%; margin:0.5em 0; font-size:13px; }
.editor-content :deep(th), .editor-content :deep(td) { border:1px solid #d0d0d0; padding:6px 10px; text-align:left; min-width:60px; }
.editor-content :deep(th) { background:#f5f5f5; font-weight:600; }
.editor-content :deep(td p) { margin:0; }
.editor-content :deep(.selectedCell) { background:#ecf5ff; }
</style>
