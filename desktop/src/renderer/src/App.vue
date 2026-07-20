<template>
  <MainPanel v-if="view === 'main'" />
  <SearchBox v-else-if="view === 'search'" />
  <PluginPage v-else-if="view === 'plugin-page'" />
  <LoginPage v-else />
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import MainPanel from './components/MainPanel.vue'
import SearchBox from './components/SearchBox.vue'
import PluginPage from './components/PluginPage.vue'
import LoginPage from './components/LoginPage.vue'

const params = new URLSearchParams(window.location.search)
const view = ref(params.get('view') || 'main')
</script>
