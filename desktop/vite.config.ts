import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import electron from 'vite-plugin-electron'
import renderer from 'vite-plugin-electron-renderer'
import UnoCSS from 'unocss/vite'
import { resolve } from 'path'

export default defineConfig({
  plugins: [
    vue(),
    UnoCSS(),
    electron([
      {
        entry: 'src/main/index.ts',
        onstart(options) { options.startup() },
        vite: {
          build: { outDir: 'dist-electron/main', minify: false },
        },
      },
      {
        entry: 'src/preload/index.ts',
        onstart(options) { options.reload() },
        vite: {
          build: { outDir: 'dist-electron/preload' },
        },
      },
    ]),
    renderer(),
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
