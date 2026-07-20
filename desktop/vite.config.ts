import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import electron from 'vite-plugin-electron'
import { resolve } from 'path'

export default defineConfig({
  plugins: [
    vue(),
    electron([
      {
        entry: 'src/main/index.ts',
        onstart(args) { args.startup() },
        vite: { build: { outDir: 'dist-electron/main' } },
      },
      {
        entry: 'src/preload/index.ts',
        onstart(args) { args.reload() },
        vite: { build: { outDir: 'dist-electron/preload' } },
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
    outDir: 'dist',
    emptyOutDir: true,
  },
})
