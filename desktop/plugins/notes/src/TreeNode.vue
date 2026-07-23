<template>
  <div
    :class="['tree-node', { 'drag-over-top': dropPos === 'before', 'drag-over-bottom': dropPos === 'after', 'drag-over-inside': dropPos === 'inside' }]"
  >
    <div
      :class="['tree-item', { active: node.id === currentId && !node.is_folder, dragging: isDragging }]"
      :style="{ paddingLeft: 16 + depth * 16 + 'px' }"
      :draggable="!node.is_folder"
      @click="$emit('select', node.id)"
      @dragstart="onDragStart"
      @dragend="onDragEnd"
      @dragover.prevent="onDragOver"
      @dragenter.prevent="onDragEnter"
      @dragleave="onDragLeave"
      @drop.prevent="onDrop"
    >
      <span v-if="hasChildren" class="toggle" @click.stop="expanded = !expanded">
        {{ expanded ? '▾' : '▸' }}
      </span>
      <span v-else class="bullet">·</span>
      <span class="item-title">{{ node.title || '无标题' }}</span>
      <div class="item-actions" @click.stop>
        <button v-if="!node.is_folder" class="small-btn" title="新建子笔记" @click="$emit('createChild', node.id)">+</button>
        <button class="small-btn" title="删除" @click="$emit('delete', node.id)">×</button>
      </div>
    </div>
    <div v-if="hasChildren && expanded">
      <TreeNode
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :current-id="currentId"
        :depth="depth + 1"
        @select="(id: number) => $emit('select', id)"
        @create-child="(id: number) => $emit('createChild', id)"
        @delete="(id: number) => $emit('delete', id)"
        @move="(src, tgt, pos) => $emit('move', src, tgt, pos)"
      />
      <div v-if="node.children.length === 0 && node.is_folder" class="empty-hint" :style="{ paddingLeft: 32 + depth * 16 + 'px' }">空文件夹</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const props = defineProps<{
  node: any
  currentId: number | null
  depth: number
}>()

const emit = defineEmits<{
  select: [id: number]
  createChild: [id: number]
  delete: [id: number]
  move: [sourceId: number, targetId: number, position: 'before' | 'after' | 'inside']
}>()

const expanded = ref(true)
const isDragging = ref(false)
const dropPos = ref<'before' | 'after' | 'inside' | null>(null)
const hasChildren = computed(() => props.node.children?.length > 0 || props.node.is_folder)

function onDragStart(e: DragEvent) {
  if (!e.dataTransfer) return
  isDragging.value = true
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', String(props.node.id))
}

function onDragEnd() {
  isDragging.value = false
  dropPos.value = null
}

function onDragOver(e: DragEvent) {
  if (!e.dataTransfer) return
  const srcId = Number(e.dataTransfer.getData('text/plain'))
  if (srcId === props.node.id) return
  e.dataTransfer.dropEffect = 'move'

  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
  const y = e.clientY - rect.top
  const h = rect.height

  if (props.node.is_folder) {
    if (y < h * 0.25) {
      dropPos.value = 'before'
    } else {
      dropPos.value = 'inside'
    }
  } else {
    if (y < h * 0.3) {
      dropPos.value = 'before'
    } else if (y > h * 0.7) {
      dropPos.value = 'after'
    } else {
      dropPos.value = 'inside'
    }
  }
}

function onDragEnter(e: DragEvent) {
  if (!e.dataTransfer) return
  const srcId = Number(e.dataTransfer.getData('text/plain'))
  if (srcId === props.node.id) return
}

function onDragLeave() {
  dropPos.value = null
}

function onDrop(e: DragEvent) {
  if (!e.dataTransfer) return
  const srcId = Number(e.dataTransfer.getData('text/plain'))
  if (srcId === props.node.id) return
  const pos = dropPos.value
  dropPos.value = null
  isDragging.value = false
  if (pos) emit('move', srcId, props.node.id, pos)
}
</script>

<style scoped>
.tree-node { position: relative; }
.tree-node.drag-over-top > .tree-item { border-top: 2px solid #0078D4; }
.tree-node.drag-over-bottom > .tree-item { border-bottom: 2px solid #0078D4; }
.tree-node.drag-over-inside > .tree-item { background: #e3f2fd; outline: 2px dashed #0078D4; outline-offset: -2px; }

.tree-item { display:flex; align-items:center; gap:4px; padding:6px 12px; cursor:pointer; font-size:13px; position:relative; transition: border-color 0.1s; }
.tree-item:hover { background:#f5f7fa; }
.tree-item.active { background:#e3f2fd; color:#0078D4; font-weight:500; }
.tree-item.dragging { opacity:0.4; }
.toggle { width:18px; text-align:center; flex-shrink:0; font-size:14px; color:#999; cursor:pointer; }
.bullet { width:18px; text-align:center; flex-shrink:0; color:#bbb; font-size:14px; }
.item-title { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.item-actions { display:none; gap:2px; flex-shrink:0; }
.tree-item:hover .item-actions { display:flex; }
.small-btn { width:18px; height:18px; border:none; background:transparent; cursor:pointer; font-size:14px; color:#999; display:flex; align-items:center; justify-content:center; border-radius:3px; padding:0; line-height:1; }
.small-btn:hover { background:#ddd; color:#333; }
.empty-hint { font-size:11px; color:#ccc; padding:4px 0; }
</style>
