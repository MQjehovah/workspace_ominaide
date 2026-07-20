import type { PluginModule, PluginContext } from '../../../src/shared/types'

interface Todo {
  id: string
  text: string
  priority: 'high' | 'medium' | 'low'
  completed: boolean
  createdAt: number
}

let todos: Todo[] = []

export default {
  async activate(context: PluginContext) {
    // Load from backend
    try {
      const data = await context.api.get('/plugins/todo/items')
      todos = (data || []).map((t: any) => ({
        id: String(t.id),
        text: t.title,
        priority: t.priority >= 3 ? 'high' : t.priority >= 2 ? 'medium' : 'low',
        completed: t.status === 'done',
        createdAt: new Date(t.created_at).getTime(),
      }))
    } catch { todos = [] }

    context.registerCommand('getPanelData', async () => {
      const pending = todos.filter(t => !t.completed)
      return { pendingCount: pending.length, items: pending.slice(0, 5) }
    })

    context.registerCommand('add', async (args: any) => {
      const text = typeof args === 'object' ? (args.content || args.text || '') : (args || '')
      if (!text) return { title: '请输入内容' }
      try {
        await context.api.post('/plugins/todo/items', { title: text, priority: 1 })
        const updated = await context.api.get('/plugins/todo/items')
        todos = updated.map((t: any) => ({ id: String(t.id), text: t.title, priority: 'medium', completed: t.status === 'done', createdAt: new Date(t.created_at).getTime() }))
        context.notification.show('待办已添加', text)
        return { title: '已添加', subtitle: text }
      } catch { return { title: '添加失败' } }
    })

    context.registerCommand('done', async (args: any) => {
      const id = typeof args === 'object' ? args.id : args
      try {
        await context.api.put(`/plugins/todo/items/${id}`, { status: 'done' })
        const todo = todos.find(t => t.id === id)
        if (todo) { todo.completed = true; context.notification.show('已完成', todo.text) }
        return { title: '已完成' }
      } catch { return { title: '操作失败' } }
    })

    context.registerSearchProvider({
      keyword: 'todo',
      name: '待办事项',
      priority: 40,
      onSearch: async (query: string) => {
        const results: any[] = []
        if (query.startsWith('add ')) {
          results.push({ title: `添加: ${query.slice(4)}`, subtitle: '按回车添加', icon: 'plus', action: 'add', actionArgs: { content: query.slice(4) }, pluginId: 'todo' })
        } else {
          results.push({ title: '添加待办', subtitle: 'todo add 内容', icon: 'plus', action: 'add', pluginId: 'todo' })
          todos.filter(t => !t.completed).slice(0, 5).forEach(t => {
            results.push({ title: t.text, subtitle: '', icon: 'circle', action: 'done', actionArgs: { id: t.id }, pluginId: 'todo' })
          })
        }
        return results
      },
    })
  },

  deactivate() { todos = [] },
} as PluginModule
