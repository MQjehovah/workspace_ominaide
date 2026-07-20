<template>
  <div class="calc-page p-4">
    <div class="max-w-sm mx-auto">
      <div class="text-lg font-bold mb-3">计算器</div>
      <div class="flex gap-2 mb-3">
        <input type="text" v-model="expr" class="flex-1 h-10 rounded border border-gray-300 px-3 text-base outline-none" placeholder="输入表达式..." @keyup.enter="calc" />
        <button class="px-4 h-10 rounded bg-purple-600 text-white" @click="calc">=</button>
      </div>
      <div v-if="result !== null" class="text-2xl text-purple-600 font-mono text-right py-2">
        {{ result }}
      </div>
      <div class="grid grid-cols-4 gap-2 mt-3">
        <button v-for="btn in buttons" :key="btn.label"
          class="h-12 rounded text-base font-medium"
          :class="btn.action === 'calc' ? 'bg-purple-600 text-white' : btn.action === 'clear' ? 'bg-red-100 text-red-600' : 'bg-gray-100 text-gray-800'"
          @click="handleButton(btn)"
        >{{ btn.label }}</button>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref } from 'vue'

export default defineComponent({
  name: 'CalculatorPage',
  props: {
    data: { type: Object, default: null },
    execute: { type: Function, default: null },
    refresh: { type: Function, default: null }
  },
  setup(props) {
    const expr = ref('')
    const result = ref<string | null>(null)

    const buttons = [
      { label: '7', value: '7', action: 'input' },
      { label: '8', value: '8', action: 'input' },
      { label: '9', value: '9', action: 'input' },
      { label: '/', value: '/', action: 'input' },
      { label: '4', value: '4', action: 'input' },
      { label: '5', value: '5', action: 'input' },
      { label: '6', value: '6', action: 'input' },
      { label: '*', value: '*', action: 'input' },
      { label: '1', value: '1', action: 'input' },
      { label: '2', value: '2', action: 'input' },
      { label: '3', value: '3', action: 'input' },
      { label: '-', value: '-', action: 'input' },
      { label: '0', value: '0', action: 'input' },
      { label: '.', value: '.', action: 'input' },
      { label: 'C', value: '', action: 'clear' },
      { label: '+', value: '+', action: 'input' },
      { label: '=', value: '', action: 'calc' },
    ]

    function handleButton(btn: { label: string; value: string; action: string }) {
      if (btn.action === 'input') {
        expr.value += btn.value
      } else if (btn.action === 'clear') {
        expr.value = ''
        result.value = null
      } else if (btn.action === 'calc') {
        calc()
      }
    }

    function calc() {
      if (!expr.value.trim()) return
      try {
        const res = Function('"use strict"; return (' + expr.value + ')')()
        result.value = String(res)
      } catch {
        result.value = '错误'
      }
    }

    return { expr, result, buttons, handleButton, calc }
  }
})
</script>
