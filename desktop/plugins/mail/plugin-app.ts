import { createApp, defineComponent, ref, h, type Component } from 'vue'

export function mountPlugin(Page: Component, pluginId: string): void {
  const Container = defineComponent({
    setup() {
      const data = ref<any>({})
      const refresh = async () => {
        const win = window as any
        try {
          const result = await win.mqbox?.plugin.execute(pluginId, 'getPageData')
          if (result !== undefined) data.value = result
        } catch (e) {
          console.warn(`[${pluginId}] refresh failed:`, e)
        }
      }
      const execute = async (action: string, args?: any) => {
        const win = window as any
        const result = await win.mqbox?.plugin.execute(pluginId, action, args)
        await refresh()
        return result
      }
      const close = () => window.close()
      refresh()
      return () => h(Page, { data: data.value, execute, close, refresh })
    }
  })
  createApp(Container).mount('#app')
}
