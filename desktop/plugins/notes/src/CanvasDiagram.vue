<template>
  <div class="canvas-wrap" ref="wrapRef">
    <div class="canvas-toolbar">
      <button class="c-tool" draggable="true" @mousedown.prevent="addNode('rect')" @dragstart="onToolDragStart($event, 'rect')" title="矩形">▭ 矩形</button>
      <button class="c-tool" draggable="true" @mousedown.prevent="addNode('ellipse')" @dragstart="onToolDragStart($event, 'ellipse')" title="圆角矩形">⬭ 圆角</button>
      <button class="c-tool" draggable="true" @mousedown.prevent="addNode('diamond')" @dragstart="onToolDragStart($event, 'diamond')" title="菱形">◇ 菱形</button>
      <button class="c-tool" draggable="true" @mousedown.prevent="addNode('circle')" @dragstart="onToolDragStart($event, 'circle')" title="圆形">◯ 圆形</button>
      <span class="c-sep"></span>
      <span class="c-zoom">缩放 {{ Math.round(scale * 100) }}%</span>
      <button class="c-tool" @mousedown.prevent="zoomIn" title="放大">＋</button>
      <button class="c-tool" @mousedown.prevent="zoomOut" title="缩小">－</button>
      <button class="c-tool" @mousedown.prevent="fitView" title="适应内容">⤢ 适应</button>
      <span class="c-flex"></span>
      <button class="c-tool del" @mousedown.prevent="requestDelete">🗑 删除图表</button>
    </div>
    <div class="canvas-area" ref="areaRef" @wheel.prevent="onWheel" @dragover.prevent="onDragOver" @drop.prevent="onDropShape">
      <svg class="canvas-svg" :viewBox="viewBox" @mousedown="onSvgMouseDown" @dblclick="onSvgDblClick">
        <defs>
          <pattern id="grid-dots" width="20" height="20" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="1" fill="#e2e8f0" />
          </pattern>
          <marker id="c-arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L0,6 L9,3 z" fill="#64748b" />
          </marker>
        </defs>
        <rect x="-4000" y="-4000" width="8000" height="8000" fill="url(#grid-dots)" />
        <g v-for="e in edges" :key="e.id">
          <path :d="edgePath(e)" class="edge-line" :class="{ selected: selectedEdge?.id === e.id }" stroke="#94a3b8" stroke-width="2" fill="none" marker-end="url(#c-arrow)" @mousedown.stop="selectEdge(e)" />
          <circle :cx="edgeCenter(e).x" :cy="edgeCenter(e).y" r="9" fill="transparent" @mousedown.stop="selectEdge(e)" />
        </g>
        <path v-if="tempEdgeActive" :d="tempEdgePath" stroke="#3b82f6" stroke-width="2" fill="none" stroke-dasharray="6,4" />
        <g v-for="n in nodes" :key="n.id" :transform="`translate(${n.x},${n.y})`" @mousedown.stop="onNodeMouseDown(n, $event)" @dblclick.stop="editNode(n)">
          <rect v-if="n.shape === 'rect'" :width="n.w" :height="n.h" rx="6" :class="['c-node', { sel: selectedNode?.id === n.id, hover: hoverTarget === n.id }]" :fill="n.color || '#fff'" />
          <rect v-else-if="n.shape === 'ellipse'" :width="n.w" :height="n.h" rx="60" :class="['c-node', { sel: selectedNode?.id === n.id, hover: hoverTarget === n.id }]" :fill="n.color || '#fff'" />
          <polygon v-else-if="n.shape === 'diamond'" :points="diamondPoints(n)" :class="['c-node', 'c-node-diamond', { sel: selectedNode?.id === n.id, hover: hoverTarget === n.id }]" :fill="n.color || '#fef9c3'" />
          <circle v-else :cx="n.w / 2" :cy="n.h / 2" :r="Math.min(n.w, n.h) / 2" :class="['c-node', { sel: selectedNode?.id === n.id, hover: hoverTarget === n.id }]" :fill="n.color || '#fff'" />
          <text v-if="!(editingId === n.id)" :x="n.w / 2" :y="n.h / 2" class="c-node-text" :fill="n.textColor || '#334155'" :font-size="n.fontSize || 13" text-anchor="middle" dominant-baseline="central">{{ n.text || '' }}</text>
          <template v-if="selectedNode?.id === n.id">
            <g class="c-anchor" @mousedown.stop="startAnchorConnect(n, $event)"><circle :cx="n.w / 2" :cy="0" r="6" class="c-anchor-dot" /></g>
            <g class="c-anchor" @mousedown.stop="startAnchorConnect(n, $event)"><circle :cx="n.w / 2" :cy="n.h" r="6" class="c-anchor-dot" /></g>
            <g class="c-anchor" @mousedown.stop="startAnchorConnect(n, $event)"><circle :cx="0" :cy="n.h / 2" r="6" class="c-anchor-dot" /></g>
            <g class="c-anchor" @mousedown.stop="startAnchorConnect(n, $event)"><circle :cx="n.w" :cy="n.h / 2" r="6" class="c-anchor-dot" /></g>
            <g class="c-resize" @mousedown.stop="startResize(n, $event)">
              <rect :x="n.w - 8" :y="n.h - 8" width="16" height="16" fill="transparent" />
              <path :d="`M ${n.w - 3} ${n.h - 9} L ${n.w - 9} ${n.h - 3}`" class="c-resize-line" />
              <path :d="`M ${n.w - 3} ${n.h - 15} L ${n.w - 15} ${n.h - 3}`" class="c-resize-line" />
            </g>
          </template>
        </g>
      </svg>
      <input v-if="editingId" ref="editInputRef" class="c-edit-input" v-model="editText" @blur="finishEdit" @keydown.enter.prevent="finishEdit" @keydown.esc="finishEdit" />
      <div v-if="connecting" class="c-connect-hint">从锚点拖到目标节点连线</div>
      <div v-else-if="panning" class="c-connect-hint">拖动画布移动视野</div>
      <div v-if="selectedNode" class="c-props">
        <div class="c-props-hd">
          <span class="c-props-title">节点属性</span>
          <button class="c-props-close" @click.stop="selectNodeById(null)">✕</button>
        </div>
        <label class="c-prop-label">文本</label>
        <input v-model="selectedNode.text" class="c-prop-input" @input="save" @mousedown.stop @keydown.stop />
        <label class="c-prop-label">填充颜色</label>
        <div class="c-color-row">
          <span v-for="c in nodeColors" :key="c" class="c-color" :class="{ on: (selectedNode.color || '#fff') === c }" :style="{ background: c }" @click.stop="setColor(c)"></span>
        </div>
        <label class="c-prop-label">文字颜色</label>
        <div class="c-color-row">
          <span v-for="c in textColors" :key="c" class="c-color" :class="{ on: (selectedNode.textColor || '#334155') === c }" :style="{ background: c }" @click.stop="setTextColor(c)"></span>
        </div>
        <label class="c-prop-label">字号</label>
        <input v-model.number="selectedNode.fontSize" type="number" min="8" max="40" class="c-prop-input c-prop-num" @input="save" @mousedown.stop @keydown.stop />
        <label class="c-prop-label">形状</label>
        <div class="c-shape-row">
          <button v-for="s in ['rect', 'ellipse', 'diamond', 'circle']" :key="s" class="c-shape-btn" :class="{ on: selectedNode.shape === s }" @click.stop="setShape(s)">{{ s }}</button>
        </div>
        <label class="c-prop-label">层级 (Z)</label>
        <div class="c-shape-row">
          <button class="c-shape-btn" @click.stop="bringToFront">置顶</button>
          <button class="c-shape-btn" @click.stop="bringForward">上移</button>
          <button class="c-shape-btn" @click.stop="bringBackward">下移</button>
          <button class="c-shape-btn" @click.stop="sendToBack">置底</button>
        </div>
        <button class="c-prop-del" @click.stop="deleteSelected">删除节点</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted, onUnmounted } from 'vue'

interface DNode { id: string; x: number; y: number; w: number; h: number; shape: string; text: string; color?: string; textColor?: string; fontSize?: number; borderColor?: string; z?: number }
interface DEdge { id: string; from: string; to: string }

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string]; delete: [] }>()

function requestDelete() {
  emit('delete')
}

const nodes = ref<DNode[]>([])
const edges = ref<DEdge[]>([])
const selectedNode = ref<DNode | null>(null)
const selectedEdge = ref<DEdge | null>(null)
const connecting = ref(false)
const connectFrom = ref<DNode | null>(null)
const tempEdgeActive = ref(false)
const tempEdgePath = ref('')
const hoverTarget = ref<string | null>(null)
const areaRef = ref<HTMLElement | null>(null)
const wrapRef = ref<HTMLElement | null>(null)
const editingId = ref<string | null>(null)
const editText = ref('')
const editInputRef = ref<HTMLInputElement | null>(null)
const editInputStyle = ref({ left: '0px', top: '0px', width: '0px', height: '0px' })

const pan = ref({ x: 0, y: 0 })
const scale = ref(1)
const panning = ref(false)
let panStart = { x: 0, y: 0, vx: 0, vy: 0 }
let uid = 1
let dragState: { node: DNode; startX: number; startY: number; ox: number; oy: number } | null = null
let resizeState: { node: DNode; startX: number; startY: number; ow: number; oh: number } | null = null
let anchorConnect: { from: DNode; start: { x: number; y: number } } | null = null
let rafId: number | null = null
let selectedId: string | null = null

const viewBox = computed(() => {
  const w = 1200 / scale.value
  const h = 700 / scale.value
  return `${pan.value.x} ${pan.value.y} ${w} ${h}`
})

function screenToCanvas(clientX: number, clientY: number): { x: number; y: number } {
  const el = areaRef.value
  if (!el) return { x: 0, y: 0 }
  const rect = el.getBoundingClientRect()
  const vw = 1200 / scale.value
  const vh = 700 / scale.value
  return {
    x: pan.value.x + ((clientX - rect.left) / rect.width) * vw,
    y: pan.value.y + ((clientY - rect.top) / rect.height) * vh,
  }
}

function parseData() {
  try {
    const d = JSON.parse(props.modelValue || '{}')
    const arr = (d.nodes || []).map((n: any) => ({ color: '#fff', textColor: '#334155', fontSize: 13, ...n }))
    // sort by z for paint order
    arr.sort((a: any, b: any) => (a.z || 0) - (b.z || 0))
    nodes.value = arr
    edges.value = d.edges || []
    if (nodes.value.length) {
      uid = Math.max(...nodes.value.map((n: any) => parseInt(String(n.id).replace(/\D/g, '') || '0'))) + 1
      fitView(true)
    }
    if (selectedId) selectedNode.value = nodes.value.find(n => n.id === selectedId) || null
  } catch {
    nodes.value = []
    edges.value = []
  }
}
watch(() => props.modelValue, parseData, { immediate: true })

function save() {
  emit('update:modelValue', JSON.stringify({ nodes: nodes.value, edges: edges.value }))
}

function selectNodeById(id: string | null) {
  selectedId = id
  selectedNode.value = id ? nodes.value.find(n => n.id === id) || null : null
  selectedEdge.value = null
}
function selectNodeObj(n: DNode) {
  selectedId = n.id
  selectedNode.value = n
  selectedEdge.value = null
}

function lockSelect(lock: boolean) {
  document.body.style.userSelect = lock ? 'none' : ''
  document.body.style.webkitUserSelect = lock ? 'none' : ''
  const area = areaRef.value
  if (area) area.style.userSelect = lock ? 'none' : ''
}

function addNode(shape: string) {
  const center = { x: pan.value.x + 200 / scale.value, y: pan.value.y + 150 / scale.value }
  const n: DNode = {
    id: 'n' + (uid++),
    x: center.x - 70, y: center.y - 30,
    w: shape === 'circle' ? 80 : 140,
    h: shape === 'circle' ? 80 : 60,
    shape,
    text: shape === 'diamond' ? '判断' : shape === 'circle' ? '开始' : '节点',
    color: '#fff', textColor: '#334155', fontSize: 13,
  }
  nodes.value.push(n)
  selectNodeObj(n)
  save()
}

function diamondPoints(n: DNode): string {
  return `${n.w / 2},0 ${n.w},${n.h / 2} ${n.w / 2},${n.h} 0,${n.h / 2}`
}

const nodeColors = ['#ffffff', '#fee2e2', '#fef9c3', '#dcfce7', '#dbeafe', '#f3e8ff', '#ffedd5', '#f1f5f9']
const textColors = ['#334155', '#dc2626', '#d97706', '#16a34a', '#2563eb', '#7c3aed', '#0f172a', '#94a3b8']
function setColor(c: string) {
  if (selectedNode.value) { selectedNode.value.color = c; save() }
}
function setTextColor(c: string) {
  if (selectedNode.value) { selectedNode.value.textColor = c; save() }
}
function setShape(s: string) {
  if (selectedNode.value) {
    selectedNode.value.shape = s
    if (s === 'circle') { selectedNode.value.w = 80; selectedNode.value.h = 80 }
    else if (selectedNode.value.w < 120) { selectedNode.value.w = 140; selectedNode.value.h = 60 }
    save()
  }
}

// ---- toolbar drag to create ----
function onToolDragStart(ev: DragEvent, shape: string) {
  if (ev.dataTransfer) ev.dataTransfer.setData('application/x-draw-shape', shape)
}
function onDragOver(ev: DragEvent) {
  ev.preventDefault()
  if (ev.dataTransfer) ev.dataTransfer.dropEffect = 'copy'
}
function onDropShape(ev: DragEvent) {
  const shape = ev.dataTransfer?.getData('application/x-draw-shape')
  if (!shape) return
  const c = screenToCanvas(ev.clientX, ev.clientY)
  const n: DNode = {
    id: 'n' + (uid++),
    x: c.x - 70, y: c.y - 30,
    w: shape === 'circle' ? 80 : 140,
    h: shape === 'circle' ? 80 : 60,
    shape,
    text: shape === 'diamond' ? '判断' : shape === 'circle' ? '开始' : '节点',
    color: '#fff', textColor: '#334155', fontSize: 13,
  }
  nodes.value.push(n)
  selectNodeObj(n)
  save()
}

// ---- anchor drag to connect ----
function startAnchorConnect(n: DNode, ev: MouseEvent) {
  ev.stopPropagation()
  selectNodeObj(n)
  anchorConnect = { from: n, start: { x: n.x + n.w / 2, y: n.y + n.h / 2 } }
  tempEdgeActive.value = true
  const move = (e: MouseEvent) => {
    if (!anchorConnect) return
    const c = screenToCanvas(e.clientX, e.clientY)
    tempEdgePath.value = `M ${anchorConnect.start.x} ${anchorConnect.start.y} L ${c.x} ${c.y}`
    const t = findNodeAt(e.clientX, e.clientY)
    hoverTarget.value = t && t.id !== anchorConnect.from.id ? t.id : null
  }
  const up = (e: MouseEvent) => {
    window.removeEventListener('mousemove', move)
    window.removeEventListener('mouseup', up)
    if (anchorConnect) {
      const targetId = hoverTarget.value
      if (targetId && targetId !== anchorConnect.from.id) {
        edges.value.push({ id: 'e' + (uid++), from: anchorConnect.from.id, to: targetId })
        save()
      }
    }
    anchorConnect = null
    tempEdgeActive.value = false
    tempEdgePath.value = ''
    hoverTarget.value = null
  }
  window.addEventListener('mousemove', move)
  window.addEventListener('mouseup', up)
}
function findNodeAt(clientX: number, clientY: number): DNode | null {
  const c = screenToCanvas(clientX, clientY)
  for (let i = nodes.value.length - 1; i >= 0; i--) {
    const n = nodes.value[i]
    if (c.x >= n.x && c.x <= n.x + n.w && c.y >= n.y && c.y <= n.y + n.h) return n
  }
  return null
}

// ---- node drag ----
function onNodeMouseDown(n: DNode, ev: MouseEvent) {
  if (connecting.value) {
    if (connectFrom.value && connectFrom.value.id !== n.id) {
      edges.value.push({ id: 'e' + (uid++), from: connectFrom.value.id, to: n.id })
      save()
    }
    connecting.value = false
    connectFrom.value = null
    tempEdgeActive.value = false
    return
  }
  selectNodeObj(n)
  lockSelect(true)
  dragState = { node: n, startX: ev.clientX, startY: ev.clientY, ox: n.x, oy: n.y }
  window.addEventListener('mousemove', onNodeDrag)
  window.addEventListener('mouseup', stopNodeDrag)
}
function onNodeDrag(ev: MouseEvent) {
  if (!dragState) return
  if (rafId) cancelAnimationFrame(rafId)
  rafId = requestAnimationFrame(() => {
    const a = screenToCanvas(ev.clientX, ev.clientY)
    const b = screenToCanvas(dragState!.startX, dragState!.startY)
    const node = nodes.value.find(n => n.id === dragState!.node.id)
    if (node) {
      node.x = Math.round(dragState!.ox + (a.x - b.x))
      node.y = Math.round(dragState!.oy + (a.y - b.y))
    }
  })
}
function stopNodeDrag() {
  if (rafId) { cancelAnimationFrame(rafId); rafId = null }
  window.removeEventListener('mousemove', onNodeDrag)
  window.removeEventListener('mouseup', stopNodeDrag)
  lockSelect(false)
  if (dragState) { dragState = null; save() }
}

// ---- resize ----
function startResize(n: DNode, ev: MouseEvent) {
  ev.stopPropagation()
  lockSelect(true)
  resizeState = { node: n, startX: ev.clientX, startY: ev.clientY, ow: n.w, oh: n.h }
  window.addEventListener('mousemove', onResize)
  window.addEventListener('mouseup', stopResize)
}
function onResize(ev: MouseEvent) {
  if (!resizeState) return
  if (rafId) cancelAnimationFrame(rafId)
  rafId = requestAnimationFrame(() => {
    const a = screenToCanvas(ev.clientX, ev.clientY)
    const b = screenToCanvas(resizeState!.startX, resizeState!.startY)
    const node = nodes.value.find(n => n.id === resizeState!.node.id)
    if (node) {
      node.w = Math.max(40, resizeState!.ow + (a.x - b.x))
      node.h = Math.max(30, resizeState!.oh + (a.y - b.y))
    }
  })
}
function stopResize() {
  if (rafId) { cancelAnimationFrame(rafId); rafId = null }
  window.removeEventListener('mousemove', onResize)
  window.removeEventListener('mouseup', stopResize)
  lockSelect(false)
  if (resizeState) { resizeState = null; save() }
}

// ---- z-order ----
function bringForward() { reorder(1) }
function bringBackward() { reorder(-1) }
function bringToFront() { reorder(Infinity) }
function sendToBack() { reorder(-Infinity) }
function reorder(dir: number) {
  const idx = nodes.value.findIndex(n => n.id === selectedNode.value?.id)
  if (idx < 0) return
  const [node] = nodes.value.splice(idx, 1)
  let target = dir === Infinity ? nodes.value.length : dir === -Infinity ? 0 : idx + dir
  target = Math.max(0, Math.min(nodes.value.length, target))
  nodes.value.splice(target, 0, node)
  nodes.value.forEach((n, i) => { n.z = i })
  save()
}

// ---- pan ----
function onSvgMouseDown(ev: MouseEvent) {
  if (connecting.value) { startTempEdge(ev); return }
  selectNodeById(null)
  panning.value = true
  lockSelect(true)
  panStart = { x: ev.clientX, y: ev.clientY, vx: pan.value.x, vy: pan.value.y }
  window.addEventListener('mousemove', onPan)
  window.addEventListener('mouseup', stopPan)
}
function onPan(ev: MouseEvent) {
  if (!panning.value) return
  const el = areaRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const vw = 1200 / scale.value
  const vh = 700 / scale.value
  pan.value.x = panStart.vx - ((ev.clientX - panStart.x) / rect.width) * vw
  pan.value.y = panStart.vy - ((ev.clientY - panStart.y) / rect.height) * vh
}
function stopPan() {
  panning.value = false
  window.removeEventListener('mousemove', onPan)
  window.removeEventListener('mouseup', stopPan)
  lockSelect(false)
}

// ---- temp edge (legacy connect mode) ----
function startTempEdge(ev: MouseEvent) {
  connectFrom.value = null
  tempEdgeActive.value = true
  const move = (e: MouseEvent) => {
    const c = screenToCanvas(e.clientX, e.clientY)
    tempEdgePath.value = `M ${c.x} ${c.y} L ${c.x} ${c.y}`
  }
  const up = () => {
    window.removeEventListener('mousemove', move)
    window.removeEventListener('mouseup', up)
    tempEdgeActive.value = false
    connecting.value = false
    connectFrom.value = null
  }
  window.addEventListener('mousemove', move)
  window.addEventListener('mouseup', up)
}

// ---- zoom ----
function zoomAt(cx: number, cy: number, factor: number) {
  const el = areaRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const before = screenToCanvas(cx, cy)
  const newScale = Math.min(3, Math.max(0.3, scale.value * factor))
  scale.value = newScale
  const ratioX = (cx - rect.left) / rect.width
  const ratioY = (cy - rect.top) / rect.height
  const vw = 1200 / scale.value
  const vh = 700 / scale.value
  pan.value.x = before.x - ratioX * vw
  pan.value.y = before.y - ratioY * vh
}
function onWheel(ev: WheelEvent) {
  zoomAt(ev.clientX, ev.clientY, ev.deltaY < 0 ? 1.15 : 0.87)
}
function zoomIn() {
  const el = areaRef.value
  if (!el) return
  const r = el.getBoundingClientRect()
  zoomAt(r.left + r.width / 2, r.top + r.height / 2, 1.2)
}
function zoomOut() {
  const el = areaRef.value
  if (!el) return
  const r = el.getBoundingClientRect()
  zoomAt(r.left + r.width / 2, r.top + r.height / 2, 0.85)
}
function fitView(initial = false) {
  if (!nodes.value.length) {
    pan.value = { x: -300, y: -150 }
    scale.value = 1
    return
  }
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const n of nodes.value) {
    minX = Math.min(minX, n.x); minY = Math.min(minY, n.y)
    maxX = Math.max(maxX, n.x + n.w); maxY = Math.max(maxY, n.y + n.h)
  }
  const w = (maxX - minX) + 120
  const h = (maxY - minY) + 120
  const el = areaRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const s = Math.min(rect.width / w, rect.height / h, 2)
  scale.value = Math.max(0.3, s)
  pan.value = { x: minX - 60 - (rect.width - w * scale.value) / (2 * scale.value), y: minY - 60 - (rect.height - h * scale.value) / (2 * scale.value) }
}

// ---- selection / edit ----
function onSvgDblClick(ev: MouseEvent) {
  const c = screenToCanvas(ev.clientX, ev.clientY)
  const n: DNode = { id: 'n' + (uid++), x: c.x - 70, y: c.y - 30, w: 140, h: 60, shape: 'rect', text: '节点', color: '#fff', textColor: '#334155', fontSize: 13 }
  nodes.value.push(n)
  selectNodeObj(n)
  save()
}
function selectEdge(e: DEdge) {
  selectedEdge.value = e
  selectedNode.value = null
}
function editNode(n: DNode) {
  editingId.value = n.id
  editText.value = n.text || ''
  nextTick(() => {
    const el = areaRef.value
    if (!el) return
    const rect = el.getBoundingClientRect()
    const vw = 1200 / scale.value
    const cssX = ((n.x - pan.value.x) / vw) * rect.width
    const cssY = ((n.y - pan.value.y) / (700 / scale.value)) * rect.height
    editInputStyle.value = {
      left: (cssX + 6) + 'px',
      top: (cssY + n.h / 2 - 14) + 'px',
      width: (n.w / vw * rect.width - 12) + 'px',
      height: '28px',
    }
    editInputRef.value?.focus()
    editInputRef.value?.select()
  })
}
function finishEdit() {
  const n = nodes.value.find(x => x.id === editingId.value)
  if (n) { n.text = editText.value; save() }
  editingId.value = null
}
function deleteSelected() {
  if (selectedNode.value) {
    const id = selectedNode.value.id
    nodes.value = nodes.value.filter(n => n.id !== id)
    edges.value = edges.value.filter(e => e.from !== id && e.to !== id)
    selectNodeById(null)
    save()
  } else if (selectedEdge.value) {
    edges.value = edges.value.filter(e => e.id !== selectedEdge.value?.id)
    selectedEdge.value = null
    save()
  }
}

function edgePath(e: DEdge): string {
  const a = nodes.value.find(n => n.id === e.from)
  const b = nodes.value.find(n => n.id === e.to)
  if (!a || !b) return ''
  const ax = a.x + a.w / 2, ay = a.y + a.h / 2
  const bx = b.x + b.w / 2, by = b.y + b.h / 2
  const mx = (ax + bx) / 2
  return `M ${ax} ${ay} C ${mx} ${ay}, ${mx} ${by}, ${bx} ${by}`
}
function edgeCenter(e: DEdge) {
  const a = nodes.value.find(n => n.id === e.from)
  const b = nodes.value.find(n => n.id === e.to)
  return { x: ((a?.x || 0) + (a?.w || 0) / 2 + (b?.x || 0) + (b?.w || 0) / 2) / 2, y: ((a?.y || 0) + (a?.h || 0) / 2 + (b?.y || 0) + (b?.h || 0) / 2) / 2 }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Delete' || e.key === 'Backspace') {
    const t = e.target as HTMLElement
    if (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA') return
    if (selectedNode.value || selectedEdge.value) { e.preventDefault(); deleteSelected() }
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 'd' && selectedNode.value) {
    e.preventDefault()
    const n = { ...selectedNode.value, id: 'n' + (uid++), x: selectedNode.value.x + 30, y: selectedNode.value.y + 30 }
    nodes.value.push(n)
    selectNodeObj(n)
    save()
  }
  if (e.key === 'Escape') {
    connecting.value = false; connectFrom.value = null; tempEdgeActive.value = false
    editingId.value = null
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  fitView(true)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('mousemove', onNodeDrag)
  window.removeEventListener('mouseup', stopNodeDrag)
  window.removeEventListener('mousemove', onPan)
  window.removeEventListener('mouseup', stopPan)
})
</script>

<style scoped>
.canvas-wrap { border: 1px solid #e2e8f0; border-radius: 10px; overflow: hidden; background: #fafbfc; }
.canvas-toolbar { display: flex; align-items: center; gap: 4px; padding: 6px 10px; border-bottom: 1px solid #e2e8f0; background: #f8fafc; flex-wrap: wrap; }
.c-tool { padding: 4px 10px; border: 1px solid #e2e8f0; border-radius: 6px; background: #fff; color: #475569; font-size: 12px; cursor: pointer; }
.c-tool:hover { background: #eef2ff; color: #4f46e5; }
.c-tool.active { background: #e0e7ff; color: #4f46e5; border-color: #a5b4fc; }
.c-tool.del:hover { background: #fef2f2; color: #dc2626; border-color: #fca5a5; }
.c-sep { width: 1px; height: 18px; background: #e2e8f0; margin: 0 2px; }
.c-flex { flex: 1; }
.c-zoom { font-size: 11px; color: #94a3b8; margin: 0 4px; }
.canvas-area { position: relative; width: 100%; height: 480px; overflow: hidden; cursor: grab; }
.canvas-area:active { cursor: grabbing; }
.canvas-svg { display: block; width: 100%; height: 100%; user-select: none; touch-action: none; }
.c-node { stroke: #94a3b8; stroke-width: 1.5; cursor: move; }
.c-node.sel { stroke: #3b82f6; stroke-width: 2; }
.c-node.hover { stroke: #22c55e; stroke-width: 3; stroke-dasharray: 6,3; }
.c-node-text { pointer-events: none; font-family: -apple-system, 'Segoe UI', sans-serif; }
.edge-line { cursor: pointer; }
.edge-line.selected { stroke: #3b82f6; stroke-width: 2.5; }
.c-anchor { cursor: crosshair; }
.c-anchor-dot { fill: #3b82f6; stroke: #fff; stroke-width: 2; }
.c-anchor:hover .c-anchor-dot { fill: #2563eb; }
.c-resize { cursor: nwse-resize; }
.c-resize-line { stroke: #3b82f6; stroke-width: 2; fill: none; }
.c-edit-input { position: absolute; z-index: 10; border: 1px solid #3b82f6; border-radius: 4px; font-size: 13px; padding: 2px 6px; outline: none; }
.c-connect-hint { position: absolute; bottom: 8px; left: 50%; transform: translateX(-50%); background: #1e293b; color: #fff; font-size: 11px; padding: 4px 12px; border-radius: 6px; z-index: 20; pointer-events: none; }
.c-props { position: absolute; top: 10px; right: 10px; z-index: 30; width: 180px; background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; box-shadow: 0 8px 24px rgba(0,0,0,0.12); padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; }
.c-props-hd { display: flex; justify-content: space-between; align-items: center; }
.c-props-close { border: none; background: transparent; cursor: pointer; color: #94a3b8; font-size: 13px; }
.c-props-title { font-size: 11px; font-weight: 600; color: #64748b; }
.c-prop-input { width: 100%; padding: 4px 8px; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 12px; outline: none; }
.c-prop-input:focus { border-color: #3b82f6; }
.c-prop-num { width: 70px; }
.c-prop-label { font-size: 11px; color: #64748b; }
.c-color-row { display: flex; gap: 4px; flex-wrap: wrap; }
.c-color { width: 18px; height: 18px; border-radius: 4px; border: 1px solid #cbd5e1; cursor: pointer; }
.c-color.on { outline: 2px solid #3b82f6; outline-offset: 1px; }
.c-shape-row { display: flex; gap: 4px; flex-wrap: wrap; }
.c-shape-btn { padding: 3px 8px; border: 1px solid #e2e8f0; background: #fff; border-radius: 5px; font-size: 10px; cursor: pointer; color: #64748b; }
.c-shape-btn.on { background: #e0e7ff; color: #4f46e5; border-color: #a5b4fc; }
.c-prop-del { padding: 3px 10px; border: 1px solid #fca5a5; background: #fef2f2; color: #dc2626; border-radius: 6px; font-size: 11px; cursor: pointer; align-self: flex-start; }
</style>
