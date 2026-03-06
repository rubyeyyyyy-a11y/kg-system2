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
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules/')) return

          const pkgPath = id.split('node_modules/')[1]
          const parts = pkgPath.split('/')
          const pkgName = parts[0].startsWith('@') ? `${parts[0]}/${parts[1]}` : parts[0]

          if (pkgName === 'react' || pkgName === 'react-dom' || pkgName === 'scheduler') {
            return 'vendor-react'
          }
          if (pkgName === 'react-window') {
            return 'vendor-react-window'
          }
          if (pkgName.startsWith('@antv/')) {
            return `vendor-antv-${pkgName.slice('@antv/'.length)}`
          }
        },
      },
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
