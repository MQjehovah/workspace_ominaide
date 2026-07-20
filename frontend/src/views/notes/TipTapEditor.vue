<template>
  <div class="editor-wrapper" @click="focus">
    <div v-if="!readonly" class="toolbar">
      <button @click="toggleBold" :class="{ active: editor?.isActive('bold') }" title="加粗"><strong>B</strong></button>
      <button @click="toggleItalic" :class="{ active: editor?.isActive('italic') }" title="斜体"><em>I</em></button>
      <button @click="toggleUnderline" :class="{ active: editor?.isActive('underline') }" title="下划线"><u>U</u></button>
      <span class="sep">|</span>
      <button @click="toggleHeading(1)" :class="{ active: editor?.isActive('heading', { level: 1 }) }" title="标题 1">H1</button>
      <button @click="toggleHeading(2)" :class="{ active: editor?.isActive('heading', { level: 2 }) }" title="标题 2">H2</button>
      <button @click="toggleHeading(3)" :class="{ active: editor?.isActive('heading', { level: 3 }) }" title="标题 3">H3</button>
      <span class="sep">|</span>
      <button @click="toggleBulletList" :class="{ active: editor?.isActive('bulletList') }" title="无序列表">≡</button>
      <button @click="toggleOrderedList" :class="{ active: editor?.isActive('orderedList') }" title="有序列表">#</button>
      <button @click="toggleBlockquote" :class="{ active: editor?.isActive('blockquote') }" title="引用">"</button>
      <span class="sep">|</span>
      <button @click="setLink" :class="{ active: editor?.isActive('link') }" title="链接">🔗</button>
      <button @click="addImage" title="图片">🖼</button>
    </div>
    <editor-content :editor="editor" class="editor-content" :style="{ minHeight: minHeight }" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, watch } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import Link from '@tiptap/extension-link'
import Image from '@tiptap/extension-image'
import Placeholder from '@tiptap/extension-placeholder'

const props = defineProps<{
  modelValue: string
  readonly?: boolean
  placeholder?: string
  minHeight?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const editor = useEditor({
  content: props.modelValue,
  editable: !props.readonly,
  extensions: [
    StarterKit.configure({ heading: { levels: [1, 2, 3] }, link: false, underline: false }),
    Underline,
    Link.configure({ openOnClick: false }),
    Image.configure({ inline: true }),
    Placeholder.configure({ placeholder: props.placeholder || '开始写点什么...' }),
  ],
  onUpdate: ({ editor }) => {
    emit('update:modelValue', editor.getHTML())
  },
})

watch(() => props.modelValue, (val) => {
  if (editor.value && val !== editor.value.getHTML()) {
    editor.value.commands.setContent(val)
  }
})

watch(() => props.readonly, (val) => {
  if (editor.value) editor.value.setEditable(!val)
})

function toggleBold() { editor.value?.chain().focus().toggleBold().run() }
function toggleItalic() { editor.value?.chain().focus().toggleItalic().run() }
function toggleUnderline() { editor.value?.chain().focus().toggleUnderline().run() }
function toggleHeading(level: 1 | 2 | 3) { editor.value?.chain().focus().toggleHeading({ level }).run() }
function toggleBulletList() { editor.value?.chain().focus().toggleBulletList().run() }
function toggleOrderedList() { editor.value?.chain().focus().toggleOrderedList().run() }
function toggleBlockquote() { editor.value?.chain().focus().toggleBlockquote().run() }

function setLink() {
  if (!editor.value) return
  const prev = editor.value.getAttributes('link').href || ''
  const url = window.prompt('输入链接 URL:', prev)
  if (url === null) return
  if (url === '') { editor.value.chain().focus().unsetLink().run(); return }
  editor.value.chain().focus().setLink({ href: url }).run()
}

function addImage() {
  const url = window.prompt('输入图片 URL:')
  if (url) editor.value?.chain().focus().setImage({ src: url }).run()
}

function focus() { editor.value?.chain().focus().run() }

onBeforeUnmount(() => editor.value?.destroy())
</script>

<style scoped>
.editor-wrapper { border: 1px solid #dcdfe6; border-radius: 8px; overflow: hidden; }
.toolbar { display: flex; align-items: center; gap: 4px; padding: 8px 12px; border-bottom: 1px solid #dcdfe6; background: #fafafa; flex-wrap: wrap; }
.toolbar button { padding: 4px 8px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; background: transparent; color: #606266; }
.toolbar button:hover { background: #ecf5ff; color: #409EFF; }
.toolbar button.active { background: #409EFF; color: #fff; }
.toolbar .sep { color: #dcdfe6; margin: 0 4px; font-size: 12px; }
.editor-content { padding: 16px 20px; outline: none; font-size: 15px; line-height: 1.8; }
.editor-content :deep(h1) { font-size: 1.8em; font-weight: 700; margin: 0.5em 0; }
.editor-content :deep(h2) { font-size: 1.4em; font-weight: 600; margin: 0.4em 0; }
.editor-content :deep(h3) { font-size: 1.15em; font-weight: 600; margin: 0.3em 0; }
.editor-content :deep(p) { margin: 0.3em 0; }
.editor-content :deep(ul), .editor-content :deep(ol) { padding-left: 1.5em; }
.editor-content :deep(blockquote) { border-left: 3px solid #409EFF; margin: 0.5em 0; padding: 0.3em 1em; color: #909399; }
.editor-content :deep(a) { color: #409EFF; text-decoration: underline; cursor: pointer; }
.editor-content :deep(img) { max-width: 100%; border-radius: 6px; margin: 0.5em 0; }
.editor-content :deep(p.is-editor-empty:first-child::before) { content: attr(data-placeholder); float: left; color: #c0c4cc; pointer-events: none; height: 0; }
</style>
