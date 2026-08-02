<template>
  <div class="ql-page">
    <div class="ql-head">
      <div class="ql-title">
        <h2>快捷指令</h2>
        <span class="ql-sub">{{ links.length }} 个 · 一键打开软件 / 网页 / 脚本</span>
      </div>
      <button class="ql-add" @click="openEdit()">+ 新建</button>
    </div>

    <div class="ql-list">
      <div v-for="(link, i) in links" :key="link.id" class="ql-item">
        <div class="ql-icon" :style="{ background: link.color || typeMeta[link.type]?.color }">
          <span>{{ link.icon || typeMeta[link.type]?.icon || '⌨️' }}</span>
        </div>
        <div class="ql-info">
          <div class="ql-name">{{ link.name || '未命名' }}</div>
          <div class="ql-target">{{ typeMeta[link.type]?.label || link.type }} · {{ link.target }}</div>
        </div>
        <div class="ql-actions">
          <button class="ql-run" title="运行" @click="run(link)">▶</button>
          <button class="ql-op" title="上移" @click="move(link, -1)" :disabled="i === 0">↑</button>
          <button class="ql-op" title="下移" @click="move(link, 1)" :disabled="i === links.length - 1">↓</button>
          <button class="ql-op" title="编辑" @click="openEdit(link)">✎</button>
          <button class="ql-op danger" title="删除" @click="remove(link)">✕</button>
        </div>
      </div>
      <div v-if="links.length === 0" class="ql-empty">还没有快捷指令，点击右上角「+ 新建」添加</div>
    </div>

    <div v-if="showEditor" class="ql-mask" @click.self="showEditor = false">
      <div class="ql-editor">
        <h3>{{ editing?.id ? '编辑' : '新建' }}快捷指令</h3>

        <label class="fld">名称</label>
        <input v-model="form.name" class="inp" placeholder="例如：VSCode / 博客后台 / 备份脚本" />

        <label class="fld">类型</label>
        <div class="type-row">
          <button
            v-for="(meta, key) in typeMeta"
            :key="key"
            class="type-btn"
            :class="{ active: form.type === key }"
            @click="form.type = key"
          >
            {{ meta.icon }} {{ meta.label }}
          </button>
        </div>

        <label class="fld">{{ targetLabel }}</label>
        <input v-model="form.target" class="inp" :placeholder="targetPlaceholder" />
        <div class="hint">{{ targetHint }}</div>

        <label v-if="form.type === 'script'" class="fld">参数（可选，空格分隔）</label>
        <input v-if="form.type === 'script'" v-model="form.args" class="inp" placeholder="例如：--clean --force" />

        <div class="ed-actions">
          <button class="btn ghost" @click="showEditor = false">取消</button>
          <button class="btn primary" @click="save">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

const props = defineProps<{ data: any; execute: (a: string, args?: any) => Promise<any>; close: () => void }>()

const links = ref<any[]>([])
const typeMeta = ref<any>({})
const showEditor = ref(false)
const editing = ref<any>(null)
const form = ref({ name: '', type: 'command', target: '', args: '', icon: '', color: '' })

watch(() => props.data, (d) => {
  links.value = d?.links || []
  typeMeta.value = d?.typeMeta || {}
}, { immediate: true })

const targetLabel = computed(() => {
  if (form.value.type === 'app') return '应用路径或启动命令'
  if (form.value.type === 'url') return '网址'
  if (form.value.type === 'folder') return '文件夹路径'
  if (form.value.type === 'script') return '脚本路径'
  return '命令内容'
})

const targetPlaceholder = computed(() => {
  if (form.value.type === 'app') return 'C:\\Program Files\\...\\app.exe 或 vscode'
  if (form.value.type === 'url') return 'https://example.com'
  if (form.value.type === 'folder') return 'D:\\Projects\\my-app'
  if (form.value.type === 'script') return 'D:\\scripts\\backup.ps1 或 .bat'
  return 'git pull / npm run dev / 任意命令'
})

const targetHint = computed(() => {
  if (form.value.type === 'url') return '用系统默认浏览器打开'
  if (form.value.type === 'app') return '填 exe 路径用系统打开；填名字需在 PATH 中'
  if (form.value.type === 'folder') return '用资源管理器打开'
  if (form.value.type === 'script') return '支持 .ps1 / .bat / .cmd / .exe'
  return '通过 cmd.exe 执行，含参数直接写全'
})

function openEdit(link?: any) {
  if (link) {
    editing.value = link
    form.value = { name: link.name || '', type: link.type || 'command', target: link.target || '', args: link.args || '', icon: link.icon || '', color: link.color || '' }
  } else {
    editing.value = null
    form.value = { name: '', type: 'command', target: '', args: '', icon: '', color: '' }
  }
  showEditor.value = true
}

async function save() {
  if (!form.value.target.trim()) return
  if (editing.value?.id) {
    await props.execute('update', { id: editing.value.id, patch: { ...form.value } })
  } else {
    await props.execute('add', { ...form.value })
  }
  showEditor.value = false
}

async function run(link: any) {
  await props.execute('run', { id: link.id })
}

async function move(link: any, dir: number) {
  await props.execute('move', { id: link.id, dir })
}

async function remove(link: any) {
  if (confirm(`删除「${link.name}」？`)) await props.execute('remove', { id: link.id })
}
</script>

<style scoped>
.ql-page { height: 100vh; display: flex; flex-direction: column; background: #eef1f6; padding: 16px 20px; font-family: system-ui, "Microsoft YaHei", sans-serif; overflow: hidden; }
.ql-head { display: flex; align-items: center; justify-content: space-between; padding: 6px 0 14px; }
.ql-title h2 { font-size: 18px; color: #2c3550; margin: 0; }
.ql-sub { font-size: 12px; color: #8a94a8; }
.ql-add { background: #6366f1; color: #fff; border: none; border-radius: 10px; padding: 8px 14px; font-size: 13px; cursor: pointer; box-shadow: 0 3px 10px rgba(99,102,241,.35); }
.ql-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
.ql-item { display: flex; align-items: center; gap: 12px; background: #fff; border-radius: 12px; padding: 10px 12px; box-shadow: 0 2px 6px rgba(30,41,59,.06); }
.ql-icon { width: 42px; height: 42px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 20px; flex-shrink: 0; }
.ql-info { flex: 1; min-width: 0; }
.ql-name { font-size: 14px; font-weight: 600; color: #2c3550; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ql-target { font-size: 12px; color: #8a94a8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ql-actions { display: flex; gap: 6px; }
.ql-run { background: #10b981; color: #fff; border: none; border-radius: 8px; width: 30px; height: 30px; cursor: pointer; font-size: 13px; }
.ql-op { background: #f1f5f9; color: #475569; border: none; border-radius: 8px; width: 30px; height: 30px; cursor: pointer; font-size: 13px; }
.ql-op.danger { color: #ef4444; }
.ql-op:disabled { opacity: .35; cursor: default; }
.ql-empty { color: #8a94a8; text-align: center; padding: 40px 0; font-size: 13px; }

.ql-mask { position: fixed; inset: 0; background: rgba(15,23,42,.4); display: flex; align-items: center; justify-content: center; z-index: 50; }
.ql-editor { background: #fff; border-radius: 16px; padding: 20px 22px; width: 380px; max-height: 90vh; overflow-y: auto; box-shadow: 0 10px 40px rgba(15,23,42,.25); }
.ql-editor h3 { margin: 0 0 14px; font-size: 16px; color: #2c3550; }
.fld { display: block; font-size: 12px; color: #64748b; margin: 10px 0 4px; }
.inp { width: 100%; border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 10px; font-size: 13px; outline: none; box-sizing: border-box; }
.inp:focus { border-color: #6366f1; }
.hint { font-size: 11px; color: #94a3b8; margin-top: 4px; }
.type-row { display: flex; gap: 6px; flex-wrap: wrap; }
.type-btn { border: 1px solid #e2e8f0; background: #fff; border-radius: 8px; padding: 6px 10px; font-size: 12px; cursor: pointer; color: #475569; }
.type-btn.active { border-color: #6366f1; background: #eef2ff; color: #4f46e5; }
.ed-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.btn { border: none; border-radius: 8px; padding: 8px 16px; font-size: 13px; cursor: pointer; }
.btn.ghost { background: #f1f5f9; color: #475569; }
.btn.primary { background: #6366f1; color: #fff; }
</style>
