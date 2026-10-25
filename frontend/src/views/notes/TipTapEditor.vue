<template>
  <NotesEditor ref="editorRef" :model-value="modelValue" v-bind="$attrs" />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { NotesEditor } from '@omniaide/editor'
import { installOmniAideEditorAdapter } from './editorAdapter'

defineOptions({ inheritAttrs: false })
defineProps<{ modelValue: string }>()
installOmniAideEditorAdapter()
const editorRef = ref<any>(null)

defineExpose({
  getJSONContent: () => null,
  getMarkdown: () => (editorRef.value as any)?.getMarkdown?.(),
  applyExternalContent: (...args: any[]) => (editorRef.value as any)?.applyExternalContent?.(...args),
  findQuery: (q: string) => (editorRef.value as any)?.findQuery?.(q),
})
</script>
