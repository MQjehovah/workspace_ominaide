<template>
  <div class="layout">
    <CoreSidebar :collapsed="collapsed" />
    <div class="layout-main">
      <CoreHeader @toggle-sidebar="collapsed = !collapsed" />
      <div class="layout-content">
        <router-view />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import CoreSidebar from './CoreSidebar.vue'
import CoreHeader from './CoreHeader.vue'
import { useAuthStore } from '@/stores/auth'

const collapsed = ref(false)
const auth = useAuthStore()

onMounted(async () => {
  if (auth.token && !auth.user) {
    try { await auth.fetchUser() } catch { /* silently fail */ }
  }
})
</script>

<style scoped>
.layout { display: flex; height: 100vh; }
.layout-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.layout-content { flex: 1; overflow-y: auto; }
</style>
