import { createApp } from 'vue'
import Panel from '../src/Panel.vue'

interface Note {
  id: string
  content: string
  tags: string[]
  time: number
}

const mockNotes: Note[] = [
  { id: '1', content: '完成项目文档编写', tags: ['工作', '重要'], time: Date.now() - 3600000 },
  { id: '2', content: '学习 Vue 3 新特性', tags: ['学习'], time: Date.now() - 7200000 },
  { id: '3', content: '健身计划：每周三次跑步', tags: ['生活', '健康'], time: Date.now() - 86400000 },
  { id: '4', content: '阅读《代码整洁之道》', tags: ['学习', '读书'], time: Date.now() - 172800000 }
]

const mockData = {
  notes: mockNotes
}

const mockContext = {
  data: mockData,
  execute: async (action: string, args?: any) => {
    console.log('execute:', action, args)
    if (action === 'add') {
      const newNote: Note = {
        id: Date.now().toString(),
        content: args?.content || '',
        tags: args?.tags || [],
        time: Date.now()
      }
      mockNotes.unshift(newNote)
      return { success: true, note: newNote }
    }
    if (action === 'delete') {
      const index = mockNotes.findIndex(n => n.id === args?.id)
      if (index > -1) {
        mockNotes.splice(index, 1)
        return { success: true }
      }
      return { success: false }
    }
    if (action === 'list') {
      return { success: true, notes: mockNotes }
    }
    return { success: false }
  },
  openPage: () => {
    console.log('openPage clicked')
  }
}

createApp(Panel, mockContext).mount('#app')