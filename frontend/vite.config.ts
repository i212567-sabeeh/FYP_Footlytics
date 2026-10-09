import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'

const envDir = fileURLToPath(new URL('..', import.meta.url))

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, envDir, ['API_PROXY_TARGET'])

  return {
    plugins: [react(), tailwindcss()],
    envDir,
    build: {
      rollupOptions: {
        output: {
          // Framework code changes rarely: keep it in its own long-cached chunk.
          // Recharts stays with the lazily loaded analytics route.
          manualChunks: (id: string) => /[\\/]node_modules[\\/](react|react-dom|react-router|scheduler|@tanstack)[\\/]/.test(id) ? 'vendor' : undefined,
        },
      },
    },
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': {
          target: env.API_PROXY_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      clearMocks: true,
    },
  }
})
