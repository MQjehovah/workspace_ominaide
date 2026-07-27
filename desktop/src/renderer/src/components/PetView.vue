<template>
  <div class="pet-wrap" ref="container"
    @dragover.prevent="onDragOver" @dragleave="onDragLeave" @drop.prevent="onDrop"
    @contextmenu.prevent="showContextMenu">
    <div v-if="dropActive" class="drop-zone">📂 放下文件</div>

    <div v-if="contextMenu.show" class="context-menu" :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }">
      <div class="menu-item" @click="doAction('pet')"><span>✋</span> 摸头</div>
      <div class="menu-item" @click="doAction('feed')"><span>🍖</span> 喂食</div>
      <div class="menu-item" @click="doAction('chat')"><span>💬</span> 聊天</div>
      <div class="menu-item" @click="doAction('work')"><span>💻</span> 工作</div>
      <div class="menu-sep"></div>
      <div class="menu-item" @click="doAction('mood')"><span>😊</span> 换心情</div>
      <div class="menu-sep"></div>
      <div class="menu-item" @click="doAction('close')"><span>✕</span> 隐藏</div>
    </div>
    <div class="drag-handle"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { PetEngine } from './pet'

const container = ref<HTMLDivElement>()
const dropActive = ref(false)
const contextMenu = ref({ show: false, x: 0, y: 0 })

let engine: PetEngine | null = null

async function init() {
  const el = container.value!
  engine = new PetEngine(el, {
    modelUrl: 'https://threejs.org/examples/models/gltf/Xbot.glb',
    useDog: false,
    environment: 'none',
    enablePhysics: true,
    enableBehavior: true,
    onReady: () => {
      engine!.interaction.onClick = () => {
        engine?.behavior.pet()
        engine?.hud.showEmotion('😊', 1500)
      }
      engine!.interaction.onMenu = (x, y) => {
        contextMenu.value = { show: true, x, y }
      }
      setTimeout(() => {
        engine?.hud.showBubble('你好！我是你的小狗朋友 🐕', 3000)
        engine?.hud.showEmotion('😊', 2000)
      }, 500)
    },
  })

  await engine.init()
}

function showContextMenu(e: MouseEvent) {
  contextMenu.value = { show: true, x: e.clientX, y: e.clientY }
}

function closeMenu() {
  contextMenu.value.show = false
}

async function doChat() {
  closeMenu()
  engine?.hud.showBubble('让我想想...')
  try {
    const cfg = JSON.parse(localStorage.getItem('ai_chat_config') || '{}')
    const msg = ['今天心情怎么样？', '讲个笑话！', '你在干什么？', '有什么好玩的？'][Math.floor(Math.random() * 4)]
    let reply: string
    if (cfg.mode === 'backend') {
      const token = await (window as any).mqbox?.config?.get('token') || ''
      const su = await (window as any).mqbox?.config?.get('serverUrl') || 'http://localhost:8000'
      const r = await fetch(`${su}/api/chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
        body: JSON.stringify({ message: msg, history: [] }),
      })
      const data = await r.json()
      reply = data.reply || data.response || '汪~'
    } else reply = `汪~ ${msg}`
    engine?.hud.showBubble(reply, 4000)
    if (reply.includes('笑') || reply.includes('开心')) engine?.behavior.modifyMood({ happy: 10, excited: 5 })
  } catch {
    engine?.hud.showBubble('网络不太好...', 2000)
  }
}

function doAction(a: string) {
  closeMenu()
  switch (a) {
    case 'pet':
      engine?.behavior.pet()
      break
    case 'feed':
      engine?.behavior.feed()
      break
    case 'chat':
      doChat()
      break
    case 'work':
      engine?.fsm.transition('work')
      engine?.hud.showBubble('💻 工作中...', 2000)
      setTimeout(() => engine?.fsm.transition('idle'), 3000)
      break
    case 'mood':
      engine?.behavior.setMood(['happy', 'sad', 'sleepy', 'excited'][Math.floor(Math.random() * 4)] as any)
      break
    case 'close':
      (window as any).mqbox?.window?.hide()
      break
  }
}

let dragCount = 0
function onDragOver() { dropActive.value = true; dragCount++ }
function onDragLeave() { dragCount--; if (dragCount <= 0) { dragCount = 0; dropActive.value = false } }
function onDrop(e: DragEvent) {
  dragCount = 0; dropActive.value = false
  engine?.behavior.pet()
  const files = e.dataTransfer?.files
  if (!files || files.length === 0) return
  for (const f of Array.from(files)) {
    engine?.hud.showBubble(`📎 ${f.name}`, 2000)
    const path = (f as any).path
    if (path) (window as any).mqbox?.shell?.moveToTrash(path)
      .then((r: any) => { engine?.hud.showBubble(r?.success ? '已移到回收站 ♻️' : '删除失败', 2000) })
      .catch(() => {})
  }
}

document.addEventListener('click', (e) => {
  if (contextMenu.value.show && !(e.target as HTMLElement)?.closest('.context-menu')) {
    contextMenu.value.show = false
  }
})

onMounted(async () => {
  try {
    await init()
  } catch (e: any) {
    console.error('[PetView] init error:', e)
    const el = container.value
    if (el) {
      el.innerHTML = `<div style="color:red;padding:20px;font-size:12px">Error: ${e.message || e}</div>`
    }
  }
})
onUnmounted(() => {
  engine?.dispose()
  engine = null
})
</script>

<style>
*{margin:0;padding:0;box-sizing:border-box;user-select:none}
.pet-wrap{width:100vw;height:100vh;position:relative;overflow:hidden;background:transparent;-webkit-app-region:drag;transition:opacity 0.5s}
canvas{display:block;-webkit-app-region:no-drag}

.drop-zone{position:absolute;inset:8px;border:2px dashed rgba(68,255,136,0.5);border-radius:14px;background:rgba(68,255,136,0.06);display:flex;align-items:center;justify-content:center;font-size:14px;color:rgba(68,255,136,0.7);z-index:50;pointer-events:none;backdrop-filter:blur(3px);-webkit-app-region:no-drag}

.context-menu{position:fixed;background:rgba(255,255,255,0.96);border-radius:10px;box-shadow:0 4px 20px rgba(0,0,0,0.18);padding:4px;z-index:100;min-width:150px;backdrop-filter:blur(8px);-webkit-app-region:no-drag}
.menu-item{padding:8px 14px;font-size:12px;color:#333;cursor:pointer;border-radius:6px;display:flex;align-items:center;gap:8px}
.menu-item:hover{background:#f0f4ff}
.menu-sep{height:1px;background:#eee;margin:3px 6px}
.drag-handle{position:fixed;bottom:0;left:0;right:0;height:20px;-webkit-app-region:drag;z-index:20;cursor:move}
.drag-handle:hover{background:rgba(255,255,255,0.08)}
</style>
