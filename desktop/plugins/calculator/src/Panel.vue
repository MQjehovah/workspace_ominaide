<template>
  <div class="calc-panel rounded-lg bg-white border border-gray-200 p-2.5 flex flex-col gap-2">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2">
        <div class="w-8 h-8 rounded-lg bg-purple-100 flex items-center justify-center">
          <svg class="w-4.5 h-4.5 text-purple-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect width="7" height="7" x="3" y="3" rx="1" />
            <rect width="7" height="7" x="14" y="3" rx="1" />
            <rect width="7" height="7" x="14" y="14" rx="1" />
            <rect width="7" height="7" x="3" y="14" rx="1" />
          </svg>
        </div>
        <span class="text-sm text-gray-800 font-semibold">计算器</span>
      </div>
    </div>
    <div class="flex gap-1.5">
      <input
        type="text"
        v-model="expr"
        class="flex-1 h-9 rounded bg-gray-100 border-none px-2.5 text-sm outline-none"
        placeholder="输入表达式..."
        @keyup.enter="calc"
      />
      <button
        class="w-9 h-9 rounded bg-purple-600 flex items-center justify-center hover:bg-purple-700"
        @click="calc"
      >
        <svg class="w-4 h-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M5 12h14M12 5l7 7-7 7" />
        </svg>
      </button>
    </div>
    <div v-if="result !== null" class="text-sm text-purple-600 font-mono">
      = {{ result }}
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref } from 'vue'

export default defineComponent({
  name: 'CalculatorPanel',
  props: {
    data: { type: Object, default: null },
    execute: { type: Function, default: null },
    openPage: { type: Function, default: null },
    refresh: { type: Function, default: null }
  },
  setup(props) {
    const expr = ref((props.data as any)?.input || '')
    const result = ref<string | null>(null)

    function calc() {
      if (!expr.value.trim()) return
      try {
        const res = Function('"use strict"; return (' + expr.value + ')')()
        result.value = String(res)
      } catch {
        result.value = '错误'
      }
    }

    return { expr, result, calc }
  }
})
</script>
