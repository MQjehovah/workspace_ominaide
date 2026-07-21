<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'

interface DisplayInfo {
  id: number
  bounds: { x: number; y: number; width: number; height: number }
  scaleFactor: number
  isPrimary: boolean
  label: string
}

const displays = ref<DisplayInfo[]>([])
const images = ref<string[]>([])
const isSelecting = ref(false)
const selection = ref({ x: 0, y: 0, width: 0, height: 0 })
const startX = ref(0)
const startY = ref(0)
const bgCanvas = ref<HTMLCanvasElement | null>(null)
const currentDisplayId = ref<number>(0)

// 窗口 CSS 尺寸（可能不等于 display bounds，Windows DPI bug 导致）
const winW = ref(0)
const winH = ref(0)

const currentDisplay = computed(() => displays.value.find(d => d.id === currentDisplayId.value))

// ★ 窗口 CSS 坐标 → 屏幕 DIP 坐标的缩放比
//   窗口可能比屏幕大或小，鼠标坐标需要按比例映射到 DIP
const scaleX = computed(() => {
  const d = currentDisplay.value
  if (!d || winW.value === 0) return 1
  return d.bounds.width / winW.value
})
const scaleY = computed(() => {
  const d = currentDisplay.value
  if (!d || winH.value === 0) return 1
  return d.bounds.height / winH.value
})

const displayMasks = computed<{ style: Record<string, string> }[]>(() => {
  const masks: { style: Record<string, string> }[] = []
  const vw = winW.value
  const vh = winH.value
  const addBlock = (x: number, y: number, w: number, h: number) => {
    if (w <= 0 || h <= 0) return
    masks.push({
      style: {
        position: 'fixed',
        left: `${x}px`, top: `${y}px`, width: `${w}px`, height: `${h}px`,
        background: 'rgba(0, 0, 0, 0.5)', pointerEvents: 'none', zIndex: '40',
      },
    })
  }
  if (!isSelecting.value || selection.value.width < 3 || selection.value.height < 3) {
    addBlock(0, 0, vw, vh)
    return masks
  }
  // 选区 DIP 坐标 → 窗口 CSS 坐标
  const d = currentDisplay.value
  if (!d) { addBlock(0, 0, vw, vh); return masks }
  const selCssX = (selection.value.x - d.bounds.x) / scaleX.value
  const selCssY = (selection.value.y - d.bounds.y) / scaleY.value
  const selCssW = selection.value.width / scaleX.value
  const selCssH = selection.value.height / scaleY.value
  if (selCssY > 0) addBlock(0, 0, vw, selCssY)
  if (selCssY + selCssH < vh) addBlock(0, selCssY + selCssH, vw, vh - selCssY - selCssH)
  if (selCssX > 0) addBlock(0, selCssY, selCssX, selCssH)
  if (selCssX + selCssW < vw) addBlock(selCssX + selCssW, selCssY, vw - selCssX - selCssW, selCssH)
  return masks
})

const selectionStyle = computed(() => {
  const sel = selection.value
  if (sel.width < 3 || sel.height < 3) return {} as Record<string, string>
  const d = currentDisplay.value
  if (!d) return {} as Record<string, string>
  return {
    position: 'fixed',
    left: `${(sel.x - d.bounds.x) / scaleX.value}px`,
    top: `${(sel.y - d.bounds.y) / scaleY.value}px`,
    width: `${sel.width / scaleX.value}px`,
    height: `${sel.height / scaleY.value}px`,
    border: '2px solid #00a8ff',
    pointerEvents: 'none',
    zIndex: '50',
  } as Record<string, string>
})

onMounted(async () => {
  document.addEventListener('keydown', onKeyDown)
  try {
    const result = await window.mqbox?.screenshot?.getAllScreens()
    if (result) {
      displays.value = result.displays
      images.value = result.images

      winW.value = window.innerWidth
      winH.value = window.innerHeight

      // 检测当前窗口所在的显示器
      const wx = window.screenX || 0
      currentDisplayId.value = displays.value.find(d =>
        wx >= d.bounds.x && wx < d.bounds.x + d.bounds.width
      )?.id || displays.value[0]?.id || 0

      await nextTick()
      drawBackground()
    }
  } catch (e) {
    console.error('Failed to get screens:', e)
  }
})

async function drawBackground() {
  const canvas = bgCanvas.value
  if (!canvas) return
  const dispIdx = displays.value.findIndex(d => d.id === currentDisplayId.value)
  if (dispIdx < 0) return
  const dataUrl = images.value[dispIdx]
  if (!dataUrl) return

  const vw = window.innerWidth
  const vh = window.innerHeight
  canvas.width = vw
  canvas.height = vh
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.clearRect(0, 0, vw, vh)

  const img = new Image()
  img.src = dataUrl
  await new Promise<void>(resolve => {
    img.onload = () => resolve()
    img.onerror = () => resolve()
  })
  // 截图图片铺满窗口
  ctx.drawImage(img, 0, 0, vw, vh)
}

onUnmounted(() => {
  document.removeEventListener('keydown', onKeyDown)
})

const getScreenPosition = (clientX: number, clientY: number) => {
  const d = currentDisplay.value
  if (!d) return { x: clientX, y: clientY }
  return {
    x: d.bounds.x + clientX * scaleX.value,
    y: d.bounds.y + clientY * scaleY.value,
  }
}

const onMouseDown = (e: MouseEvent) => {
  e.preventDefault()
  isSelecting.value = true
  const pos = getScreenPosition(e.clientX, e.clientY)
  startX.value = pos.x
  startY.value = pos.y
  selection.value = { x: pos.x, y: pos.y, width: 0, height: 0 }
}

const onMouseMove = (e: MouseEvent) => {
  if (!isSelecting.value) return
  const pos = getScreenPosition(e.clientX, e.clientY)
  selection.value = {
    x: Math.min(startX.value, pos.x),
    y: Math.min(startY.value, pos.y),
    width: Math.abs(pos.x - startX.value),
    height: Math.abs(pos.y - startY.value),
  }
}

const onMouseUp = async (_e: MouseEvent) => {
  if (!isSelecting.value) return
  isSelecting.value = false
  if (selection.value.width < 5 || selection.value.height < 5) {
    selection.value = { x: 0, y: 0, width: 0, height: 0 }
    return
  }
  try {
    const result = await window.mqbox?.screenshot?.capture(
      selection.value.x, selection.value.y,
      selection.value.width, selection.value.height,
    )
    if (result) {
      window.mqbox?.screenshot?.cancel()
    }
  } catch (e) {
    console.error('Capture failed:', e)
  }
}

const onKeyDown = (e: KeyboardEvent) => {
  if (e.key === 'Escape') {
    window.mqbox?.screenshot?.cancel()
  }
}
</script>

<template>
  <div
    class="screenshot-panel"
    @mousedown="onMouseDown"
    @mousemove="onMouseMove"
    @mouseup="onMouseUp"
    @contextmenu.prevent
  >
    <canvas ref="bgCanvas" class="bg-canvas"></canvas>

    <div
      v-for="(mask, idx) in displayMasks"
      :key="'mask-' + idx"
      :style="mask.style"
    ></div>

    <div
      v-if="isSelecting && selection.width > 2 && selection.height > 2"
      class="selection-indicator"
      :style="selectionStyle"
    >
      <div class="size-label">{{ Math.round(selection.width) }} × {{ Math.round(selection.height) }}</div>
    </div>

    <div v-if="!isSelecting" class="hint">拖动选择截图区域，按 Esc 取消</div>
  </div>
</template>

<style scoped>
.screenshot-panel {
  position: fixed; left: 0; top: 0; width: 100vw; height: 100vh;
  z-index: 9999; background: transparent; cursor: crosshair; user-select: none;
  overflow: hidden;
}
.bg-canvas { position: fixed; left: 0; top: 0; width: 100vw; height: 100vh; z-index: 5; pointer-events: none; }
.selection-indicator { z-index: 50; }
.size-label {
  position: absolute; top: -28px; left: 0;
  background: #00a8ff; color: #fff; font-size: 12px;
  padding: 4px 10px; border-radius: 4px; white-space: nowrap; pointer-events: none;
}
.hint {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  background: rgba(0,0,0,0.7); color: #fff; font-size: 14px;
  padding: 12px 20px; border-radius: 8px; pointer-events: none; z-index: 200;
}
</style>
