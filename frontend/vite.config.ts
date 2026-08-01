import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') }
  },
  server: {
    port: 3000,
    proxy: {
      '/api': process.env.VITE_PROXY_TARGET || 'http://mqgeek.com:8000',
      '/ws': { target: process.env.VITE_PROXY_TARGET?.replace(/^http/, 'ws') || 'ws://mqgeek.com:8000', ws: true }
    }
  }
})
