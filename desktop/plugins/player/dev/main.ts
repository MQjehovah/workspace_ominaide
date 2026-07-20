import { createApp } from 'vue'
import Panel from '../src/Panel.vue'

const mockData = {
  currentTrack: { name: '测试歌曲.mp3', path: '/test.mp3', type: 'audio' },
  isPlaying: true,
  currentTime: 45,
  duration: 180,
  volume: 80,
  playlist: [
    { name: '歌曲1.mp3', path: '/song1.mp3', type: 'audio' },
    { name: '歌曲2.mp3', path: '/song2.mp3', type: 'audio' },
    { name: '视频1.mp4', path: '/video1.mp4', type: 'video' }
  ],
  playMode: 'sequence'
}

const mockContext = {
  data: mockData,
  execute: async (action: string, args?: any) => {
    console.log('execute:', action, args)
    if (action === 'play') mockData.isPlaying = true
    if (action === 'pause') mockData.isPlaying = false
    if (action === 'next') mockData.currentTrack = mockData.playlist[1]
    if (action === 'prev') mockData.currentTrack = mockData.playlist[0]
    return { success: true }
  },
  openPage: () => {
    console.log('openPage clicked')
  },
  formatTime: (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }
}

createApp(Panel, mockContext).mount('#app')