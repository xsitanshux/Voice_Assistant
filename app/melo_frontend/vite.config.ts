// vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// No async, no branches — just a plain object.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/chat':  { target: 'http://127.0.0.1:8000', ws: true, changeOrigin: true },
      '/speak': { target: 'http://127.0.0.1:8000', ws: true, changeOrigin: true },
    },
  },
  publicDir: 'public',
  build: { sourcemap: true },
})
