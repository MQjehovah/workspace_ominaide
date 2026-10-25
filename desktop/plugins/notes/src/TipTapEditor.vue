<template>
  <NotesEditor ref="editorRef" :model-value="modelValue" v-bind="$attrs" />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { NotesEditor } from '../../../../frontend/src/components/editor/index'
import { installDesktopEditorAdapter } from './editorAdapter'

defineOptions({ inheritAttrs: false })
defineProps<{ modelValue: string }>()
installDesktopEditorAdapter()
const editorRef = ref<any>(null)

defineExpose({
  getJSONContent: () => null,
  getMarkdown: () => (editorRef.value as any)?.getMarkdown?.(),
  applyExternalContent: (...args: any[]) => (editorRef.value as any)?.applyExternalContent?.(...args),
  prepareForPrint: () => (editorRef.value as any)?.prepareForPrint?.(),
  finishPrint: () => (editorRef.value as any)?.finishPrint?.(),
  findQuery: (q: string) => (editorRef.value as any)?.findQuery?.(q),
})
</script>
