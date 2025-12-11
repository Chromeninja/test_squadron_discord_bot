import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite app config (move Vitest settings to vitest.config.ts)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/auth': 'http://localhost:8081',
      '/api': 'http://localhost:8081',
    },
  },
})
