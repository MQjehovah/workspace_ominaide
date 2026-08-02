<template>
  <div class="sm-page">
    <div class="sm-head">
      <span class="sm-title">系统监控</span>
      <span class="sm-sub" v-if="stats">{{ stats.platform }} · 运行 {{ stats.uptime }}</span>
    </div>

    <!-- CPU & Memory -->
    <div class="sm-row">
      <div class="sm-card">
        <div class="sm-label">CPU</div>
        <div class="sm-big" :style="{ color: color(stats?.cpu) }">{{ stats?.cpu ?? '—' }}%</div>
        <div class="sm-bar"><div class="sm-bar-fill" :style="{ width: bar(stats?.cpu), background: color(stats?.cpu) }"></div></div>
      </div>
      <div class="sm-card">
        <div class="sm-label">内存</div>
        <div class="sm-big" :style="{ color: color(stats?.mem?.percent) }">{{ stats?.mem?.percent ?? '—' }}%</div>
        <div class="sm-bar"><div class="sm-bar-fill" :style="{ width: bar(stats?.mem?.percent), background: color(stats?.mem?.percent) }"></div></div>
        <div class="sm-small">{{ stats?.mem?.usedGB }}/{{ stats?.mem?.totalGB }} GB</div>
      </div>
    </div>

    <!-- GPU -->
    <div class="sm-card" v-if="stats?.gpu" style="margin-bottom:10px">
      <div class="sm-label">GPU · {{ stats.gpu }}</div>
      <div class="sm-row-inline">
        <span class="sm-big2" v-if="stats.gpuUtil != null">{{ stats.gpuUtil }}%</span>
        <span class="sm-small" v-if="stats.gpuMem">{{ stats.gpuMem }}</span>
        <span class="sm-small" v-else>无利用率数据</span>
      </div>
    </div>

    <!-- Disks -->
    <div class="sm-card" v-if="stats?.disks?.length" style="margin-bottom:10px">
      <div class="sm-label">磁盘</div>
      <div v-for="d in stats.disks" :key="d.drive" class="sm-disk">
        <div class="sm-disk-top">
          <span class="sm-disk-name">{{ d.drive }}</span>
          <span class="sm-disk-meta">{{ d.used }} / {{ d.total }} GB · {{ d.percent }}%</span>
        </div>
        <div class="sm-bar"><div class="sm-bar-fill" :style="{ width: d.percent + '%', background: color(d.percent) }"></div></div>
      </div>
    </div>

    <!-- Cleanup -->
    <div class="sm-clean">
      <div class="sm-clean-title">清理</div>
      <div class="sm-clean-actions">
        <button class="sm-btn" :disabled="cleaning" @click="cleanMemory">
          {{ cleaning === 'mem' ? '清理中…' : '🧹 清理内存' }}
        </button>
        <button class="sm-btn" :disabled="cleaning" @click="cleanDisk">
          {{ cleaning === 'disk' ? '清理中…' : '🧹 清理临时文件' }}
        </button>
      </div>
      <div v-if="cleanResult" class="sm-result">{{ cleanResult }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const props = defineProps<{ data: any; execute: (a: string, args?: any) => Promise<any>; close: Function; refresh: Function }>()

const stats = ref<any>(null)
const cleaning = ref('')
const cleanResult = ref('')

function color(p: number | undefined): string {
  if (p == null) return '#909399'
  if (p > 80) return '#e11d48'
  if (p > 50) return '#f59e0b'
  return '#10b981'
}
function bar(p: number | undefined): string {
  return Math.min(100, Math.max(0, p || 0)) + '%'
}

async function load() {
  const r = await props.execute('getPageData')
  if (r?.stats) stats.value = r.stats
}

async function cleanMemory() {
  cleaning.value = 'mem'
  cleanResult.value = ''
  const r = await props.execute('cleanMemory')
  if (r?.success) cleanResult.value = `内存占用 ${r.before}% → ${r.after}%`
  cleaning.value = ''
  await load()
}

async function cleanDisk() {
  cleaning.value = 'disk'
  cleanResult.value = ''
  const r = await props.execute('cleanDisk')
  if (r?.success) cleanResult.value = r.freedMB > 0 ? `释放 ${r.freedMB} MB` : '无临时文件可清理'
  cleaning.value = ''
  await load()
}

let timer: any = null
onMounted(() => {
  load()
  timer = setInterval(load, 5000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.sm-page { height:100vh; padding:16px; box-sizing:border-box; overflow-y:auto; font-family:-apple-system,'Segoe UI',sans-serif; background:#f5f6f8; }
.sm-head { display:flex; align-items:baseline; gap:10px; margin-bottom:14px; }
.sm-title { font-size:17px; font-weight:700; color:#1a1a2e; }
.sm-sub { font-size:12px; color:#909399; }
.sm-row { display:flex; gap:10px; margin-bottom:10px; }
.sm-card { flex:1; background:#fff; border-radius:10px; padding:12px 14px; box-shadow:0 1px 4px rgba(0,0,0,0.05); }
.sm-label { font-size:12px; color:#666; margin-bottom:4px; }
.sm-big { font-size:28px; font-weight:700; }
.sm-big2 { font-size:22px; font-weight:700; }
.sm-small { font-size:11px; color:#909399; margin-top:4px; }
.sm-row-inline { display:flex; align-items:baseline; gap:12px; }
.sm-bar { height:8px; background:#eef0f4; border-radius:4px; overflow:hidden; margin-top:6px; }
.sm-bar-fill { height:100%; border-radius:4px; transition:width .5s; }
.sm-disk { margin-bottom:8px; }
.sm-disk-top { display:flex; justify-content:space-between; align-items:center; margin-bottom:2px; }
.sm-disk-name { font-size:13px; font-weight:600; color:#333; }
.sm-disk-meta { font-size:11px; color:#909399; }
.sm-clean { background:#fff; border-radius:10px; padding:12px 14px; box-shadow:0 1px 4px rgba(0,0,0,0.05); margin-top:10px; }
.sm-clean-title { font-size:12px; color:#666; margin-bottom:8px; }
.sm-clean-actions { display:flex; gap:8px; }
.sm-btn { flex:1; padding:9px 0; border:none; border-radius:8px; font-size:13px; font-weight:600; cursor:pointer; background:#6366f1; color:#fff; }
.sm-btn:hover { filter:brightness(1.08); }
.sm-btn:disabled { opacity:.5; cursor:not-allowed; }
.sm-result { margin-top:8px; font-size:12px; color:#10b981; }
</style>
