import { Outlet, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { Home, Info, MessageCircle, Settings, ArrowLeft, Bell } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

// 페이지별 타이틀 매핑
const pageTitles = {
  '/portfolio': '보유종목',
  '/watchlist': '관심종목',
  '/realtime': 'AI 실시간 추천',
  '/value-stocks': 'AI 가치주 발굴',
  '/search': '종목/테마 검색',
  '/popular': '인기 종목',
  '/news': '시장 뉴스',
  '/market': '코스피/코스닥',
  '/global': '해외주식 현황',
  '/about': '앱 소개',
  '/contact': '문의하기',
  '/settings': '설정',
  '/telegram': '텔레그램 알림',
  '/login': '로그인',
  '/register': '회원가입',
};

export default function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isHome = location.pathname === '/';
  const isStockDetail = location.pathname.startsWith('/stock/');

  // 현재 페이지 타이틀
  const pageTitle = pageTitles[location.pathname] || (isStockDetail ? '종목 상세' : '');

  const navItems = [
    { to: '/', icon: Home, label: '홈' },
    { to: '/about', icon: Info, label: '앱 소개' },
    { to: '/contact', icon: MessageCircle, label: '문의' },
    { to: '/settings', icon: Settings, label: '설정' },
  ];

  return (
    <div className="h-screen bg-gray-50 flex flex-col overflow-hidden">
      {/* 공통 헤더 - 홈이 아닌 페이지에서만 표시 */}
      {!isHome && (
        <header className="bg-gradient-to-r from-purple-600 to-indigo-600 px-4 pt-12 pb-4 sticky top-0 z-40 flex-shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button
                onClick={() => navigate(-1)}
                className="p-2 -ml-2 text-white hover:bg-white/10 rounded-full transition-colors"
              >
                <ArrowLeft size={24} />
              </button>
              <h1 className="text-white font-bold text-lg">{pageTitle}</h1>
            </div>
            <div className="flex items-center gap-2">
              {user && (
                <div className="w-8 h-8 bg-white/20 rounded-full flex items-center justify-center text-white font-bold text-sm">
                  {(user?.name || user?.username)?.charAt(0)?.toUpperCase() || 'U'}
                </div>
              )}
              <button
                onClick={() => navigate('/telegram')}
                className="relative p-2 text-white hover:bg-white/10 rounded-full transition-colors"
              >
                <Bell size={20} />
                <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full"></span>
              </button>
            </div>
          </div>
        </header>
      )}

      {/* 메인 컨텐츠 */}
      <main className={`flex-1 overflow-y-auto pb-20 ${isHome ? '' : 'p-4'}`}>
        <Outlet />
      </main>

      {/* 하단 네비게이션 - 화면 하단 고정 */}
      <nav className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 px-4 py-2 z-50" style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}>
        <div className="flex justify-around items-center max-w-md mx-auto">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex flex-col items-center gap-1 px-4 py-2 rounded-full transition-all ${
                  isActive
                    ? 'bg-purple-600 text-white'
                    : 'text-gray-500 hover:text-purple-600'
                }`
              }
            >
              <Icon size={20} />
              <span className="text-xs">{label}</span>
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
