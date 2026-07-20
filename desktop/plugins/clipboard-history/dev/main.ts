import { createApp } from 'vue'
import Panel from '../src/Panel.vue'

const mockData = {
  history: [
    { content: '第一段复制的文本内容', time: Date.now() - 60000 },
    { content: '第二段复制的文本内容，稍微长一点的测试', time: Date.now() - 300000 },
    { content: 'https://github.com/example/repo', time: Date.now() - 600000 },
    { content: '第四段内容', time: Date.now() - 1200000 },
    { content: '最后一项记录', time: Date.now() - 3600000 }
  ]
}

const mockContext = {
  data: mockData,
  execute: async (action: string, args?: any) => {
    console.log('execute:', action, args)
    if (action === 'copy') {
      console.log('复制内容:', args?.content)
      return { success: true }
    }
    if (action === 'clear') {
      mockData.history = []
      return { success: true }
    }
    return { success: false }
  },
  openPage: () => {
    console.log('openPage clicked')
  },
  formatTime: (timestamp: number) => {
    const date = new Date(timestamp)
    const now = new Date()
    const diff = now.getTime() - timestamp
    if (diff < 60000) return '刚刚'
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
    return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:${date.getMinutes().toString().padStart(2, '0')}`
  }
}

createApp(Panel, mockContext).mount('#app')