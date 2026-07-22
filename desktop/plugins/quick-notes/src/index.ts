import Panel from './Panel.vue'
import Page from './Page.vue'
import type { Note } from './types'

let notes: Note[] = []

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).substr(2, 9)
}

export default {
  panel: Panel,
  page: Page,

  activate(context: any) {
    context.registerCommand('getPanelData', async () => {
      return {
        title: '快捷笔记',
        summary: notes.length,
        items: notes.slice(0, 5).map(n => ({
          title: n.content.length > 40 ? n.content.slice(0, 40) + '...' : n.content,
          subtitle: new Date(n.time).toLocaleString(),
          icon: n.tags?.includes('important') ? '❗' : '📝',
        })),
        actions: [{ label: '新建', command: 'add' }],
      }
    })

    context.registerCommand('getPageData', async () => {
      return { notes }
    })

    context.registerCommand('add', async (args: any) => {
      const note: Note = {
        id: generateId(),
        content: args?.content || '',
        tags: args?.tags || [],
        time: Date.now()
      }
      notes.unshift(note)
      context.storage?.set('notes', notes)
      return { success: true, note }
    })

    context.registerCommand('delete', async (args: any) => {
      if (args?.id) {
        const index = notes.findIndex(n => n.id === args.id)
        if (index > -1) {
          notes.splice(index, 1)
          context.storage?.set('notes', notes)
          return { success: true }
        }
      }
      return { success: false }
    })

    context.registerCommand('open', async () => {
      context.openPage('quick-notes')
    })

    context.registerCommand('view', async (args: any) => {
      context.openPage('quick-notes')
    })

    context.registerCommand('list', async (args?: any) => {
      let result = [...notes]
      if (args?.tag) {
        result = result.filter(n => n.tags.includes(args.tag))
      }
      if (args?.keyword) {
        const keyword = args.keyword.toLowerCase()
        result = result.filter(n =>
          n.content.toLowerCase().includes(keyword) ||
          n.tags.some(t => t.toLowerCase().includes(keyword))
        )
      }
      return { success: true, notes: result }
    })

    context.registerSearchProvider({
      keyword: 'note',
      name: '快速笔记',
      priority: 30,
      onSearch: async (query: string) => {
        if (!query) {
          return [{
            title: '打开笔记',
            subtitle: `共 ${notes.length} 条笔记`,
            icon: 'note',
            action: 'quick-notes:open',
            pluginId: 'quick-notes'
          }]
        }

        const results = notes.filter(n =>
          n.content.toLowerCase().includes(query.toLowerCase()) ||
          n.tags.some(t => t.toLowerCase().includes(query.toLowerCase()))
        )

        return results.slice(0, 5).map(note => ({
          title: note.content.slice(0, 50),
          subtitle: note.tags.join(', ') || '无标签',
          icon: 'note',
          action: 'quick-notes:view',
          actionArgs: { id: note.id },
          pluginId: 'quick-notes'
        }))
      }
    })

    context.storage?.get('notes').then((data: any) => {
      if (data && Array.isArray(data)) {
        notes = data
      }
    })
  },

  deactivate() {}
}