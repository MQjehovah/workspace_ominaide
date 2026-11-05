<template>
  <div class="layout" :class="{ 'mobile-open': mobileOpen }">
    <CoreSidebar :collapsed="isMobile ? false : collapsed" />
    <div v-if="isMobile && mobileOpen" class="sidebar-backdrop" @click="mobileOpen = false" />
    <div class="layout-main">
      <CoreHeader @toggle-sidebar="toggleSidebar" />
      <div ref="contentRef" class="layout-content">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" :key="route.path" />
          </transition>
        </router-view>
      </div>
    </div>
    <AssistantPanel />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import CoreSidebar from './CoreSidebar.vue'
import CoreHeader from './CoreHeader.vue'
import AssistantPanel from './AssistantPanel.vue'
import { useAuthStore } from '@/stores/auth'

const collapsed = ref(false)
const isMobile = ref(false)
const mobileOpen = ref(false)
const contentRef = ref<HTMLElement | null>(null)
const auth = useAuthStore()
const route = useRoute()

function syncViewport() {
  isMobile.value = window.innerWidth <= 768
  if (!isMobile.value) mobileOpen.value = false
}

function toggleSidebar() {
  if (isMobile.value) mobileOpen.value = !mobileOpen.value
  else collapsed.value = !collapsed.value
}

watch(() => route.path, () => {
  mobileOpen.value = false
  contentRef.value?.scrollTo({ top: 0 })
})

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
.layout { display: flex; height: 100vh; height: 100dvh; }
.layout-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.layout-content { flex: 1; overflow-y: auto; overscroll-behavior: contain; -webkit-overflow-scrolling: touch; }
.sidebar-backdrop {
  position: fixed; inset: 0; z-index: 2000;
  background: rgba(8, 15, 30, .5);
  backdrop-filter: blur(3px);
  -webkit-backdrop-filter: blur(3px);
  animation: fade-in .18s ease;
}
@keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }

.page-enter-active, .page-leave-active { transition: opacity .16s ease, transform .16s ease; }
.page-enter-from { opacity: 0; transform: translateY(6px); }
.page-leave-to { opacity: 0; transform: translateY(-4px); }

@media (max-width: 768px) {
  .layout :deep(.sidebar) {
    position: fixed; left: 0; top: 0; bottom: 0; z-index: 2001;
    width: 248px; transform: translateX(-100%);
    transition: transform .24s cubic-bezier(.2, .7, .3, 1);
    border-radius: 0 18px 18px 0;
    box-shadow: 26px 0 60px -34px rgba(0, 0, 0, .7);
    padding-bottom: env(safe-area-inset-bottom);
  }
  .layout.mobile-open :deep(.sidebar) { transform: translateX(0); }
  .layout-main { width: 100%; }
  .page-enter-from, .page-leave-to { transform: none; }
}
</style>
