import { createApp, defineComponent, ref, h } from 'vue'
import Page from './src/Page.vue'

const pluginId = 'vibecoding-proxy'

const Container = defineComponent({
  setup() {
    const data = ref<any>({})
    const refresh = async () => {
      try {
        const result = await (window as any).mqbox?.plugin.execute(pluginId, 'getPageData')
        if (result !== undefined) data.value = result
      } catch {}
    }
    const execute = async (action: string, args?: any) => {
      const result = await (window as any).mqbox?.plugin.execute(pluginId, action, args)
      await refresh()
      return result
    }
    const close = () => window.close()
    refresh()
    return () => h(Page, { data: data.value, execute, close, refresh })
  }
})

createApp(Container).mount('#app')
