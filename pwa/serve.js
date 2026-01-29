import express from 'express';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import history from 'connect-history-api-fallback';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const app = express();
const PORT = process.env.PORT || 3000;

// SPA 히스토리 폴백 (React Router 지원)
app.use(history());

// 정적 파일 서빙
app.use(express.static(join(__dirname, 'dist'), {
  maxAge: '1d',
  setHeaders: (res, path) => {
    // HTML과 Service Worker는 캐시하지 않음 (항상 최신 버전)
    if (path.endsWith('.html') || path.endsWith('sw.js')) {
      res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
      res.setHeader('Pragma', 'no-cache');
      res.setHeader('Expires', '0');
    }
  }
}));

app.listen(PORT, () => {
  console.log(`PWA Server running on port ${PORT}`);
});
