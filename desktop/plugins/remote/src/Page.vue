<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
const params = new URLSearchParams(window.location.search)
const isViewer = params.get('mode') === 'viewer'
const roomId = params.get('room') || ''

const ViewerSession = defineAsyncComponent(() => import('./ViewerSession.vue'))
const ManagementDashboard = defineAsyncComponent(() => import('./ManagementDashboard.vue'))

defineProps<{ data: any; execute: (a: string, args?: any) => Promise<any>; refresh?: () => void; close: () => void }>()
</script>
<template>
  <component :is="isViewer ? ViewerSession : ManagementDashboard" v-bind="$props" :room="roomId" />
</template>
