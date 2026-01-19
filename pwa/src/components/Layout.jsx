import { Outlet, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Home, Info, MessageCircle, Settings, ArrowLeft, Bell, Bot } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { alertsAPI } from '../api/client';

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
  '/push': '푸시 알림',
  '/alerts': '알림 기록',
  '/login': '로그인',
  '/register': '회원가입',
  '/auto-trade': '자동매매',
  '/auto-trade/api-key': 'API 키 설정',
  '/auto-trade/account': '계좌 현황',
  '/auto-trade/settings': '자동매매 설정',
  '/auto-trade/suggestions': '매매 제안 관리',
  '/auto-trade/history': '거래 내역',
  '/auto-trade/performance': '성과 분석',
  '/auto-trade/diagnosis': '보유종목 진단',
  '/auto-trade/manual': '수동 매매',
  '/auto-trade/pending-orders': '미체결 내역',
};

export default function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isHome = location.pathname === '/';
  const isAutoTradeMain = location.pathname === '/auto-trade';
  const isStockDetail = location.pathname.startsWith('/stock/');

  // 알림 기록 조회
  const { data: alertsData } = useQuery({
    queryKey: ['alerts'],
    queryFn: () => alertsAPI.list(7).then((res) => res.data),
    staleTime: 1000 * 60 * 5, // 5분 캐시
    enabled: !!user,
  });

  // 읽지 않은 알림 계산 (localStorage에 마지막 확인 시간 저장)
  const lastViewedAlerts = localStorage.getItem('lastViewedAlerts');
  const unreadCount = alertsData?.items?.filter((alert) => {
    if (!lastViewedAlerts) return true;
    return new Date(alert.created_at) > new Date(lastViewedAlerts);
  }).length || 0;
  const hasUnread = unreadCount > 0;

  // 현재 페이지 타이틀
  const pageTitle = pageTitles[location.pathname] || (isStockDetail ? '종목 상세' : '');

  // 자동매매 권한에 따라 메뉴 동적 생성
  const navItems = [
    { to: '/', icon: Home, label: '홈' },
    // 자동매매 권한이 있으면 홈과 앱소개 사이에 자동매매 메뉴 추가
    ...(user?.auto_trade_enabled ? [{ to: '/auto-trade', icon: Bot, label: '자동매매' }] : []),
    { to: '/about', icon: Info, label: '앱 소개' },
    { to: '/contact', icon: MessageCircle, label: '문의' },
    { to: '/settings', icon: Settings, label: '설정' },
  ];

  return (
    <div className="h-screen bg-gray-50 flex flex-col overflow-hidden">
      {/* 공통 헤더 - 홈과 자동매매 메인이 아닌 페이지에서만 표시 */}
      {!isHome && !isAutoTradeMain && (
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
                onClick={() => navigate('/alerts')}
                className={`relative p-2 rounded-full transition-colors ${
                  hasUnread
                    ? 'text-white hover:bg-white/10'
                    : 'text-white/50 cursor-default'
                }`}
                disabled={!hasUnread}
              >
                <Bell size={20} />
                {hasUnread && (
                  <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full animate-pulse"></span>
                )}
              </button>
            </div>
          </div>
        </header>
      )}

      {/* 메인 컨텐츠 */}
      <main className={`flex-1 pb-20 ${isHome || isAutoTradeMain ? 'overflow-hidden' : 'overflow-y-auto p-4'}`}>
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
