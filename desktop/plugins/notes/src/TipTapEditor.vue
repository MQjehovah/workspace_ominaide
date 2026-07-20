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
import { renderToMarkdown } from '@tiptap/static-renderer/pm/markdown'
import { renderToHTMLString } from '@tiptap/static-renderer/pm/html-string'
import { defaultMarkdownParser } from 'prosemirror-markdown'

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const editorExtensions = [
  StarterKit.configure({ heading: { levels: [1, 2, 3] } }),
  Underline,
  Link.configure({ openOnClick: false }),
  Image.configure({ inline: true }),
  Placeholder.configure({ placeholder: '开始写点什么...' }),
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
    handlePaste: async (view, event) => {
      const items = event.clipboardData?.items
      if (!items) return false
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
      return false
    },
  },
  onUpdate: ({ editor }) => {
    const md = renderToMarkdown({ content: editor.getJSON(), extensions: editorExtensions })
    emit('update:modelValue', md)
  },
})

watch(() => props.modelValue, (val) => {
  if (!editor.value || !val) return
  const currentMd = renderToMarkdown({ content: editor.value.getJSON(), extensions: editorExtensions })
  if (currentMd === val) return
  const html = mdToHTML(val)
  if (html) editor.value.commands.setContent(html)
})

async function uploadImage(file: File) {
  try {
    const res = await window.mqbox?.api.post('/files/upload/note', {})
    if (!res?.upload_url || !res?.object_key) return
    await fetch(res.upload_url, { method: 'PUT', body: file })
    const serverUrl = await window.mqbox?.config.get('serverUrl') || 'http://localhost:8000'
    const imgUrl = `${serverUrl}/api/files/note/${res.object_key}`
    editor.value?.chain().focus().setImage({ src: imgUrl }).run()
  } catch {}
}

async function uploadFile(file: File) {
  try {
    const res = await window.mqbox?.api.post('/files/upload/note', {})
    if (!res?.upload_url || !res?.object_key) return
    await fetch(res.upload_url, { method: 'PUT', body: file })
    const serverUrl = await window.mqbox?.config.get('serverUrl') || 'http://localhost:8000'
    const fileUrl = `${serverUrl}/api/files/note/${res.object_key}`
    const linkHtml = `<a href="${fileUrl}" onclick="event.preventDefault();window.mqbox?.shell.openExternal('${fileUrl}')">📎 ${file.name}</a>`
    editor.value?.chain().focus().insertContent(linkHtml).run()
  } catch {}
}

function setLink() {
  if (!editor.value) return
  const prev = editor.value.getAttributes('link').href || ''
  const url = window.prompt('输入链接 URL:', prev)
  if (url === null) return
  if (url === '') { editor.value.chain().focus().unsetLink().run(); return }
  editor.value.chain().focus().setLink({ href: url }).run()
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
</style>
