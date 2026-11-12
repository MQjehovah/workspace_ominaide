import { createApp, defineComponent, ref, h, type Component } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'

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

  const app = createApp(Container)
  // The shared notes editor uses Element Plus dialogs/dropdowns/popovers.
  // Without registering it they render as unknown inline elements and steal
  // the editor's height, which looks like "content is cut off".
  app.use(ElementPlus)
  app.mount('#app')
}
