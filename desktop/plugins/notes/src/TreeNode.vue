<template>
  <div>
    <div
      :class="['tree-item', { active: node.id === currentId && !node.is_folder }]"
      :style="{ paddingLeft: 16 + depth * 16 + 'px' }"
      @click="$emit('select', node.id)"
    >
    <span v-if="hasChildren" class="toggle" @click.stop="expanded = !expanded">
      {{ expanded ? '▾' : '▸' }}
    </span>
    <span v-else class="bullet">·</span>
    <span class="item-title">{{ node.title || '无标题' }}</span>
    <div class="item-actions" @click.stop>
      <button class="small-btn" title="新建子笔记" @click="$emit('createChild', node.id)">+</button>
      <button class="small-btn" title="删除" @click="$emit('delete', node.id)">×</button>
    </div>
  </div>
  <div v-if="hasChildren && expanded && node.children?.length">
      <TreeNode
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :current-id="currentId"
        :depth="depth + 1"
        @select="(id: number) => $emit('select', id)"
        @create-child="(id: number) => $emit('createChild', id)"
        @delete="(id: number) => $emit('delete', id)"
      />
    </div>
    <div v-if="node.is_folder && expanded && !node.children?.length" class="empty-hint" :style="{ paddingLeft: 32 + depth * 16 + 'px' }">
      空文件夹
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

defineEmits<{
  select: [id: number]
  createChild: [id: number]
  delete: [id: number]
}>()

const expanded = ref(true)
const hasChildren = computed(() => props.node.children?.length > 0 || props.node.is_folder)
</script>

<style scoped>
.tree-item { display:flex; align-items:center; gap:4px; padding:6px 12px; cursor:pointer; font-size:13px; position:relative; }
.tree-item:hover { background:#f5f7fa; }
.tree-item.active { background:#e3f2fd; color:#0078D4; font-weight:500; }
.toggle { width:14px; text-align:center; flex-shrink:0; font-size:11px; color:#999; }
.bullet { width:14px; text-align:center; flex-shrink:0; color:#bbb; }
.item-title { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.item-actions { display:none; gap:2px; flex-shrink:0; }
.tree-item:hover .item-actions { display:flex; }
.small-btn { width:18px; height:18px; border:none; background:transparent; cursor:pointer; font-size:14px; color:#999; display:flex; align-items:center; justify-content:center; border-radius:3px; padding:0; line-height:1; }
.small-btn:hover { background:#ddd; color:#333; }
.empty-hint { font-size:11px; color:#ccc; padding:4px 0; }
</style>
