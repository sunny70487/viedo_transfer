import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/transcribe': 'http://localhost:5000',
      '/tasks': 'http://localhost:5000',
      '/download': 'http://localhost:5000',
      '/gpu-info': 'http://localhost:5000',
      '/system': 'http://localhost:5000',
      '/api': 'http://localhost:5000',
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
