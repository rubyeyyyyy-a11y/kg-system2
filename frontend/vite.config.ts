import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      'react-window': fileURLToPath(new URL('./src/vendor/react-window.tsx', import.meta.url)),
    },
  },
  server: {
    proxy: {
      // 前端请求 /api/** 会被转发到后端 8000
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
