import vue from '@vitejs/plugin-vue'
import { defineConfig, externalizeDepsPlugin } from 'electron-vite'
import { fileURLToPath, URL } from 'node:url'
import { SERVICE_ORIGIN } from './src/serviceConfig'

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
  },
  preload: {
    build: {
      rollupOptions: {
        input: fileURLToPath(new URL('./src/main/preload.ts', import.meta.url)),
        output: { entryFileNames: 'index.js' },
      },
    },
  },
  renderer: {
    server: {
      host: '127.0.0.1',
      port: 5174,
      proxy: { '^/api/v1(?:/|$)': { target: SERVICE_ORIGIN, changeOrigin: true } },
    },
    plugins: [vue()],
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src/renderer', import.meta.url)) },
    },
  },
})
