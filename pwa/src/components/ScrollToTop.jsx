import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

export default function ScrollToTop() {
  const { pathname } = useLocation();

  useEffect(() => {
    // window 스크롤 초기화
    window.scrollTo(0, 0);

    // Layout의 main 요소 스크롤 초기화 (overflow-y-auto 사용 시)
    const mainContent = document.getElementById('main-content');
    if (mainContent) {
      mainContent.scrollTo(0, 0);
    }
  }, [pathname]);

  return null;
}
