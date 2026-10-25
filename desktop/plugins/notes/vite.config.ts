import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@omniaide/editor': resolve(__dirname, '../../../frontend/src/components/editor/index.ts'),
    },
  },
  build: {
    lib: { entry: resolve(__dirname, 'src/index.ts'), name: 'NotesPlugin', formats: ['cjs'], fileName: 'index' },

    outDir: 'dist', emptyOutDir: true,
  },
})
