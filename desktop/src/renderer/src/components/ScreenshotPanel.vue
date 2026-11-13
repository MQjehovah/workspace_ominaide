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
// Vue templates cannot access `window`; read the DPR here instead.
const dpr = window.devicePixelRatio || 1

const selectionStyle = computed(() => {
  const sel = selection.value
  if (sel.width < 3 || sel.height < 3) return {} as Record<string, string>
  return {
    position: 'fixed',
    left: `${sel.x}px`,
    top: `${sel.y}px`,
    width: `${sel.width}px`,
    height: `${sel.height}px`,
    border: '2px solid #00a8ff',
    boxSizing: 'border-box',
    // A single huge shadow dims everything outside the hole. Unlike four
    // manually positioned mask blocks, this can never cover the selection.
    boxShadow: '0 0 0 100vmax rgba(0, 0, 0, 0.5)',
    pointerEvents: 'none',
    zIndex: '40',
  } as Record<string, string>
})

onMounted(async () => {
  document.addEventListener('keydown', onKeyDown)
  try {
    const result = await window.mqbox?.screenshot?.getAllScreens()
    if (result) {
      displays.value = result.displays
      images.value = result.images

      // Prefer the explicit display id passed by the main process; fall back
      // to the window position for older builds.
      const queryId = Number(
        new URLSearchParams(window.location.search).get('displayId') || 0,
      )
      const wx = window.screenX || 0
      currentDisplayId.value =
        displays.value.find(d => d.id === queryId)?.id ||
        displays.value.find(d =>
          wx >= d.bounds.x && wx < d.bounds.x + d.bounds.width
        )?.id ||
        displays.value[0]?.id ||
        0

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

const onMouseDown = (e: MouseEvent) => {
  e.preventDefault()
  isSelecting.value = true
  startX.value = e.clientX
  startY.value = e.clientY
  selection.value = { x: e.clientX, y: e.clientY, width: 0, height: 0 }
}

const onMouseMove = (e: MouseEvent) => {
  if (!isSelecting.value) return
  selection.value = {
    x: Math.min(startX.value, e.clientX),
    y: Math.min(startY.value, e.clientY),
    width: Math.abs(e.clientX - startX.value),
    height: Math.abs(e.clientY - startY.value),
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
    const vw = window.innerWidth
    const vh = window.innerHeight
    if (vw <= 0 || vh <= 0) return
    const sel = selection.value
    const result = await window.mqbox?.screenshot?.captureNormalized(
      currentDisplayId.value,
      sel.x / vw,
      sel.y / vh,
      sel.width / vw,
      sel.height / vh,
    )
    if (result) window.mqbox?.screenshot?.cancel()
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
      v-if="!(isSelecting && selection.width > 2 && selection.height > 2)"
      class="dim-mask"
    ></div>

    <div
      v-if="isSelecting && selection.width > 2 && selection.height > 2"
      class="selection-indicator"
      :style="selectionStyle"
    >
      <div class="size-label">{{ Math.round(selection.width * dpr) }} × {{ Math.round(selection.height * dpr) }}</div>
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
.dim-mask { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.5); z-index: 40; pointer-events: none; }
.selection-indicator { z-index: 40; }
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
