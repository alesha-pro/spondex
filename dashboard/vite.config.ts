import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../src/spondex/server/static',
    emptyOutDir: true,
  },
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://127.0.0.1:9847',
      '/ws': {
        target: 'ws://127.0.0.1:9847',
        ws: true,
      },
    },
  },
})
