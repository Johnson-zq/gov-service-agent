import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Local Backend default is 18000 (Windows often reserves 7998-8097, including 8000).
// Override: GOVAGENT_DEV_BACKEND_URL=http://127.0.0.1:18000 npm run dev
const backendTarget =
  process.env.GOVAGENT_DEV_BACKEND_URL?.trim() || 'http://127.0.0.1:18000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: backendTarget,
      },
      '/health': {
        target: backendTarget,
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    globals: true,
    css: true,
  },
})
