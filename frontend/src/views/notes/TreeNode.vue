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
      :class="['tree-item', {
        active: node.id === currentId,
        folder: node.is_folder,
        note: !node.is_folder,
        'has-children': hasChildren,
        dragging: dragging,
      }]"
      :style="{ paddingLeft: 8 + depth * 15 + 'px' }"
      draggable="true"
      @click="onClick"
      @dragstart="onDragStart"
      @dragend="onDragEnd"
      @dragover.prevent="onDragOver"
      @dragleave="onDragLeave"
      @drop.prevent="onDrop"
    >
      <span v-if="hasChildren" class="toggle" @click.stop="expanded = !expanded">
        {{ expanded ? '▾' : '▸' }}
      </span>
      <span v-else class="toggle-spacer"></span>
      <span class="node-icon" :class="{ folder: node.is_folder }">{{ iconOf }}</span>
      <span class="item-title">{{ node.title || '无标题' }}</span>
      <span v-if="node.is_folder" class="folder-badge">文件夹</span>
      <div class="item-actions" @click.stop>
        <el-button text size="small" :icon="Plus" @click="$emit('createChild', node.id)" />
        <el-popconfirm title="确定删除？" @confirm="$emit('delete', node.id)">
          <template #reference>
            <el-button text size="small" :icon="Delete" />
          </template>
        </el-popconfirm>
      </div>
    </div>
    <div v-if="hasChildren && expanded" class="children">
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
    </div>
    <div v-if="node.is_folder && !node.children?.length" class="empty-hint" :style="{ paddingLeft: 34 + depth * 15 + 'px' }">
      空文件夹
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'

const props = defineProps<{ node: any; currentId: number | null; depth: number }>()
const emit = defineEmits<{
  select: [id: number]
  createChild: [id: number]
  delete: [id: number]
  move: [sourceId: number, targetId: number, position: 'before' | 'after' | 'inside']
}>()

// Only the first level starts expanded: rendering the whole 400+ node tree at
// once made the notes page feel slow.
const expanded = ref(props.depth < 1)
const dragging = ref(false)
const dropPos = ref<'before' | 'after' | 'inside' | null>(null)
const hasChildren = computed(() => (props.node.children?.length || 0) > 0)

const iconOf = computed(() => {
  if (props.node.icon) return props.node.icon
  if (props.node.is_folder) return '📁'
  return hasChildren.value ? '📝' : '📄'
})

function contains(node: any, id: number | null): boolean {
  if (!node || id == null) return false
  if (node.id === id) return true
  return (node.children || []).some((child: any) => contains(child, id))
}

// Auto-expand the branch that contains the active note.
watch(() => props.currentId, (id) => {
  if (!expanded.value && contains(props.node, id)) expanded.value = true
}, { immediate: true })

function onClick() {
  if (props.node.is_folder) {
    if (hasChildren.value) expanded.value = !expanded.value
    return
  }
  emit('select', props.node.id)
}

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
    // Folders are top-level workspaces: only reorder them at the root.
    if ((props.node.parent_id ?? null) !== null) {
      dropPos.value = null
      return
    }
    dropPos.value = y < h * 0.5 ? 'before' : 'after'
    return
  }

  if (y < h * 0.28) dropPos.value = 'before'
  else if (y > h * 0.72) dropPos.value = 'after'
  else dropPos.value = 'inside'
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
.tree-node.drag-over-before > .tree-item { box-shadow: inset 0 2px 0 var(--brand-500); }
.tree-node.drag-over-after > .tree-item { box-shadow: inset 0 -2px 0 var(--brand-500); }
.tree-node.drag-over-inside > .tree-item { background: #eef2ff; outline: 2px dashed #a5b4fc; outline-offset: -2px; }

.tree-item {
  display: flex; align-items: center; gap: 4px;
  padding: 6px 8px 6px 0; margin: 1px 0; border-radius: 8px;
  cursor: pointer; font-size: 13px;
  transition: background .15s, color .15s;
}
.tree-item:hover { background: #f4f7fc; }
.tree-item.active { background: #eef2ff; color: #3730a3; font-weight: 600; }
.tree-item.dragging { opacity: .4; }

.tree-item.folder { font-weight: 600; color: #334155; }
.tree-item.folder .item-title { letter-spacing: .1px; }

.toggle {
  width: 16px; text-align: center; flex-shrink: 0;
  font-size: 11px; color: #94a3b8; cursor: pointer;
  transition: color .15s;
}
.toggle:hover { color: #475569; }
.toggle-spacer { width: 16px; flex-shrink: 0; }

.node-icon {
  width: 18px; flex-shrink: 0; text-align: center;
  font-size: 13px; line-height: 1;
}
.node-icon.folder { font-size: 14px; }

.item-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.folder-badge {
  flex-shrink: 0; font-size: 9.5px; font-weight: 500;
  color: #94a3b8; background: #f1f5f9;
  padding: 1px 6px; border-radius: 999px;
}

.item-actions { display: none; gap: 2px; flex-shrink: 0; }
.tree-item:hover .item-actions { display: flex; }
.empty-hint { font-size: 11px; color: #b5bdc9; padding: 3px 0 5px; }

.children { position: relative; }
</style>
