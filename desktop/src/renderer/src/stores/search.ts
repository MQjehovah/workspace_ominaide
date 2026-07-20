import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useSearchStore = defineStore('search', () => {
  const query = ref('')
  const results = ref<any[]>([])
  const providers = ref<any[]>([])
  const loading = ref(false)

  async function loadProviders() {
    providers.value = await window.mqbox.search.getProviders()
  }

  async function search(keyword: string, queryText: string) {
    loading.value = true
    try {
      results.value = await window.mqbox.search.plugin(keyword, queryText)
    } finally {
      loading.value = false
    }
  }

  return { query, results, providers, loading, loadProviders, search }
})
