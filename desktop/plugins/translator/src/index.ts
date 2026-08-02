import Page from './Page.vue'
import Panel from './Panel.vue'

let ctx: any = null

export default {
  panel: Panel,
  page: Page,

  activate(context: any) {
    ctx = context

    context.registerCommand('getPanelData', async () => {
      return {
        title: '翻译助手',
        subtitle: '快速翻译，支持多语言',
        buttons: [{ label: '打开翻译', command: 'open' }],
      }
    })

    context.registerCommand('getPageData', async () => {
      return { supported: ['zh', 'en', 'ja', 'ko', 'fr', 'de', 'es', 'ru'] }
    })

    context.registerCommand('translate', async (args: any) => {
      const text = args?.text || ''
      const target = args?.target || 'zh'
      if (!text.trim()) return { success: false, error: '文本为空' }
      try {
        const res = await ctx.api.post('/chat/translate', { text, target })
        return { success: true, translated: res?.translated || '' }
      } catch (e: any) {
        return { success: false, error: e?.message || '翻译失败' }
      }
    })

    context.registerCommand('open', async () => {
      context.openPage('translator')
    })
  },

  deactivate() {},
}
