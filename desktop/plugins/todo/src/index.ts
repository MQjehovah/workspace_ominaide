import type { PluginModule, PluginContext } from '../../../src/shared/types'

interface Todo {
  id: string
  text: string
  status: 'pending' | 'in_progress' | 'done'
  priority: number
  due_date: string | null
  tags: string[] | null
  created_at: string
}

let todos: Todo[] = []

async function loadFromApi(context: PluginContext) {
  try {
    const data = await context.api.get('/plugins/todo/items')
    todos = (data || []).map((t: any) => ({
      id: String(t.id),
      text: t.title,
      status: t.status || 'pending',
      priority: t.priority || 0,
      due_date: t.due_date || null,
      tags: t.tags || null,
      created_at: t.created_at || '',
    }))
  } catch { todos = [] }
}

export default {
  async activate(context: PluginContext) {
    await loadFromApi(context)

    context.registerCommand('getPanelData', async () => {
      const pending = todos.filter(t => t.status !== 'done')
      return {
        title: '待办事项',
        subtitle: pending.length > 0 ? `${pending.length} 项待办` : '全部完成',
        items: pending.slice(0, 5).map(t => ({
          title: t.text,
          subtitle: t.due_date || t.priority || '',
          action: 'update',
          actionArgs: { id: t.id, status: 'done' },
        })),
        buttons: [{ label: '新建', command: 'create' }],
      }
    })

    context.registerCommand('getPageData', async () => {
      return { todos }
    })

    context.registerCommand('reload', async () => {
      await loadFromApi(context)
    })

    context.registerCommand('create', async (args: any) => {
      const text = args?.content || args?.text || ''
      if (!text) return { success: false }
      try {
        await context.api.post('/plugins/todo/items', { title: text, priority: args?.priority || 0 })
        await loadFromApi(context)
        return { success: true }
      } catch { return { success: false } }
    })

    context.registerCommand('update', async (args: any) => {
      if (!args?.id) return { success: false }
      const body: any = {}
      if (args.text !== undefined) body.title = args.text
      if (args.status !== undefined) body.status = args.status
      if (args.priority !== undefined) body.priority = args.priority
      try {
        await context.api.put(`/plugins/todo/items/${args.id}`, body)
        await loadFromApi(context)
        return { success: true }
      } catch { return { success: false } }
    })

    context.registerCommand('delete', async (args: any) => {
      const id = args?.id || args
      if (!id) return { success: false }
      try {
        await context.api.delete(`/plugins/todo/items/${id}`)
        await loadFromApi(context)
        return { success: true }
      } catch { return { success: false } }
    })

    context.registerSearchProvider({
      keyword: 'todo',
      name: '待办事项',
      priority: 40,
      onSearch: async (query: string) => {
        const results: any[] = []
        if (query.startsWith('add ')) {
          results.push({ title: `添加: ${query.slice(4)}`, subtitle: '按回车添加', icon: 'plus', action: 'create', actionArgs: { content: query.slice(4) }, pluginId: 'todo' })
        } else {
          results.push({ title: '添加待办', subtitle: 'todo add 内容', icon: 'plus', action: 'create', pluginId: 'todo' })
          todos.filter(t => t.status !== 'done').slice(0, 5).forEach(t => {
            results.push({ title: t.text, subtitle: t.status, icon: 'circle', action: 'update', actionArgs: { id: t.id, status: 'done' }, pluginId: 'todo' })
          })
        }
        return results
      },
    })
  },

  deactivate() { todos = [] },
} as PluginModule
