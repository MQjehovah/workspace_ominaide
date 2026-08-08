import { Node, mergeAttributes } from '@tiptap/core'
import { VueNodeViewRenderer, NodeViewWrapper } from '@tiptap/vue-3'
import { h, defineComponent } from 'vue'

// Inline embed for another note: renders as a clickable card.
const NoteEmbedNode = defineComponent({
  props: {
    node: { type: Object, required: true },
    editor: { type: Object, required: true },
  },
  setup(props) {
    const attrs = props.node?.attrs || {}
    const id = attrs.noteId
    const label = attrs.label || '笔记 #' + id
    return () => h(NodeViewWrapper, { class: 'note-embed' }, [
      h('div', { class: 'note-embed-card', 'data-note-id': String(id) }, [
        h('span', { class: 'note-embed-icon' }, '📄'),
        h('span', { class: 'note-embed-label' }, String(label)),
      ]),
    ])
  },
})

export const NoteEmbed = Node.create({
  name: 'noteEmbed',
  group: 'block',
  atom: true,
  selectable: true,

  addAttributes() {
    return {
      noteId: { default: null },
      label: { default: '嵌入笔记' },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-note-embed]' }]
  },

  renderHTML({ HTMLAttributes }) {
    const { noteId, label } = HTMLAttributes as any
    return ['div', mergeAttributes(HTMLAttributes, {
      'data-note-embed': '',
      'data-note-id': String(noteId ?? ''),
    }), String(label || '')]
  },

  addNodeView() {
    return VueNodeViewRenderer(NoteEmbedNode)
  },
})
