<template>
  <div>
    <div
      :class="['tree-item', { active: node.id === currentId && !node.is_folder }]"
      :style="{ paddingLeft: 12 + depth * 16 + 'px' }"
      @click="$emit('select', node.id)"
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'

const props = defineProps<{ node: any; currentId: number | null; depth: number }>()
defineEmits<{ select: [id: number]; createChild: [id: number]; delete: [id: number] }>()

const expanded = ref(true)
const hasChildren = computed(() => props.node.children?.length > 0 || props.node.is_folder)
</script>

<style scoped>
.tree-item { display:flex; align-items:center; gap:4px; padding:8px 12px; cursor:pointer; font-size:13px; transition:background 0.15s; }
.tree-item:hover { background:#f5f7fa; }
.tree-item.active { background:#ecf5ff; color:#409EFF; font-weight:500; }
.toggle { width:14px; text-align:center; flex-shrink:0; font-size:11px; color:#c0c4cc; cursor:pointer; }
.bullet { width:14px; text-align:center; flex-shrink:0; color:#ddd; }
.item-title { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.item-actions { display:none; gap:2px; flex-shrink:0; }
.tree-item:hover .item-actions { display:flex; }
</style>
