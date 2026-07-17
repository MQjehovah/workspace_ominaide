<template>
  <div v-if="pluginName">
    <h2>{{ pluginName }}</h2>
    <p style="color:#909399">插件页面加载中...</p>
  </div>
  <div v-else>
    <h2>应用未找到</h2>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const pluginName = computed(() => route.params.pluginName as string)
</script>
