import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  root: resolve(__dirname),
  build: {
    outDir: 'frontend', emptyOutDir: true,
    rollupOptions: { input: resolve(__dirname, 'index.html') },
  },
})
