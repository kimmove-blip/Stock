import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    // 구형 Android WebView 호환성을 위해 ES2017 타겟
    target: 'es2017',
    // 청크 크기 경고 제한 상향
    chunkSizeWarningLimit: 1000,
  },
})
