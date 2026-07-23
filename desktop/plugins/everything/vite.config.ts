import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import { builtinModules } from 'module'

export default defineConfig({
  plugins: [vue()],
  build: {
    lib: { entry: resolve(__dirname, 'src/index.ts'), name: 'EverythingPlugin', formats: ['cjs'], fileName: 'index' },
    rollupOptions: { external: [...builtinModules] },
    outDir: 'dist', emptyOutDir: true,
  },
})
