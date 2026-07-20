import { createApp } from 'vue'
import Panel from '../src/Panel.vue'

const mockData = {
  lastCapture: new Date().toISOString(),
  captures: [
    { id: '1', path: '/screenshot1.png', time: new Date().toISOString(), type: 'region' },
    { id: '2', path: '/screenshot2.png', time: new Date(Date.now() - 60000).toISOString(), type: 'fullscreen' },
    { id: '3', path: '/screenshot3.png', time: new Date(Date.now() - 120000).toISOString(), type: 'window' }
  ]
}

const mockContext = {
  data: mockData,
  execute: async (action: string, args?: any) => {
    console.log('execute:', action, args)
    if (action === 'region') {
      mockData.lastCapture = new Date().toISOString()
      mockData.captures.unshift({ id: Date.now().toString(), path: '/new.png', time: new Date().toISOString(), type: 'region' })
    }
    if (action === 'fullscreen') {
      mockData.lastCapture = new Date().toISOString()
      mockData.captures.unshift({ id: Date.now().toString(), path: '/new.png', time: new Date().toISOString(), type: 'fullscreen' })
    }
    return { success: true }
  },
  openPage: () => {
    console.log('openPage clicked')
  }
}

createApp(Panel, mockContext).mount('#app')