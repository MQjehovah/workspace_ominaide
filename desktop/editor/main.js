import { Editor } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import Link from '@tiptap/extension-link'
import Image from '@tiptap/extension-image'
import Placeholder from '@tiptap/extension-placeholder'
import TurndownService from 'turndown'
import { marked } from 'marked'

const turndown = new TurndownService({ headingStyle: 'atx' })

window.EditorAPI = {
  _editor: null,
  _saveTimer: null,
  _currentId: null,
  _token: '',
  _baseUrl: '',
  _onSave: null,

  init(el, content, noteId, baseUrl, token) {
    if (this._editor) this._editor.destroy()
    this._currentId = noteId
    this._baseUrl = baseUrl
    this._token = token

    const html = content ? marked.parse(content) : ''
    this._editor = new Editor({
      element: el,
      content: html || '',
      extensions: [
        StarterKit.configure({ heading: { levels: [1, 2, 3] } }),
        Underline,
        Image.configure({ inline: true }),
        Link.configure({ openOnClick: false }),
        Placeholder.configure({ placeholder: '开始写点什么...' }),
      ],
      editorProps: {
        handlePaste: (view, event) => {
          const items = event.clipboardData?.items
          if (items) {
            for (const item of items) {
              if (item.type.startsWith('image/')) {
                event.preventDefault()
                const file = item.getAsFile()
                if (file) this._uploadImage(file)
                return true
              }
            }
          }
          return false
        },
      },
      onUpdate: () => {
        clearTimeout(this._saveTimer)
        this._saveTimer = setTimeout(() => this.save(), 2000)
      },
    })
    this._setupToolbar()
  },

  _setupToolbar() {
    document.querySelectorAll('.tt-btn').forEach(btn => {
      btn.onclick = () => {
        const ed = this._editor
        if (!ed) return
        const cmd = btn.dataset.cmd
        if (cmd === 'bold') ed.chain().focus().toggleBold().run()
        else if (cmd === 'italic') ed.chain().focus().toggleItalic().run()
        else if (cmd === 'underline') ed.chain().focus().toggleUnderline().run()
        else if (cmd === 'h1') ed.chain().focus().toggleHeading({ level: 1 }).run()
        else if (cmd === 'h2') ed.chain().focus().toggleHeading({ level: 2 }).run()
        else if (cmd === 'h3') ed.chain().focus().toggleHeading({ level: 3 }).run()
        else if (cmd === 'bulletList') ed.chain().focus().toggleBulletList().run()
        else if (cmd === 'orderedList') ed.chain().focus().toggleOrderedList().run()
        else if (cmd === 'blockquote') ed.chain().focus().toggleBlockquote().run()
        this._updateActive()
      }
    })
  },

  _updateActive() {
    const ed = this._editor
    if (!ed) return
    document.querySelectorAll('.tt-btn').forEach(btn => {
      const c = btn.dataset.cmd
      let a = false
      if (c === 'bold') a = ed.isActive('bold')
      else if (c === 'italic') a = ed.isActive('italic')
      else if (c === 'underline') a = ed.isActive('underline')
      else if (c === 'h1') a = ed.isActive('heading', { level: 1 })
      else if (c === 'h2') a = ed.isActive('heading', { level: 2 })
      else if (c === 'h3') a = ed.isActive('heading', { level: 3 })
      else if (c === 'bulletList') a = ed.isActive('bulletList')
      else if (c === 'orderedList') a = ed.isActive('orderedList')
      else if (c === 'blockquote') a = ed.isActive('blockquote')
      btn.classList.toggle('active', a)
    })
  },

  async save() {
    const ed = this._editor
    if (!ed || !this._currentId) return
    const html = ed.getHTML()
    const md = turndown.turndown(html)
    try {
      await fetch(`${this._baseUrl}/api/plugins/notes/${this._currentId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + this._token },
        body: JSON.stringify({ content: md }),
      })
      if (this._onSave) this._onSave()
    } catch (e) {}
  },

  async _uploadImage(file) {
    try {
      const res = await fetch(`${this._baseUrl}/api/v1/files/upload/note`, {
        method: 'POST',
        headers: { Authorization: 'Bearer ' + this._token },
      })
      if (!res.ok) return
      const { upload_url, object_key } = await res.json()
      await fetch(upload_url, { method: 'PUT', body: file })
      const imgUrl = `${this._baseUrl}/api/v1/files/note/${object_key}`
      if (this._editor) {
        this._editor.chain().focus().setImage({ src: imgUrl }).run()
      }
    } catch (e) {}
  },

  destroy() {
    if (this._editor) this._editor.destroy()
    this._editor = null
  },
}
