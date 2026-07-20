<template>
  <div class="overlay" @click.self="$emit('close')">
    <div class="card">
      <div class="card-hd">
        <span>{{ plugin?.manifest?.displayName || pluginId }} 配置</span>
        <button class="close-btn" @click="$emit('close')">✕</button>
      </div>
      <div class="card-body">
        <div class="section">
          <div class="field">
            <label>最大历史记录</label>
            <input v-model.number="config.maxHistory" type="number" min="10" max="500" />
          </div>
          <div class="field">
            <label>自动清理</label>
            <label class="switch"><input v-model="config.autoCleanup" type="checkbox" /><span class="slider"></span></label>
          </div>
        </div>
        <div class="section">
          <div class="section-title">权限</div>
          <div v-for="p in permissions" :key="p" class="perm-item">
            <span class="perm-dot"></span>
            <span>{{ getPermLabel(p) }}</span>
          </div>
        </div>
      </div>
      <div class="card-ft">
        <button class="btn primary" @click="save">保存</button>
        <button class="btn" @click="$emit('close')">取消</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const props = defineProps<{ pluginId: string }>()
const emit = defineEmits<{ close: [] }>()

const plugin = ref<any>(null)
const config = ref<any>({ maxHistory: 100, autoCleanup: false })
const permissions = ref<string[]>([])

function getPermLabel(p: string) {
  const map: Record<string, string> = { clipboard: '剪贴板', notification: '通知', storage: '存储', 'files:read': '读取文件', 'files:write': '写入文件', shell: '打开外部链接', screenshot: '截图' }
  return map[p] || p
}

onMounted(async () => {
  const plugins = await window.mqbox.plugin.list()
  plugin.value = plugins.find((p: any) => p.id === props.pluginId)
  permissions.value = plugin.value?.manifest?.permissions || []
  const saved = await window.mqbox.config.get(`plugins.${props.pluginId}`)
  if (saved) config.value = { ...config.value, ...saved }
})

async function save() {
  await window.mqbox.config.set(`plugins.${props.pluginId}`, config.value)
  emit('close')
}
</script>

<style scoped>
.overlay { position:fixed; inset:0; background:rgba(0,0,0,0.3); display:flex; align-items:center; justify-content:center; z-index:1000; }
.card { width:420px; background:#fff; border-radius:12px; box-shadow:0 4px 24px rgba(0,0,0,0.15); overflow:hidden; }
.card-hd { display:flex; justify-content:space-between; align-items:center; padding:14px 20px; border-bottom:1px solid #e8e8e8; font-weight:600; font-size:14px; -webkit-app-region:drag; }
.close-btn { border:none; background:transparent; cursor:pointer; color:#999; font-size:16px; padding:4px; }
.card-body { padding:20px; max-height:380px; overflow-y:auto; }
.section { margin-bottom:20px; }
.section-title { font-size:12px; font-weight:600; color:#999; margin-bottom:8px; text-transform:uppercase; }
.field { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }
.field label { font-size:13px; color:#333; }
.field input[type=number] { width:80px; padding:6px 10px; border:1px solid #e0e0e0; border-radius:6px; font-size:13px; text-align:right; }
.switch { position:relative; width:40px; height:22px; display:inline-block; }
.switch input { opacity:0; width:0; height:0; }
.slider { position:absolute; cursor:pointer; inset:0; background:#ddd; border-radius:22px; transition:0.2s; }
.slider::before { content:''; position:absolute; height:18px; width:18px; left:2px; bottom:2px; background:#fff; border-radius:50%; transition:0.2s; }
.switch input:checked + .slider { background:#0078D4; }
.switch input:checked + .slider::before { transform:translateX(18px); }
.perm-item { display:flex; align-items:center; gap:8px; padding:6px 0; font-size:12px; color:#666; }
.perm-dot { width:6px; height:6px; border-radius:3px; background:#28A745; }
.card-ft { display:flex; justify-content:flex-end; gap:8px; padding:14px 20px; border-top:1px solid #e8e8e8; }
.btn { padding:8px 20px; border-radius:8px; border:1px solid #e0e0e0; background:#fff; cursor:pointer; font-size:13px; }
.btn.primary { background:#0078D4; color:#fff; border-color:#0078D4; }
.btn.primary:hover { background:#005ea6; }
</style>
