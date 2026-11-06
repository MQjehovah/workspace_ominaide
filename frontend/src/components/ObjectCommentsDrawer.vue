<template>
  <el-drawer
    :model-value="modelValue"
    :title="title || '评论与材料'"
    size="420px"
    append-to-body
    @update:model-value="(value: boolean) => emit('update:modelValue', value)"
  >
    <ObjectComments
      v-if="type && objectId"
      :type="type"
      :object-id="objectId"
      :title="title"
    />
  </el-drawer>
</template>

<script setup lang="ts">
import ObjectComments from './ObjectComments.vue'

defineProps<{
  modelValue: boolean
  type: string
  objectId: number
  title?: string
}>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
</script>
