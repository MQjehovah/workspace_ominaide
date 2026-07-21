import Panel from './Panel.vue'
import Page from './Page.vue'
import Editor from './Editor.vue'
import type { PluginModule, PluginContext } from '../../../src/shared/types'

export default {
  panel: Panel,
  page: Page,
  editor: Editor,

  async activate(context: PluginContext) {
    context.registerCommand('getPanelData', async () => {
      const history = context.screenshot?.getHistory() || []
      const last = history.length > 0 ? history[0] : null
      return {
        lastCapture: last,
        captureCount: history.length,
      }
    })

    context.registerCommand('getPageData', async () => {
      const history = context.screenshot?.getHistory() || []
      return { captures: history }
    })

    context.registerCommand('region', async () => {
      await context.screenshot?.start()
      return { success: true }
    })

    context.registerCommand('fullscreen', async () => {
      const dataUrl = await context.screenshot?.captureFullscreen()
      if (dataUrl) {
        context.notification.show('截图完成', '全屏截图已复制到剪贴板')
      }
      return { success: !!dataUrl }
    })

    context.registerCommand('open', async (args: any) => {
      if (args?.dataUrl) {
        await context.screenshot?.showEditor(args.dataUrl)
      }
      return { success: true }
    })

    context.registerCommand('clear', async () => {
      context.screenshot?.clearHistory()
      return { success: true }
    })

    context.registerCommand('delete', async (args: any) => {
      if (args?.id) {
        context.screenshot?.deleteHistory(args.id)
      }
      return { success: true }
    })

    context.registerSearchProvider({
      keyword: 'ss',
      name: '截图工具',
      onSearch: async () => {
        return [
          {
            type: 'screenshot',
            title: '区域截图',
            subtitle: '截取屏幕指定区域',
            icon: 'screenshot',
            action: 'region',
            pluginId: 'screenshot',
          },
          {
            type: 'screenshot',
            title: '全屏截图',
            subtitle: '截取整个屏幕',
            icon: 'screenshot',
            action: 'fullscreen',
            pluginId: 'screenshot',
          },
        ]
      },
    })
  },

  deactivate() {},
} as PluginModule
