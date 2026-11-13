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
        forms: [
          {
            fields: [
              { key: 'text', label: '文本', type: 'textarea', placeholder: '输入或粘贴要翻译的内容' },
              {
                key: 'target',
                label: '目标',
                type: 'select',
                value: 'zh',
                options: [
                  { label: '中文', value: 'zh' },
                  { label: 'English', value: 'en' },
                  { label: '日本語', value: 'ja' },
                  { label: '한국어', value: 'ko' },
                ],
              },
            ],
            submitLabel: '翻译并复制',
            command: 'translateFromPanel',
          },
        ],
      }
    })

    context.registerCommand('getPageData', async () => {
      return { supported: ['zh', 'en', 'ja', 'ko', 'fr', 'de', 'es', 'ru'] }
    })

    context.registerCommand('translateFromPanel', async (args: any) => {
      const text = String(args?.text || '')
      if (!text.trim()) return { success: false, error: '文本为空' }
      try {
        const res = await ctx.api.post('/chat/translate', {
          text,
          target: args?.target || 'zh',
        })
        const translated = res?.translated || ''
        if (translated) await context.signal('clipboard:writeText', translated)
        return { success: !!translated, translated }
      } catch (e: any) {
        return { success: false, error: e?.message || '翻译失败' }
      }
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

    // ---- System-wide selection actions (划词) --------------------------
    context.registerSelectionAction({
      id: 'translate-replace',
      title: '翻译并替换',
      description: '自动识别中英文，结果直接替换选中文本',
      icon: '🌐',
      command: 'translateSelection',
      args: { mode: 'replace' },
    })
    context.registerSelectionAction({
      id: 'translate-copy',
      title: '翻译并复制',
      description: '把译文复制到剪贴板',
      icon: '📋',
      command: 'translateSelection',
      args: { mode: 'copy' },
    })

    context.registerCommand('translateSelection', async (args: any) => {
      const text = String(args?.text || '')
      if (!text.trim()) return { message: '没有读取到选中文本' }
      const target = /[\u4e00-\u9fa5]/.test(text) ? 'en' : 'zh'
      try {
        const res = await ctx.api.post('/chat/translate', { text, target })
        const translated = res?.translated || ''
        if (!translated) return { message: '翻译失败，请稍后再试' }
        if (args?.mode === 'copy') return { copy: translated }
        return { replace: translated }
      } catch (e: any) {
        return { message: e?.message || '翻译失败' }
      }
    })

    // ---- Tray + command palette contributions --------------------------
    context.setTrayItems([
      { id: 'open', label: '打开翻译', command: 'open' },
    ])
    context.registerPaletteItem({
      id: 'open',
      title: '翻译助手',
      subtitle: '打开翻译面板',
      icon: '🌐',
      keywords: ['translate', '翻译', 'translation'],
      command: 'open',
    })
  },

  deactivate() {},
}
