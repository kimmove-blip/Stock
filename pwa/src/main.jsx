import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.jsx';

// 안드로이드 감지 및 클래스 추가
if (/Android/i.test(navigator.userAgent)) {
  document.documentElement.classList.add('android');
}

// PWA Service Worker 등록 (버전 파라미터로 강제 업데이트)
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    // 기존 SW 강제 업데이트
    navigator.serviceWorker.getRegistrations().then(registrations => {
      registrations.forEach(reg => reg.update());
    });
    // 새 SW 등록 (버전 파라미터로 캐시 무효화)
    navigator.serviceWorker.register('/sw.js?v=12').catch((error) => {
      console.log('SW registration failed:', error);
    });
  });
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>
);
