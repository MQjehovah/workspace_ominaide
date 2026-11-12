import { createApp, defineComponent, h, type Component } from 'vue'
import Page from './src/Page.vue'

export function mountPlugin(PageComponent: Component, pluginId: string): void {
  const Container = defineComponent({
    setup() {
      const execute = async (action: string, args?: any) => {
        const win = window as any
        return await win.mqbox?.plugin.execute(pluginId, action, args)
      }

      const close = () => window.close()

      // This plugin page is self-contained (it loads its own session data), so
      // there is no page-data refresh to run after every command.
      return () => h(PageComponent, { data: {}, execute, close })
    },
  })

  createApp(Container).mount('#app')
}

mountPlugin(Page, 'vibecoding-proxy')
