<template>
  <div class="layout" :class="{ 'mobile-open': mobileOpen }">
    <CoreSidebar :collapsed="isMobile ? false : collapsed" />
    <div v-if="isMobile && mobileOpen" class="sidebar-backdrop" @click="mobileOpen = false" />
    <div class="layout-main">
      <CoreHeader @toggle-sidebar="toggleSidebar" />
      <div class="layout-content">
        <router-view />
      </div>
    </div>
    <AssistantPanel />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import CoreSidebar from './CoreSidebar.vue'
import CoreHeader from './CoreHeader.vue'
import AssistantPanel from './AssistantPanel.vue'
import { useAuthStore } from '@/stores/auth'

const collapsed = ref(false)
const isMobile = ref(false)
const mobileOpen = ref(false)
const auth = useAuthStore()

function syncViewport() {
  isMobile.value = window.innerWidth <= 768
  if (!isMobile.value) mobileOpen.value = false
}

function toggleSidebar() {
  if (isMobile.value) mobileOpen.value = !mobileOpen.value
  else collapsed.value = !collapsed.value
}

onMounted(async () => {
  syncViewport()
  window.addEventListener('resize', syncViewport)
  if (auth.token && !auth.user) {
    try { await auth.fetchUser() } catch { /* silently fail */ }
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', syncViewport)
})
</script>

<style scoped>
.layout { display: flex; height: 100vh; }
.layout-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.layout-content { flex: 1; overflow-y: auto; }
.sidebar-backdrop {
  position: fixed; inset: 0; background: rgba(0, 0, 0, .45); z-index: 2000;
}
@media (max-width: 768px) {
  .layout :deep(.sidebar) {
    position: fixed; left: 0; top: 0; bottom: 0; z-index: 2001;
    width: 240px; transform: translateX(-100%); transition: transform .2s ease;
  }
  .layout.mobile-open :deep(.sidebar) { transform: translateX(0); }
  .layout-main { width: 100%; }
}
</style>
