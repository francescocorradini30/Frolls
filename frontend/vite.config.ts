import { readFileSync } from 'node:fs'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import { defineConfig } from 'vite'

// The e2e run points the proxy at its own isolated backend.
const backend = process.env.FROLLS_API_URL ?? 'http://localhost:8000'

// Single app version, shared with the backend: the root package.json is the only source.
const { version } = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf-8'))

// https://vite.dev/config/
export default defineConfig({
  plugins: [svelte()],
  // A second Vite (e2e) next to the dev one needs its own dependency cache.
  cacheDir: process.env.FROLLS_VITE_CACHE_DIR,
  define: {
    __APP_VERSION__: JSON.stringify(version),
  },
  server: {
    proxy: {
      '/ws': { target: backend, ws: true },
      '/health': backend,
      '/api': backend,
      '/uploads': backend,
    },
  },
})
