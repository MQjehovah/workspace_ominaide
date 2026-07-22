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
import { ref } from 'vue'
import CoreSidebar from './CoreSidebar.vue'
import CoreHeader from './CoreHeader.vue'

const collapsed = ref(false)
</script>

<style scoped>
.layout { display: flex; height: 100vh; }
.layout-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.layout-content { flex: 1; overflow-y: auto; }
</style>
