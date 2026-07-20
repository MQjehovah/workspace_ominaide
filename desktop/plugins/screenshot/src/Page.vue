<script setup lang="ts">
interface CaptureRecord {
  id: string
  dataUrl: string
  time: number
  type: string
  width: number
  height: number
}

interface Props {
  data: {
    captures: CaptureRecord[]
  }
  execute: (action: string, args?: unknown) => Promise<unknown>
  close: () => void
}

defineProps<Props>()

const formatTime = (time: number) => {
  if (!time) return ''
  return new Date(time).toLocaleString('zh-CN', { 
    month: '2-digit', 
    day: '2-digit', 
    hour: '2-digit', 
    minute: '2-digit' 
  })
}

const getTypeLabel = (type: string) => {
  const labels: Record<string, string> = {
    region: '区域',
    fullscreen: '全屏'
  }
  return labels[type] || type
}
</script>

<template>
  <div class="screenshot-page flex flex-col h-full">
    <div class="p-4 bg-gray-100 border-b border-gray-200">
      <div class="flex items-center justify-between mb-4">
        <span class="text-sm text-gray-800 font-medium">截图工具</span>
        <span class="text-xs text-gray-400">{{ data?.captures?.length || 0 }} 张截图</span>
      </div>
      
      <div class="flex gap-3">
        <button 
          class="flex-1 h-20 rounded-lg bg-blue-500 text-white flex flex-col items-center justify-center gap-1.5 hover:bg-blue-600"
          @click="execute('region')"
        >
          <svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
            <path d="M9 3v18M3 9h18"/>
          </svg>
          <span class="text-sm font-medium">区域截图</span>
        </button>
        <button 
          class="flex-1 h-20 rounded-lg bg-gray-200 text-gray-700 flex flex-col items-center justify-center gap-1.5 hover:bg-gray-300"
          @click="execute('fullscreen')"
        >
          <svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="2" y="2" width="20" height="20" rx="2"/>
          </svg>
          <span class="text-sm font-medium">全屏截图</span>
        </button>
      </div>
    </div>

    <div class="flex-1 overflow-auto p-2">
      <div v-if="!data?.captures || data.captures.length === 0" class="flex flex-col items-center justify-center h-full text-gray-400">
        <svg class="w-12 h-12 mb-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
          <circle cx="8.5" cy="8.5" r="1.5"/>
          <polyline points="21,15 16,10 5,21"/>
        </svg>
        <span class="text-sm">暂无截图</span>
        <span class="text-xs mt-1">点击上方按钮开始截图</span>
      </div>

      <div v-else class="grid grid-cols-3 gap-2">
        <div 
          v-for="capture in data.captures"
          :key="capture.id"
          class="aspect-video rounded-lg bg-gray-100 overflow-hidden cursor-pointer hover:ring-2 hover:ring-blue-500 relative group"
          @click="execute('open', { dataUrl: capture.dataUrl })"
        >
          <img :src="capture.dataUrl" class="w-full h-full object-cover" />
          <div class="absolute bottom-0 left-0 right-0 bg-black/50 text-white text-xs px-1.5 py-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
            {{ getTypeLabel(capture.type) }} · {{ formatTime(capture.time) }}
          </div>
          <button 
            class="absolute top-1 right-1 w-5 h-5 rounded-full bg-black/50 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-500"
            @click.stop="execute('delete', { id: capture.id })"
          >
            <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <div class="p-3 bg-gray-50 border-t border-gray-200">
      <button 
        class="w-full h-9 rounded-md bg-gray-200 text-gray-600 text-sm font-medium hover:bg-gray-300"
        @click="execute('clear')"
      >
        清空截图历史
      </button>
    </div>
  </div>
</template>

<style scoped>
.screenshot-page {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
</style>
