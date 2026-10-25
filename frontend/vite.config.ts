import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The gateway runs on 8080; dev server proxies API traffic to it so the
// browser never hits CORS (and production build is served by FastAPI itself).
const target = process.env.VITE_API_TARGET || 'http://localhost:8080'
const proxied = ['/v1', '/admin', '/tools', '/health', '/metrics', '/docs', '/openapi.json']

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      proxied.map((p) => [p, { target, changeOrigin: true }])
    ),
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
