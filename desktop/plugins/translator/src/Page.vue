<template>
  <div class="tr-page">
    <div class="tr-head">
      <span class="tr-title">翻译助手</span>
      <div class="tr-targets">
        <button v-for="t in targets" :key="t.code" class="tr-target" :class="{ active: target === t.code }" @click="target = t.code">
          {{ t.label }}
        </button>
      </div>
    </div>

    <div class="tr-body">
      <div class="tr-col">
        <textarea v-model="source" class="tr-input" placeholder="输入或粘贴要翻译的文本…" @input="onInput"></textarea>
      </div>
      <div class="tr-col">
        <div class="tr-result" :class="{ loading: loading }">
          <span v-if="loading" class="tr-loader"></span>
          <template v-else-if="result">{{ result }}</template>
          <template v-else>
            <span style="color:#999;font-size:12px">翻译结果将显示在这里</span>
          </template>
        </div>
      </div>
    </div>

    <div v-if="error" class="tr-error">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const props = defineProps<{ data: any; execute: (a: string, args?: any) => Promise<any>; close: Function; refresh: Function }>()

const targets = [
  { code: 'zh', label: '中' }, { code: 'en', label: '英' }, { code: 'ja', label: '日' },
  { code: 'ko', label: '韩' }, { code: 'fr', label: '法' }, { code: 'de', label: '德' },
  { code: 'es', label: '西' }, { code: 'ru', label: '俄' },
]
const source = ref('')
const target = ref('zh')
const result = ref('')
const error = ref('')
const loading = ref(false)
let timer: any = null

async function doTranslate() {
  const text = source.value.trim()
  if (!text) { result.value = ''; return }
  loading.value = true
  error.value = ''
  const res = await props.execute('translate', { text, target: target.value })
  if (res?.success) result.value = res.translated
  else error.value = res?.error || '翻译失败'
  loading.value = false
}

function onInput() {
  if (timer) clearTimeout(timer)
  timer = setTimeout(doTranslate, 700)
}

onMounted(() => { props.refresh() })
</script>

<style scoped>
.tr-page { height:100vh; display:flex; flex-direction:column; padding:16px; box-sizing:border-box; font-family:-apple-system,'Segoe UI',sans-serif; }
.tr-head { display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; }
.tr-title { font-size:16px; font-weight:700; color:#1a1a2e; }
.tr-targets { display:flex; gap:4px; }
.tr-target { padding:4px 10px; border-radius:6px; border:none; background:#f0f1f5; color:#666; cursor:pointer; font-size:12px; }
.tr-target:hover { background:#e4e7ef; }
.tr-target.active { background:#6366f1; color:#fff; }
.tr-body { flex:1; display:flex; gap:12px; min-height:0; }
.tr-col { flex:1; min-width:0; display:flex; flex-direction:column; }
.tr-input { flex:1; resize:none; border:1px solid #e0e3ec; border-radius:10px; padding:12px; font-size:14px; line-height:1.6; outline:none; background:#fff; }
.tr-input:focus { border-color:#6366f1; }
.tr-result { flex:1; border:1px solid #e0e3ec; border-radius:10px; padding:12px; font-size:14px; line-height:1.6; background:#fafbfd; overflow-y:auto; white-space:pre-wrap; word-break:break-word; }
.tr-loader { display:inline-block; width:16px; height:16px; border:2px solid #e0e3ec; border-top-color:#6366f1; border-radius:50%; animation:spin .6s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }
.tr-error { color:#e11d48; font-size:12px; margin-top:8px; }
</style>
