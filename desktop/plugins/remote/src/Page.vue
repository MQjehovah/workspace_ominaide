<script setup lang="ts">
import { ref, defineAsyncComponent } from 'vue'
import WebrtcAccept from './WebrtcAccept.vue'
const params = new URLSearchParams(window.location.search)
const initialMode = params.get('mode') || ''
const isWebrtcAccept = initialMode === 'webrtc-accept'
const initialRoom = params.get('room') || ''

const activeRoom = ref(initialMode === 'viewer' ? initialRoom : '')

const ViewerSession = defineAsyncComponent(() => import('./ViewerSession.vue'))
const ManagementDashboard = defineAsyncComponent(() => import('./ManagementDashboard.vue'))

const props = defineProps<{ data: any; execute: (a: string, args?: any) => Promise<any>; refresh?: () => void; close: () => void }>()

function openViewer(roomId: string) { activeRoom.value = roomId }
function closeViewer() { activeRoom.value = '' }
</script>
<template>
  <WebrtcAccept v-if="isWebrtcAccept" v-bind="$props" />
  <template v-else-if="activeRoom">
    <ViewerSession v-bind="$props" :room="activeRoom" :close="closeViewer" />
  </template>
  <ManagementDashboard v-else v-bind="$props" @control-device="openViewer" />
</template>
