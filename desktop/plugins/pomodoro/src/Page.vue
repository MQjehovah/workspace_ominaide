<template>
  <div class="po-page">
    <div class="po-head">
      <span class="po-title">番茄钟</span>
      <div class="po-presets">
        <button :class="{ active: focusMin === 25 }" @click="setDur(25)">25分</button>
        <button :class="{ active: focusMin === 45 }" @click="setDur(45)">45分</button>
        <button :class="{ active: focusMin === 60 }" @click="setDur(60)">60分</button>
      </div>
    </div>

    <div class="po-timer-wrap">
      <div class="po-ring" :class="state.mode">
        <div class="po-time">{{ timeStr }}</div>
        <div class="po-mode">{{ state.mode === 'focus' ? '专注' : '休息' }}</div>
      </div>
    </div>

    <div class="po-actions">
      <button v-if="!state.running" class="po-btn primary" @click="start">开始专注</button>
      <button v-else class="po-btn warning" @click="reset">结束</button>
    </div>

    <div class="po-info">
      今日已完成 <b>{{ completedToday }}</b> 轮专注
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps<{ data: any; execute: (a: string, args?: any) => Promise<any>; close: Function; refresh: Function }>()

const state = ref<any>({ running: false, mode: 'focus', focusMin: 25, breakMin: 5, endAt: 0, remainingMs: 0 })
const completedToday = ref(0)

function tick() {
  props.refresh()
  // Also recompute local remaining for display
}

const timeStr = computed(() => {
  const s = state.value
  if (!s.running) return `${String(s.focusMin).padStart(2, '0')}:00`
  const ms = s.remainingMs
  const m = Math.floor(ms / 60000)
  const sec = Math.floor((ms % 60000) / 1000)
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
})

async function start() {
  await props.execute('start', { focusMin: state.value.focusMin, breakMin: state.value.breakMin })
  props.refresh()
}

async function reset() {
  await props.execute('reset')
  props.refresh()
}

async function setDur(m: number) {
  await props.execute('setDuration', { focusMin: m })
  state.value.focusMin = m
}

let timer: any = null
onMounted(() => {
  props.refresh()
  timer = setInterval(() => {
    props.refresh()
    // Refresh local remaining estimate every second for the ticking display.
    if (state.value.running) {
      state.value.remainingMs = Math.max(0, state.value.endAt - Date.now())
    }
  }, 1000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.po-page { height:100vh; display:flex; flex-direction:column; align-items:center; padding:24px; box-sizing:border-box; font-family:-apple-system,'Segoe UI',sans-serif; }
.po-head { width:100%; display:flex; align-items:center; justify-content:space-between; }
.po-title { font-size:16px; font-weight:700; color:#1a1a2e; }
.po-presets { display:flex; gap:4px; }
.po-presets button { padding:4px 10px; border:none; border-radius:6px; background:#f0f1f5; color:#666; cursor:pointer; font-size:12px; }
.po-presets button.active { background:#6366f1; color:#fff; }
.po-timer-wrap { flex:1; display:flex; align-items:center; justify-content:center; }
.po-ring { width:200px; height:200px; border-radius:50%; display:flex; flex-direction:column; align-items:center; justify-content:center; box-shadow:8px 8px 20px rgba(99,102,241,0.2),-8px -8px 20px #fff,inset 2px 2px 6px rgba(0,0,0,0.05); background:#f0f1f5; }
.po-ring.focus { border:4px solid #6366f1; }
.po-ring.break { border:4px solid #10b981; }
.po-time { font-size:40px; font-weight:700; color:#1a1a2e; font-variant-numeric:tabular-nums; }
.po-mode { margin-top:6px; font-size:14px; color:#909399; }
.po-actions { display:flex; gap:8px; }
.po-btn { padding:10px 28px; border:none; border-radius:24px; font-size:14px; font-weight:600; cursor:pointer; }
.po-btn.primary { background:#6366f1; color:#fff; }
.po-btn.warning { background:#e11d48; color:#fff; }
.po-info { margin-top:16px; font-size:12px; color:#909399; }
</style>
