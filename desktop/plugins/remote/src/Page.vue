<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import WebrtcAccept from './WebrtcAccept.vue'
const params = new URLSearchParams(window.location.search)
const mode = params.get('mode') || ''
const isViewer = mode === 'viewer'
const isWebrtcAccept = mode === 'webrtc-accept'
const roomId = params.get('room') || ''

const ViewerSession = defineAsyncComponent(() => import('./ViewerSession.vue'))
const ManagementDashboard = defineAsyncComponent(() => import('./ManagementDashboard.vue'))

defineProps<{ data: any; execute: (a: string, args?: any) => Promise<any>; refresh?: () => void; close: () => void }>()
</script>
<template>
  <WebrtcAccept v-if="isWebrtcAccept" v-bind="$props" />
  <component v-else :is="isViewer ? ViewerSession : ManagementDashboard" v-bind="$props" :room="roomId" />
</template>
