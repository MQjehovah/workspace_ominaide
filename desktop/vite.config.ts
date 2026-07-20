import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import electron from 'vite-plugin-electron'
import { resolve } from 'path'

export default defineConfig({
  root: resolve(__dirname, 'src/renderer'),
  plugins: [
    vue(),
    electron([
      {
        entry: resolve(__dirname, 'src/main/index.ts'),
        onstart(args) { args.startup() },
        vite: { build: { outDir: resolve(__dirname, 'dist-electron/main') } },
      },
      {
        entry: resolve(__dirname, 'src/preload/index.ts'),
        onstart(args) { args.reload() },
        vite: { build: { outDir: resolve(__dirname, 'dist-electron/preload') } },
      },
    ]),
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src/renderer/src'),
      '@plugins': resolve(__dirname, 'plugins'),
    },
  },
  build: {
    outDir: resolve(__dirname, 'dist'),
    emptyOutDir: true,
  },
})
