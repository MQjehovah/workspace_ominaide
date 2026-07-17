import { defineConfig } from 'vite'
export default defineConfig({
  build: {
    outDir: '../dist-editor',
    emptyOutDir: true,
    rollupOptions: {
      input: 'index.html',
    },
  },
})
