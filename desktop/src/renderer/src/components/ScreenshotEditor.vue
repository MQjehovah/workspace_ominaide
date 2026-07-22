<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'

const imageSrc = ref('')
const canvasRef = ref<HTMLCanvasElement>()
const imageRef = ref<HTMLImageElement>()

type Tool = 'rect' | 'arrow' | 'line' | 'text' | 'blur' | 'move'
const currentTool = ref<Tool>('move')
const color = ref('#ff3b30')
const lineWidth = ref(3)
const fontSize = ref(20)
const textContent = ref('')

const isDrawing = ref(false)
const startX = ref(0)
const startY = ref(0)
const annotations = ref<any[]>([])

const imageWidth = ref(0)
const imageHeight = ref(0)

const scale = ref(1)
const panX = ref(0)
const panY = ref(0)
const isPanning = ref(false)
const panStartClientX = ref(0)
const panStartClientY = ref(0)
const panStartX = ref(0)
const panStartY = ref(0)
const viewportRef = ref<HTMLElement>()
const wrapperStyle = ref('')

const MIN_SCALE = 0.05
const MAX_SCALE = 16

const colors = ['#ff3b30', '#ff9500', '#ffcc00', '#34c759', '#007aff', '#5856d6', '#ffffff', '#000000']

function updateWrapperStyle() {
  wrapperStyle.value = `transform: translate(${panX.value}px, ${panY.value}px) scale(${scale.value}); transform-origin: 0 0;`
}

const setImageHandler = (dataUrl: string) => {
  imageSrc.value = dataUrl
}

onMounted(() => {
  window.mqbox?.screenshot?.onImage(setImageHandler)
})

onUnmounted(() => {})

watch(imageSrc, () => {
  if (imageSrc.value) {
    const img = new Image()
    img.onload = () => {
      imageWidth.value = img.width
      imageHeight.value = img.height
      zoomReset()
      redrawCanvas()
    }
    img.src = imageSrc.value
  }
})

const getCanvasPos = (e: MouseEvent) => {
  const canvas = canvasRef.value
  if (!canvas) return { x: 0, y: 0 }
  const rect = canvas.getBoundingClientRect()
  return {
    x: (e.clientX - rect.left) / scale.value,
    y: (e.clientY - rect.top) / scale.value,
  }
}

const onViewportMouseDown = (e: MouseEvent) => {
  if (e.button === 1 || currentTool.value === 'move') {
    e.preventDefault()
    isPanning.value = true
    panStartClientX.value = e.clientX
    panStartClientY.value = e.clientY
    panStartX.value = panX.value
    panStartY.value = panY.value
    return
  }
}

const onViewportMouseMove = (e: MouseEvent) => {
  if (isPanning.value) {
    panX.value = panStartX.value + (e.clientX - panStartClientX.value)
    panY.value = panStartY.value + (e.clientY - panStartClientY.value)
    updateWrapperStyle()
  }
}

const onViewportMouseUp = () => {
  isPanning.value = false
}

const onCanvasMouseDown = (e: MouseEvent) => {
  if (currentTool.value === 'move' || currentTool.value === 'text') return
  e.stopPropagation()
  const pos = getCanvasPos(e)
  startX.value = pos.x
  startY.value = pos.y
  isDrawing.value = true
}

const onCanvasMouseMove = (e: MouseEvent) => {
  if (!isDrawing.value) return
  e.stopPropagation()
  const pos = getCanvasPos(e)
  redrawCanvas()
  drawPreview(pos.x, pos.y)
}

const onCanvasMouseUp = (e: MouseEvent) => {
  if (!isDrawing.value) return
  e.stopPropagation()
  const pos = getCanvasPos(e)
  isDrawing.value = false
  const annotation = createAnnotation(startX.value, startY.value, pos.x, pos.y)
  if (annotation) annotations.value.push(annotation)
  redrawCanvas()
}

const createAnnotation = (x1: number, y1: number, x2: number, y2: number) => {
  const tool = currentTool.value
  if (tool === 'rect') {
    return { type: 'rect', x: Math.min(x1, x2), y: Math.min(y1, y2), width: Math.abs(x2 - x1), height: Math.abs(y2 - y1), color: color.value, lineWidth: lineWidth.value }
  }
  if (tool === 'arrow') {
    return { type: 'arrow', x1, y1, x2, y2, color: color.value, lineWidth: lineWidth.value }
  }
  if (tool === 'line') {
    return { type: 'line', x1, y1, x2, y2, color: color.value, lineWidth: lineWidth.value }
  }
  if (tool === 'blur') {
    return { type: 'blur', x: Math.min(x1, x2), y: Math.min(y1, y2), width: Math.abs(x2 - x1), height: Math.abs(y2 - y1) }
  }
  return null
}

const drawPreview = (x: number, y: number) => {
  const canvas = canvasRef.value
  const ctx = canvas?.getContext('2d')
  if (!ctx) return
  ctx.strokeStyle = color.value
  ctx.lineWidth = lineWidth.value
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  if (currentTool.value === 'rect') {
    ctx.strokeRect(Math.min(startX.value, x), Math.min(startY.value, y), Math.abs(x - startX.value), Math.abs(y - startY.value))
  } else if (currentTool.value === 'line' || currentTool.value === 'arrow') {
    ctx.beginPath()
    ctx.moveTo(startX.value, startY.value)
    ctx.lineTo(x, y)
    ctx.stroke()
    if (currentTool.value === 'arrow') drawArrowHead(ctx, startX.value, startY.value, x, y)
  } else if (currentTool.value === 'blur') {
    ctx.filter = 'blur(8px)'
    const bx = Math.min(startX.value, x)
    const by = Math.min(startY.value, y)
    const bw = Math.abs(x - startX.value)
    const bh = Math.abs(y - startY.value)
    if (imageRef.value && bw > 0 && bh > 0) {
      ctx.drawImage(imageRef.value, bx, by, bw, bh, bx, by, bw, bh)
    }
    ctx.filter = 'none'
  }
}

const drawArrowHead = (ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number) => {
  const angle = Math.atan2(y2 - y1, x2 - x1)
  const headLength = 12 + lineWidth.value * 2
  ctx.fillStyle = color.value
  ctx.beginPath()
  ctx.moveTo(x2, y2)
  ctx.lineTo(x2 - headLength * Math.cos(angle - Math.PI / 7), y2 - headLength * Math.sin(angle - Math.PI / 7))
  ctx.lineTo(x2 - headLength * Math.cos(angle + Math.PI / 7), y2 - headLength * Math.sin(angle + Math.PI / 7))
  ctx.closePath()
  ctx.fill()
}

const redrawCanvas = () => {
  const canvas = canvasRef.value
  const ctx = canvas?.getContext('2d')
  if (!ctx || !canvas || !imageRef.value) return
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.drawImage(imageRef.value, 0, 0)
  for (const annotation of annotations.value) {
    drawAnnotation(ctx, annotation)
  }
}

const drawAnnotation = (ctx: CanvasRenderingContext2D, a: any) => {
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  if (a.type === 'rect') {
    ctx.strokeStyle = a.color
    ctx.lineWidth = a.lineWidth
    ctx.strokeRect(a.x, a.y, a.width, a.height)
  } else if (a.type === 'arrow') {
    ctx.strokeStyle = a.color
    ctx.lineWidth = a.lineWidth
    ctx.beginPath()
    ctx.moveTo(a.x1, a.y1)
    ctx.lineTo(a.x2, a.y2)
    ctx.stroke()
    drawArrowHead(ctx, a.x1, a.y1, a.x2, a.y2)
  } else if (a.type === 'line') {
    ctx.strokeStyle = a.color
    ctx.lineWidth = a.lineWidth
    ctx.beginPath()
    ctx.moveTo(a.x1, a.y1)
    ctx.lineTo(a.x2, a.y2)
    ctx.stroke()
  } else if (a.type === 'text') {
    ctx.fillStyle = a.color
    ctx.font = `600 ${a.fontSize}px -apple-system, "Segoe UI", sans-serif`
    ctx.fillText(a.text, a.x, a.y)
  } else if (a.type === 'blur') {
    ctx.filter = 'blur(8px)'
    ctx.drawImage(imageRef.value!, a.x, a.y, a.width, a.height, a.x, a.y, a.width, a.height)
    ctx.filter = 'none'
  }
}

const onCanvasClick = (e: MouseEvent) => {
  if (currentTool.value !== 'text') return
  const pos = getCanvasPos(e)
  const text = textContent.value.trim()
  if (!text) return
  annotations.value.push({ type: 'text', x: pos.x, y: pos.y + fontSize.value, text, color: color.value, fontSize: fontSize.value })
  textContent.value = ''
  redrawCanvas()
}

const copyToClipboard = () => {
  const canvas = canvasRef.value
  if (!canvas) return
  window.mqbox?.clipboard?.writeImage(canvas.toDataURL('image/png'))
  closeEditor()
}

const saveToFile = () => {
  const canvas = canvasRef.value
  if (!canvas) return
  window.mqbox?.screenshot?.save(canvas.toDataURL('image/png'))
  closeEditor()
}

const pinToDesktop = () => {
  const canvas = canvasRef.value
  if (!canvas) return
  window.mqbox?.screenshot?.pin(canvas.toDataURL('image/png'))
  closeEditor()
}

const closeEditor = () => {
  window.mqbox?.screenshot?.closeEditor()
}

const undoLast = () => {
  annotations.value.pop()
  redrawCanvas()
}

const clearAll = () => {
  annotations.value = []
  redrawCanvas()
}

const onWheel = (e: WheelEvent) => {
  e.preventDefault()
  const vp = viewportRef.value
  if (!vp) return
  const rect = vp.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top
  const delta = e.deltaY < 0 ? 1.2 : 1 / 1.2
  const newScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale.value * delta))
  const cx = (mx - panX.value) / scale.value
  const cy = (my - panY.value) / scale.value
  scale.value = newScale
  panX.value = mx - cx * newScale
  panY.value = my - cy * newScale
  updateWrapperStyle()
}

const zoomByButton = (factor: number) => {
  const vp = viewportRef.value
  if (!vp) return
  const mx = vp.clientWidth / 2
  const my = vp.clientHeight / 2
  const newScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale.value * factor))
  const cx = (mx - panX.value) / scale.value
  const cy = (my - panY.value) / scale.value
  scale.value = newScale
  panX.value = mx - cx * newScale
  panY.value = my - cy * newScale
  updateWrapperStyle()
}

const zoomIn = () => zoomByButton(1.25)
const zoomOut = () => zoomByButton(1 / 1.25)

const zoomReset = () => {
  scale.value = 1
  const vp = viewportRef.value
  if (vp) {
    panX.value = Math.max(0, (vp.clientWidth - imageWidth.value) / 2)
    panY.value = Math.max(0, (vp.clientHeight - imageHeight.value) / 2)
  }
  updateWrapperStyle()
}

const zoomFit = () => {
  const vp = viewportRef.value
  if (!vp || !imageWidth.value) return
  const sx = vp.clientWidth / imageWidth.value
  const sy = vp.clientHeight / imageHeight.value
  const s = Math.min(sx, sy)
  scale.value = s
  panX.value = (vp.clientWidth - imageWidth.value * s) / 2
  panY.value = (vp.clientHeight - imageHeight.value * s) / 2
  updateWrapperStyle()
}

const tools: { id: Tool; label: string; icon: string }[] = [
  { id: 'move', label: '移动', icon: '<path d="M5 9l-3 3 3 3M9 5l3-3 3 3M15 19l-3 3-3-3M19 9l3 3-3 3M2 12h20M12 2v20"/>' },
  { id: 'rect', label: '矩形', icon: '<rect x="4" y="4" width="16" height="16" rx="1"/>' },
  { id: 'arrow', label: '箭头', icon: '<path d="M5 12h11M11 6l6 6-6 6"/>' },
  { id: 'line', label: '直线', icon: '<line x1="5" y1="19" x2="19" y2="5"/>' },
  { id: 'text', label: '文字', icon: '<path d="M5 7V5h14v2M12 5v14M9 19h6"/>' },
  { id: 'blur', label: '模糊', icon: '<rect x="4" y="4" width="16" height="16" rx="2" stroke-dasharray="3 3"/>' },
]
</script>

<template>
  <div class="ed">
    <!-- 顶部工具栏 -->
    <div class="bar">
      <div class="tools app-no-drag">
        <button
          v-for="t in tools"
          :key="t.id"
          class="tbtn"
          :class="{ on: currentTool === t.id }"
          :title="t.label"
          @click="currentTool = t.id"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="t.icon" />
        </button>
      </div>

      <div class="divider" />

      <!-- 颜色选择 -->
      <div class="colors app-no-drag">
        <button
          v-for="c in colors"
          :key="c"
          class="dot"
          :class="{ on: color === c }"
          :style="{ background: c }"
          @click="color = c"
        />
        <input type="color" v-model="color" class="picker" />
      </div>

      <div class="divider" />

      <!-- 粗细 -->
      <div class="sizes app-no-drag">
        <button :class="{ on: lineWidth === 2 }" @click="lineWidth = 2"><span class="sz s" /></button>
        <button :class="{ on: lineWidth === 4 }" @click="lineWidth = 4"><span class="sz m" /></button>
        <button :class="{ on: lineWidth === 8 }" @click="lineWidth = 8"><span class="sz l" /></button>
      </div>

      <!-- 文字输入 -->
      <div v-if="currentTool === 'text'" class="txt app-no-drag">
        <input v-model="textContent" placeholder="输入文字后点击画布..." class="txt-input" />
        <select v-model="fontSize" class="txt-size">
          <option :value="16">16</option>
          <option :value="20">20</option>
          <option :value="28">28</option>
          <option :value="36">36</option>
        </select>
      </div>

      <div class="flex-1" />

      <!-- 操作 -->
      <button class="icon-btn app-no-drag" title="撤销" @click="undoLast">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 7v6h6"/><path d="M3 13a9 9 0 1 0 3-7"/></svg>
      </button>
      <button class="icon-btn app-no-drag" title="清空" @click="clearAll">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
      </button>

      <div class="divider" />

      <button class="act-btn save app-no-drag" title="保存到文件" @click="saveToFile">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/></svg>
      </button>
      <button class="act-btn copy app-no-drag" title="复制到剪贴板" @click="copyToClipboard">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
      </button>
      <button class="act-btn pin app-no-drag" title="钉到桌面" @click="pinToDesktop">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 4h6l-1 7 4 3v2H6v-2l4-3z"/><path d="M12 16v5"/></svg>
      </button>
      <button class="btn-ghost app-no-drag" title="关闭" @click="closeEditor">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
      </button>
    </div>

    <!-- 画布区域 -->
    <div
      ref="viewportRef"
      class="viewport"
      @wheel="onWheel"
      @mousedown="onViewportMouseDown"
      @mousemove="onViewportMouseMove"
      @mouseup="onViewportMouseUp"
    >
      <div class="canvas-wrap" :style="wrapperStyle">
        <img ref="imageRef" :src="imageSrc" class="bg-img" @load="redrawCanvas" />
        <canvas
          ref="canvasRef"
          :width="imageWidth"
          :height="imageHeight"
          class="cv"
          :style="{ width: imageWidth + 'px', height: imageHeight + 'px', cursor: currentTool === 'move' ? (isPanning ? 'grabbing' : 'grab') : currentTool === 'text' ? 'text' : 'crosshair', pointerEvents: currentTool === 'move' ? 'none' : 'auto' }"
          @mousedown="onCanvasMouseDown"
          @mousemove="onCanvasMouseMove"
          @mouseup="onCanvasMouseUp"
          @click="onCanvasClick"
        />
      </div>
    </div>

    <!-- 底部状态栏 -->
    <div class="statusbar app-no-drag">
      <button class="zbtn" @click="zoomOut">−</button>
      <button class="zlabel" @click="zoomReset">{{ Math.round(scale * 100) }}%</button>
      <button class="zbtn" @click="zoomIn">+</button>
      <button class="zbtn" @click="zoomFit" title="适应窗口">⤢</button>
      <span class="hint">滚轮缩放 · 中键/手型工具拖动平移</span>
    </div>
  </div>
</template>

<style scoped>
.ed {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  background: #1a1a1e;
  user-select: none;
}

/* —— 顶部工具栏 —— */
.bar {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 52px;
  padding: 0 12px;
  background: rgba(28, 28, 30, 0.92);
  backdrop-filter: blur(20px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  -webkit-app-region: drag;
}

.tools { display: flex; gap: 2px; }

.tbtn {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: rgba(255, 255, 255, 0.5);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.tbtn svg { width: 18px; height: 18px; }
.tbtn:hover { background: rgba(255, 255, 255, 0.08); color: rgba(255, 255, 255, 0.9); }
.tbtn.on { background: rgba(0, 122, 255, 0.25); color: #0a84ff; }

.divider {
  width: 1px;
  height: 24px;
  background: rgba(255, 255, 255, 0.1);
  margin: 0 4px;
}

/* —— 颜色 —— */
.colors { display: flex; gap: 4px; align-items: center; }
.dot {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.15);
  cursor: pointer;
  transition: all 0.15s;
}
.dot:hover { transform: scale(1.15); }
.dot.on { border-color: #fff; transform: scale(1.2); box-shadow: 0 0 0 2px rgba(0, 122, 255, 0.4); }
.picker {
  width: 24px;
  height: 24px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 6px;
  cursor: pointer;
  background: transparent;
  padding: 0;
}

/* —— 粗细 —— */
.sizes { display: flex; gap: 2px; }
.sizes button {
  width: 32px;
  height: 36px;
  border: none;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.sizes button:hover { background: rgba(255, 255, 255, 0.08); }
.sizes button.on { background: rgba(0, 122, 255, 0.25); }
.sz { background: rgba(255, 255, 255, 0.7); border-radius: 50%; display: block; }
.sz.s { width: 4px; height: 4px; }
.sz.m { width: 8px; height: 8px; }
.sz.l { width: 14px; height: 14px; }

/* —— 文字 —— */
.txt { display: flex; gap: 4px; }
.txt-input {
  height: 30px;
  padding: 0 10px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.06);
  color: #fff;
  font-size: 13px;
  outline: none;
  width: 180px;
}
.txt-input:focus { border-color: rgba(0, 122, 255, 0.5); background: rgba(0, 122, 255, 0.08); }
.txt-input::placeholder { color: rgba(255, 255, 255, 0.3); }
.txt-size {
  height: 30px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.06);
  color: #fff;
  font-size: 12px;
  padding: 0 6px;
  outline: none;
}

/* —— 图标按钮 —— */
.icon-btn {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: rgba(255, 255, 255, 0.5);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.icon-btn svg { width: 18px; height: 18px; }
.icon-btn:hover { background: rgba(255, 255, 255, 0.08); color: rgba(255, 255, 255, 0.9); }

/* —— 操作按钮（图标） —— */
.act-btn {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.act-btn svg { width: 18px; height: 18px; }
.act-btn.save { background: rgba(48, 209, 88, 0.15); color: #30d158; }
.act-btn.save:hover { background: rgba(48, 209, 88, 0.3); }
.act-btn.copy { background: rgba(10, 132, 255, 0.15); color: #0a84ff; }
.act-btn.copy:hover { background: rgba(10, 132, 255, 0.3); }
.act-btn.pin { background: rgba(191, 90, 242, 0.15); color: #bf5af2; }
.act-btn.pin:hover { background: rgba(191, 90, 242, 0.3); }

.btn-ghost {
  width: 34px;
  height: 34px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: rgba(255, 255, 255, 0.4);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.btn-ghost svg { width: 16px; height: 16px; }
.btn-ghost:hover { background: rgba(255, 255, 255, 0.08); color: rgba(255, 255, 255, 0.9); }

/* —— 画布 —— */
.viewport {
  flex: 1;
  overflow: hidden;
  position: relative;
  background: #1a1a1e;
  background-image:
    radial-gradient(circle at 50% 50%, rgba(255,255,255,0.02) 0%, transparent 70%);
}

.canvas-wrap {
  display: inline-block;
  position: relative;
  filter: drop-shadow(0 8px 32px rgba(0, 0, 0, 0.5));
  line-height: 0;
}

.bg-img { display: block; }

.cv {
  position: absolute;
  top: 0;
  left: 0;
}

/* —— 底部状态栏 —— */
.statusbar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  height: 40px;
  background: rgba(28, 28, 30, 0.92);
  backdrop-filter: blur(20px);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  -webkit-app-region: drag;
}
.zbtn {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.7);
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.zbtn:hover { background: rgba(255, 255, 255, 0.12); color: #fff; }
.zlabel {
  height: 28px;
  min-width: 56px;
  padding: 0 8px;
  border: none;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.7);
  cursor: pointer;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.zlabel:hover { background: rgba(255, 255, 255, 0.12); color: #fff; }
.hint {
  margin-left: 12px;
  color: rgba(255, 255, 255, 0.2);
  font-size: 11px;
}

/* —— 全局 —— */
.flex-1 { flex: 1; }

.app-no-drag {
  -webkit-app-region: no-drag;
}
</style>
