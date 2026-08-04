import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  build: {
    lib: { entry: resolve(__dirname, 'src/index.ts'), name: 'VibeCodingProxyPlugin', formats: ['cjs'], fileName: 'index' },
    outDir: 'dist', emptyOutDir: true,
    rollupOptions: { external: ['fs', 'path', 'os', 'http', 'child_process', 'ws', 'protobufjs'] },
  },
})
