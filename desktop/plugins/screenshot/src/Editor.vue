<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'

const imageSrc = ref('')
const canvasRef = ref<HTMLCanvasElement>()
const imageRef = ref<HTMLImageElement>()

type Tool = 'rect' | 'arrow' | 'line' | 'text' | 'blur' | 'move' | 'none'
const currentTool = ref<Tool>('rect')
const color = ref('#ff0000')
const lineWidth = ref(2)
const fontSize = ref(16)
const textContent = ref('')

const isDrawing = ref(false)
const startX = ref(0)
const startY = ref(0)
const annotations = ref<any[]>([])

const imageWidth = ref(0)
const imageHeight = ref(0)

// 缩放与平移
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

function updateWrapperStyle() {
  wrapperStyle.value = `transform: translate(${panX.value}px, ${panY.value}px) scale(${scale.value}); transform-origin: 0 0;`
}

const setImageHandler = (dataUrl: string) => {
  imageSrc.value = dataUrl
}

onMounted(() => {
  window.mqbox?.window.on('screenshot-editor:set-image', setImageHandler)
})

onUnmounted(() => {
  window.mqbox?.window.removeListener('screenshot-editor:set-image', setImageHandler)
})

watch(imageSrc, () => {
  if (imageSrc.value) {
    const img = new Image()
    img.onload = () => {
      imageWidth.value = img.width
      imageHeight.value = img.height
      zoomFit()
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
    y: (e.clientY - rect.top) / scale.value
  }
}

// —— 平移（拖拽）——
const onViewportMouseDown = (e: MouseEvent) => {
  // 中键 或 move 工具 → 平移
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

// —— 绘制 ——
const onCanvasMouseDown = (e: MouseEvent) => {
  if (currentTool.value === 'move' || currentTool.value === 'none' || currentTool.value === 'text') return
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
  if (annotation) {
    annotations.value.push(annotation)
  }
  redrawCanvas()
}

const createAnnotation = (x1: number, y1: number, x2: number, y2: number) => {
  const tool = currentTool.value
  
  if (tool === 'rect') {
    return {
      type: 'rect',
      x: Math.min(x1, x2),
      y: Math.min(y1, y2),
      width: Math.abs(x2 - x1),
      height: Math.abs(y2 - y1),
      color: color.value,
      lineWidth: lineWidth.value
    }
  }
  
  if (tool === 'arrow') {
    return {
      type: 'arrow',
      x1, y1, x2, y2,
      color: color.value,
      lineWidth: lineWidth.value
    }
  }
  
  if (tool === 'line') {
    return {
      type: 'line',
      x1, y1, x2, y2,
      color: color.value,
      lineWidth: lineWidth.value
    }
  }
  
  if (tool === 'blur') {
    return {
      type: 'blur',
      x: Math.min(x1, x2),
      y: Math.min(y1, y2),
      width: Math.abs(x2 - x1),
      height: Math.abs(y2 - y1)
    }
  }
  
  return null
}

const drawPreview = (x: number, y: number) => {
  const canvas = canvasRef.value
  const ctx = canvas?.getContext('2d')
  if (!ctx) return
  
  ctx.strokeStyle = color.value
  ctx.lineWidth = lineWidth.value
  
  if (currentTool.value === 'rect') {
    ctx.strokeRect(
      Math.min(startX.value, x),
      Math.min(startY.value, y),
      Math.abs(x - startX.value),
      Math.abs(y - startY.value)
    )
  } else if (currentTool.value === 'line' || currentTool.value === 'arrow') {
    ctx.beginPath()
    ctx.moveTo(startX.value, startY.value)
    ctx.lineTo(x, y)
    ctx.stroke()
    
    if (currentTool.value === 'arrow') {
      drawArrowHead(ctx, startX.value, startY.value, x, y)
    }
  } else if (currentTool.value === 'blur') {
    ctx.fillStyle = 'rgba(0,0,0,0.3)'
    ctx.fillRect(
      Math.min(startX.value, x),
      Math.min(startY.value, y),
      Math.abs(x - startX.value),
      Math.abs(y - startY.value)
    )
  }
}

const drawArrowHead = (ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number) => {
  const angle = Math.atan2(y2 - y1, x2 - x1)
  const headLength = 10
  
  ctx.beginPath()
  ctx.moveTo(x2, y2)
  ctx.lineTo(x2 - headLength * Math.cos(angle - Math.PI / 6), y2 - headLength * Math.sin(angle - Math.PI / 6))
  ctx.moveTo(x2, y2)
  ctx.lineTo(x2 - headLength * Math.cos(angle + Math.PI / 6), y2 - headLength * Math.sin(angle + Math.PI / 6))
  ctx.stroke()
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
    ctx.font = `${a.fontSize}px sans-serif`
    ctx.fillText(a.text, a.x, a.y)
  } else if (a.type === 'blur') {
    ctx.fillStyle = 'rgba(128,128,128,0.5)'
    ctx.fillRect(a.x, a.y, a.width, a.height)
  }
}

const onCanvasClick = (e: MouseEvent) => {
  if (currentTool.value !== 'text') return
  const pos = getCanvasPos(e)
  annotations.value.push({
    type: 'text',
    x: pos.x, y: pos.y,
    text: textContent.value || 'Text',
    color: color.value,
    fontSize: fontSize.value
  })
  redrawCanvas()
}

const copyToClipboard = async () => {
  const canvas = canvasRef.value
  if (!canvas) return
  
  const dataUrl = canvas.toDataURL('image/png')
  await window.mqbox?.clipboard?.writeImage(dataUrl)
  closeEditor()
}

const saveToFile = async () => {
  const canvas = canvasRef.value
  if (!canvas) return
  
  const dataUrl = canvas.toDataURL('image/png')
  await window.mqbox?.screenshot?.save(dataUrl)
  closeEditor()
}

const pinToDesktop = async () => {
  const canvas = canvasRef.value
  if (!canvas) return
  
  const dataUrl = canvas.toDataURL('image/png')
  await window.mqbox?.screenshot?.pin(dataUrl)
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

const selectTool = (tool: Tool) => {
  currentTool.value = tool
}

// —— 缩放控制（以鼠标位置为中心）——
const onWheel = (e: WheelEvent) => {
  e.preventDefault()
  const vp = viewportRef.value
  if (!vp) return

  const rect = vp.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top

  const delta = e.deltaY < 0 ? 1.2 : 1 / 1.2
  const newScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale.value * delta))

  // 保持鼠标位置在画布上的点不变
  const cx = (mx - panX.value) / scale.value
  const cy = (my - panY.value) / scale.value
  scale.value = newScale
  panX.value = mx - cx * newScale
  panY.value = my - cy * newScale
  updateWrapperStyle()
}

const zoomByButton = (factor: number, centerX?: number, centerY?: number) => {
  const vp = viewportRef.value
  if (!vp) return
  const mx = centerX ?? vp.clientWidth / 2
  const my = centerY ?? vp.clientHeight / 2
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
</script>

<template>
  <div class="editor-container w-full h-full flex flex-col bg-gray-900">
    <div class="toolbar app-drag h-12 flex items-center gap-2 px-4 bg-gray-800 border-b border-gray-700">
      <div class="flex gap-1">
        <button 
          class="app-no-drag p-2 rounded"
          :class="currentTool === 'move' ? 'bg-blue-500' : 'bg-gray-700 hover:bg-gray-600'"
          @click="selectTool('move')"
          title="移动"
        >
          <svg class="w-4 h-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 11V6.5a1.5 1.5 0 0 0-3 0V11M18 11V5.5a1.5 1.5 0 0 1 3 0V13M18 11V4.5a1.5 1.5 0 0 1 3 0V13M18 11v6a4 4 0 0 1-4 4H9.5a4 4 0 0 1-3.2-1.6L3 16s1-1.5 2.5-1 2.5 2 2.5 2V7.5a1.5 1.5 0 0 1 3 0V11"/>
          </svg>
        </button>
        <button 
          class="app-no-drag p-2 rounded"
          :class="currentTool === 'rect' ? 'bg-blue-500' : 'bg-gray-700 hover:bg-gray-600'"
          @click="selectTool('rect')"
          title="矩形"
        >
          <svg class="w-4 h-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="18" height="18"/>
          </svg>
        </button>
        <button 
          class="app-no-drag p-2 rounded"
          :class="currentTool === 'arrow' ? 'bg-blue-500' : 'bg-gray-700 hover:bg-gray-600'"
          @click="selectTool('arrow')"
          title="箭头"
        >
          <svg class="w-4 h-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M5 12h14M12 5l7 7-7 7"/>
          </svg>
        </button>
        <button 
          class="app-no-drag p-2 rounded"
          :class="currentTool === 'line' ? 'bg-blue-500' : 'bg-gray-700 hover:bg-gray-600'"
          @click="selectTool('line')"
          title="线条"
        >
          <svg class="w-4 h-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="5" y1="19" x2="19" y2="5"/>
          </svg>
        </button>
        <button 
          class="app-no-drag p-2 rounded"
          :class="currentTool === 'text' ? 'bg-blue-500' : 'bg-gray-700 hover:bg-gray-600'"
          @click="selectTool('text')"
          title="文字"
        >
          <svg class="w-4 h-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 7V4h16v3M9 20h6M12 4v16"/>
          </svg>
        </button>
        <button 
          class="app-no-drag p-2 rounded"
          :class="currentTool === 'blur' ? 'bg-blue-500' : 'bg-gray-700 hover:bg-gray-600'"
          @click="selectTool('blur')"
          title="模糊"
        >
          <svg class="w-4 h-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="18" height="18" rx="3" stroke-dasharray="4 2"/>
          </svg>
        </button>
      </div>
      
      <div class="h-6 w-px bg-gray-600 mx-2"></div>
      
      <input 
        type="color" 
        v-model="color"
        class="app-no-drag w-6 h-6 rounded cursor-pointer"
      />
      
      <select v-model="lineWidth" class="app-no-drag h-6 px-1 rounded bg-gray-700 text-white text-xs">
        <option value="1">细</option>
        <option value="2">中</option>
        <option value="4">粗</option>
      </select>
      
      <div v-if="currentTool === 'text'" class="flex gap-1 items-center">
        <input 
          v-model="textContent"
          type="text"
          placeholder="输入文字..."
          class="app-no-drag h-6 px-2 rounded bg-gray-700 text-white text-xs w-20"
        />
        <select v-model="fontSize" class="app-no-drag h-6 px-1 rounded bg-gray-700 text-white text-xs">
          <option value="12">12</option>
          <option value="16">16</option>
          <option value="20">20</option>
          <option value="24">24</option>
        </select>
      </div>
      
      <div class="flex-1"></div>
      
      <button @click="undoLast" class="app-no-drag p-2 rounded bg-gray-700 hover:bg-gray-600" title="撤销">
        <svg class="w-4 h-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M3 7v6h6M3 13a9 9 0 1 0 2-7"/>
        </svg>
      </button>
      <button @click="clearAll" class="app-no-drag p-2 rounded bg-gray-700 hover:bg-gray-600" title="清除">
        <svg class="w-4 h-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
        </svg>
      </button>
      
      <div class="h-6 w-px bg-gray-600 mx-2"></div>
      
      <button @click="copyToClipboard" class="app-no-drag px-3 py-1.5 rounded bg-blue-500 hover:bg-blue-600 text-white text-xs">
        复制
      </button>
      <button @click="saveToFile" class="app-no-drag px-3 py-1.5 rounded bg-green-500 hover:bg-green-600 text-white text-xs">
        保存
      </button>
      <button @click="pinToDesktop" class="app-no-drag px-3 py-1.5 rounded bg-purple-500 hover:bg-purple-600 text-white text-xs">
        钉图
      </button>
      <button @click="closeEditor" class="app-no-drag px-3 py-1.5 rounded bg-gray-700 hover:bg-gray-600 text-white text-xs">
        关闭
      </button>
    </div>
    
    <div
      ref="viewportRef"
      class="canvas-viewport flex-1 overflow-hidden relative"
      @wheel="onWheel"
      @mousedown="onViewportMouseDown"
      @mousemove="onViewportMouseMove"
      @mouseup="onViewportMouseUp"
    >
      <div class="inline-block relative" :style="wrapperStyle">
        <img 
          ref="imageRef"
          :src="imageSrc"
          class="block"
          @load="redrawCanvas"
        />
        <canvas 
          ref="canvasRef"
          :width="imageWidth"
          :height="imageHeight"
          class="absolute top-0 left-0"
          :style="{ width: imageWidth + 'px', height: imageHeight + 'px', cursor: currentTool === 'move' ? (isPanning ? 'grabbing' : 'grab') : 'crosshair', pointerEvents: currentTool === 'move' ? 'none' : 'auto' }"
          @mousedown="onCanvasMouseDown"
          @mousemove="onCanvasMouseMove"
          @mouseup="onCanvasMouseUp"
          @click="onCanvasClick"
        />
      </div>
    </div>
    
    <div class="h-9 flex items-center justify-center gap-3 bg-gray-800 border-t border-gray-700 text-white text-xs">
      <button @click="zoomOut" class="app-no-drag px-2 py-0.5 rounded bg-gray-700 hover:bg-gray-600">−</button>
      <button @click="zoomReset" class="app-no-drag px-2 py-0.5 rounded bg-gray-700 hover:bg-gray-600 w-14 text-center">{{ Math.round(scale * 100) }}%</button>
      <button @click="zoomIn" class="app-no-drag px-2 py-0.5 rounded bg-gray-700 hover:bg-gray-600">+</button>
      <button @click="zoomFit" class="app-no-drag px-2 py-0.5 rounded bg-gray-700 hover:bg-gray-600">适应</button>
      <span class="text-gray-500 ml-2">滚轮缩放 · 选择手型工具或中键拖动平移</span>
    </div>
  </div>
</template>

<style scoped>
.editor-container {
  user-select: none;
}

/* 工具栏可拖动窗口 */
.app-drag {
  -webkit-app-region: drag;
}

/* 交互元素取消拖动 */
.app-no-drag {
  -webkit-app-region: no-drag;
}
</style>