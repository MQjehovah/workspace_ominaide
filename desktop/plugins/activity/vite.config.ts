import { defineConfig } from 'vite'
import { resolve } from 'path'

export default defineConfig({
  build: {
    lib: { entry: resolve(__dirname, 'src/index.ts'), name: 'ActivityPlugin', formats: ['cjs'], fileName: 'index' },
    rollupOptions: { external: ['child_process'] },
    outDir: 'dist',
    emptyOutDir: true,
  },
})
