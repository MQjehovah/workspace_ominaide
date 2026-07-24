import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  build: {
    lib: {
      entry: resolve(__dirname, 'src/index.ts'),
      name: 'MailPlugin',
      formats: ['cjs'],
      fileName: 'index'
    },
    rollupOptions: {
      external: ['nodemailer', 'net', 'tls'],
    },
    outDir: 'dist',
    emptyOutDir: true
  }
})
