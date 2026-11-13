import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// Em desenvolvimento, /api é encaminhado para a API (ex.: exposta localmente em :8000).
export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.VITE_API_PROXY || 'http://localhost:8000', changeOrigin: true } },
  },
  build: {
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        manualChunks: {
          echarts: ['echarts', 'vue-echarts'],
          primevue: ['primevue', '@primeuix/themes'],
        },
      },
    },
  },
})
