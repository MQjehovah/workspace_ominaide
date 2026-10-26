import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    base: env.VITE_BASE || '/',
    plugins: [vue()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src'),
        '@omniaide/editor': path.resolve(__dirname, 'src/components/editor/index.ts'),
      }
    },
    server: {
      port: 3000,
      proxy: {
        '/api': env.VITE_PROXY_TARGET || 'http://mqgeek.com:8000',
        '/ws': { target: env.VITE_PROXY_TARGET?.replace(/^http/, 'ws') || 'ws://mqgeek.com:8000', ws: true }
      }
    }
  }
})
