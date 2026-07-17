import { Editor } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import Link from '@tiptap/extension-link'
import Placeholder from '@tiptap/extension-placeholder'
import TurndownService from 'turndown'
import { marked } from 'marked'

const turndown = new TurndownService({ headingStyle: 'atx' })
let editor = null
let saveTimer = null
let currentId = null
let apiBase = ''
let apiToken = ''

const toolbar = document.getElementById('toolbar')
const editorEl = document.getElementById('editor')
const statusEl = document.getElementById('status')
const saveBtn = document.getElementById('saveBtn')

// Listen for parent messages
window.addEventListener('message', (e) => {
  const msg = e.data
  if (msg.type === 'init') {
    apiBase = msg.apiBase
    apiToken = msg.apiToken
    currentId = msg.noteId
    const html = msg.content ? marked.parse(msg.content) : ''
    loadEditor(html)
  }
})

function loadEditor(html) {
  if (editor) editor.destroy()
  editor = new Editor({
    element: editorEl,
    content: html || '',
    extensions: [
      StarterKit.configure({ heading: { levels: [1, 2, 3] } }),
      Underline,
      Link.configure({ openOnClick: false }),
      Placeholder.configure({ placeholder: '开始写点什么...' }),
    ],
    onUpdate: () => {
      clearTimeout(saveTimer)
      statusEl.textContent = '未保存'
      saveTimer = setTimeout(saveNote, 2000)
    },
  })
  toolbar.style.display = 'flex'
  setupToolbar()
}

function setupToolbar() {
  document.querySelectorAll('.tt-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      if (!editor) return
      const cmd = btn.dataset.cmd
      if (cmd === 'bold') editor.chain().focus().toggleBold().run()
      else if (cmd === 'italic') editor.chain().focus().toggleItalic().run()
      else if (cmd === 'underline') editor.chain().focus().toggleUnderline().run()
      else if (cmd === 'h1') editor.chain().focus().toggleHeading({ level: 1 }).run()
      else if (cmd === 'h2') editor.chain().focus().toggleHeading({ level: 2 }).run()
      else if (cmd === 'h3') editor.chain().focus().toggleHeading({ level: 3 }).run()
      else if (cmd === 'bulletList') editor.chain().focus().toggleBulletList().run()
      else if (cmd === 'orderedList') editor.chain().focus().toggleOrderedList().run()
      else if (cmd === 'blockquote') editor.chain().focus().toggleBlockquote().run()
      updateActive()
    })
  })
}

function updateActive() {
  if (!editor) return
  document.querySelectorAll('.tt-btn').forEach(btn => {
    const c = btn.dataset.cmd
    let a = false
    if (c === 'bold') a = editor.isActive('bold')
    else if (c === 'italic') a = editor.isActive('italic')
    else if (c === 'underline') a = editor.isActive('underline')
    else if (c === 'h1') a = editor.isActive('heading', { level: 1 })
    else if (c === 'h2') a = editor.isActive('heading', { level: 2 })
    else if (c === 'h3') a = editor.isActive('heading', { level: 3 })
    else if (c === 'bulletList') a = editor.isActive('bulletList')
    else if (c === 'orderedList') a = editor.isActive('orderedList')
    else if (c === 'blockquote') a = editor.isActive('blockquote')
    btn.classList.toggle('active', a)
  })
}

async function saveNote() {
  if (!currentId || !editor) return
  const html = editor.getHTML()
  const md = turndown.turndown(html)
  statusEl.textContent = '保存中...'
  try {
    const res = await fetch(`${apiBase}/api/plugins/notes/${currentId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + apiToken },
      body: JSON.stringify({ content: md }),
    })
    if (res.ok) statusEl.textContent = '已保存'
    else statusEl.textContent = '保存失败'
  } catch (e) {
    statusEl.textContent = '保存失败'
  }
}

saveBtn.addEventListener('click', () => clearTimeout(saveTimer) || saveNote())
