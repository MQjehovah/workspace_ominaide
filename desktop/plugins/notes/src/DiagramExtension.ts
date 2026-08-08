import { Node, mergeAttributes } from '@tiptap/core'
import { VueNodeViewRenderer, NodeViewWrapper } from '@tiptap/vue-3'
import { h, defineComponent, ref, watch } from 'vue'
import CanvasDiagram from './CanvasDiagram.vue'

const DiagramNodeView = defineComponent({
  props: {
    node: { type: Object, required: true },
    updateAttributes: { type: Function, required: true },
    editor: { type: Object, required: true },
  },
  setup(props) {
    const data = ref(props.node?.attrs?.data || '')

    watch(() => props.node?.attrs?.data, (v) => {
      data.value = v || ''
    })

    function onDataChange(v: string) {
      props.updateAttributes({ data: v })
    }

    return () => h(NodeViewWrapper, { class: 'diagram-node-wrapper', contenteditable: 'false', style: 'margin:0.5em 0;border:1px dashed #cbd5e1;border-radius:10px;' }, [
      h(CanvasDiagram, {
        modelValue: data.value,
        'onUpdate:modelValue': onDataChange,
        onDelete: () => props.editor?.commands.deleteNode(props.node),
      }),
    ])
  },
})

export const Diagram = Node.create({
  name: 'diagramCanvas',
  group: 'block',
  atom: true,
  selectable: false,
  draggable: false,
  isolating: true,
  defining: true,

  addAttributes() {
    return {
      data: { default: '{"nodes":[],"edges":[]}' },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-diagram]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-diagram': '' })]
  },

  addNodeView() {
    return VueNodeViewRenderer(DiagramNodeView)
  },
})
