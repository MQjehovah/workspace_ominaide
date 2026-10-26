<template>
  <div
    class="tree-node"
    :class="{
      'drag-over-before': dropPos === 'before',
      'drag-over-after': dropPos === 'after',
      'drag-over-inside': dropPos === 'inside',
    }"
  >
    <div
      :class="['tree-item', { active: node.id === currentId && !node.is_folder, dragging: dragging }]"
      :style="{ paddingLeft: 12 + depth * 16 + 'px' }"
      draggable="true"
      @click="$emit('select', node.id)"
      @dragstart="onDragStart"
      @dragend="onDragEnd"
      @dragover.prevent="onDragOver"
      @dragleave="onDragLeave"
      @drop.prevent="onDrop"
    >
      <span v-if="hasChildren" class="toggle" @click.stop="expanded = !expanded">
        {{ expanded ? '▾' : '▸' }}
      </span>
      <span v-else class="bullet">·</span>
      <span class="item-title">{{ node.title || '无标题' }}</span>
      <div class="item-actions" @click.stop>
        <el-button text size="small" :icon="Plus" @click="$emit('createChild', node.id)" />
        <el-popconfirm title="确定删除？" @confirm="$emit('delete', node.id)">
          <template #reference>
            <el-button text size="small" :icon="Delete" />
          </template>
        </el-popconfirm>
      </div>
    </div>
    <div v-if="hasChildren && expanded">
      <TreeNode
        v-for="child in node.children || []"
        :key="child.id"
        :node="child"
        :current-id="currentId"
        :depth="depth + 1"
        @select="(id: number) => $emit('select', id)"
        @create-child="(id: number) => $emit('createChild', id)"
        @delete="(id: number) => $emit('delete', id)"
        @move="(src: number, tgt: number, pos: 'before' | 'after' | 'inside') => $emit('move', src, tgt, pos)"
      />
      <div v-if="node.is_folder && !node.children?.length" class="empty-hint" :style="{ paddingLeft: 30 + depth * 16 + 'px' }">
        空文件夹
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'

const props = defineProps<{ node: any; currentId: number | null; depth: number }>()
const emit = defineEmits<{
  select: [id: number]
  createChild: [id: number]
  delete: [id: number]
  move: [sourceId: number, targetId: number, position: 'before' | 'after' | 'inside']
}>()

const expanded = ref(true)
const dragging = ref(false)
const dropPos = ref<'before' | 'after' | 'inside' | null>(null)
const hasChildren = computed(() => props.node.children?.length > 0 || props.node.is_folder)

function onDragStart(e: DragEvent) {
  if (!e.dataTransfer) return
  dragging.value = true
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', String(props.node.id))
  if (props.node.is_folder) e.dataTransfer.setData('application/x-omni-folder', '1')
}

function onDragOver(e: DragEvent) {
  if (!e.dataTransfer) return
  const srcId = Number(e.dataTransfer.getData('text/plain'))
  if (srcId === props.node.id) return
  e.dataTransfer.dropEffect = 'move'

  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
  const y = e.clientY - rect.top
  const h = rect.height
  const folderSource = Array.from(e.dataTransfer.types).includes('application/x-omni-folder')
  if (folderSource) {
    // Folders are top-level containers: only reorder among root nodes.
    if ((props.node.parent_id ?? null) !== null) {
      dropPos.value = null
      return
    }
    dropPos.value = y < h * 0.5 ? 'before' : 'after'
    return
  }

  if (props.node.is_folder) {
    if (y < h * 0.25) dropPos.value = 'before'
    else if (y > h * 0.75) dropPos.value = 'after'
    else dropPos.value = 'inside'
  } else {
    if (y < h * 0.3) dropPos.value = 'before'
    else if (y > h * 0.7) dropPos.value = 'after'
    else dropPos.value = 'inside'
  }
}

function onDragLeave() {
  dropPos.value = null
}

function onDragEnd() {
  dragging.value = false
  dropPos.value = null
}

function onDrop(e: DragEvent) {
  if (!e.dataTransfer) return
  const srcId = Number(e.dataTransfer.getData('text/plain'))
  const pos = dropPos.value
  dropPos.value = null
  dragging.value = false
  if (srcId && srcId !== props.node.id && pos) emit('move', srcId, props.node.id, pos)
}
</script>

<style scoped>
.tree-node { position: relative; }
.tree-node.drag-over-before > .tree-item { box-shadow: inset 0 2px 0 #2f80ed; }
.tree-node.drag-over-after > .tree-item { box-shadow: inset 0 -2px 0 #2f80ed; }
.tree-node.drag-over-inside > .tree-item { background: #e8f3ff; outline: 2px dashed #2f80ed; outline-offset: -2px; }
.tree-item { display:flex; align-items:center; gap:4px; padding:8px 10px; margin:1px 0; border-radius:8px; cursor:pointer; font-size:13px; transition: background .15s, color .15s; }
.tree-item:hover { background:#f3f7fc; }
.tree-item.active { background:#eaf3ff; color:#1d6fd8; font-weight:600; }
.tree-item.dragging { opacity:.4; }
.toggle { width:16px; text-align:center; flex-shrink:0; font-size:12px; color:#8b95a5; cursor:pointer; }
.bullet { width:16px; text-align:center; flex-shrink:0; color:#c7ced8; }
.item-title { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.item-actions { display:none; gap:2px; flex-shrink:0; }
.tree-item:hover .item-actions { display:flex; }
.empty-hint { font-size:11px; color:#b5bdc9; padding:3px 0 5px; }
</style>
