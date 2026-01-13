import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../contexts/AuthContext';
import { portfolioAPI } from '../api/client';
import {
  Zap,
  TrendingUp,
  Search,
  Star,
  Briefcase,
  Flame,
  Newspaper,
  BarChart3,
  Globe,
  Bell,
} from 'lucide-react';

export default function Home() {
  const { user } = useAuth();
  const navigate = useNavigate();

  // 포트폴리오 데이터 (화면 표시될 때마다 새로고침)
  const { data: portfolio } = useQuery({
    queryKey: ['portfolio'],
    queryFn: () => portfolioAPI.list().then((res) => res.data),
    staleTime: 0,  // 항상 새 데이터 가져오기
    refetchOnMount: 'always',  // 마운트 시 항상 새로고침
    refetchOnWindowFocus: true,  // 창 포커스 시 새로고침
  });

  // 퀵 액션 목록 - 배경색과 아이콘색 분리
  const quickActions = [
    { icon: Zap, label: 'AI 실시간\n추천', bgColor: 'bg-red-100', iconColor: 'text-red-500', path: '/realtime' },
    { icon: TrendingUp, label: 'AI 가치주\n발굴', bgColor: 'bg-blue-100', iconColor: 'text-blue-500', path: '/value-stocks' },
    { icon: Search, label: '종목/테마\n검색', bgColor: 'bg-purple-100', iconColor: 'text-purple-500', path: '/search' },
    { icon: Star, label: '관심종목', bgColor: 'bg-yellow-100', iconColor: 'text-yellow-500', path: '/watchlist' },
    { icon: Briefcase, label: '보유종목', bgColor: 'bg-green-100', iconColor: 'text-green-500', path: '/portfolio' },
    { icon: Flame, label: '인기 종목', bgColor: 'bg-orange-100', iconColor: 'text-orange-500', path: '/popular' },
    { icon: Newspaper, label: '시장 뉴스', bgColor: 'bg-cyan-100', iconColor: 'text-cyan-500', path: '/news' },
    { icon: BarChart3, label: '코스피\n코스닥', bgColor: 'bg-indigo-100', iconColor: 'text-indigo-500', path: '/market' },
    { icon: Globe, label: '해외주식\n현황', bgColor: 'bg-pink-100', iconColor: 'text-pink-500', path: '/global' },
  ];

  const summary = portfolio?.summary || {
    total_investment: 0,
    total_value: 0,
    total_profit_loss: 0,
    total_profit_loss_rate: 0,
  };

  const isPositive = summary.total_profit_loss >= 0;

  return (
    <div className="h-screen bg-gray-50 flex flex-col overflow-hidden">
      {/* 헤더 - 그라데이션 */}
      <div className="bg-gradient-to-r from-purple-600 to-indigo-600 px-4 pt-14 pb-16 flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-white/20 rounded-full flex items-center justify-center text-white font-bold">
              {user?.username?.charAt(0)?.toUpperCase() || 'U'}
            </div>
            <div className="text-white">
              <p className="text-xs opacity-80">안녕하세요</p>
              <p className="font-bold">{user?.username || '사용자'}님</p>
            </div>
          </div>
          <button className="relative p-2">
            <Bell className="text-white" size={22} />
            <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full"></span>
          </button>
        </div>
      </div>

      {/* 메인 컨텐츠 영역 */}
      <div className="px-4 -mt-8 flex-1 flex flex-col pb-20">
        {/* 포트폴리오 카드 */}
        <div
          className="bg-gradient-to-br from-purple-500 via-purple-600 to-indigo-600 rounded-2xl p-4 text-white shadow-lg flex-shrink-0 cursor-pointer"
          onClick={() => navigate('/portfolio')}
        >
          {/* 상단: 제목 + 아이콘 */}
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Briefcase size={18} className="opacity-90" />
              <span className="text-sm font-medium opacity-90">내 보유종목</span>
            </div>
          </div>
          {/* 총 평가금액 */}
          <p className="text-2xl font-bold mb-3">
            {summary.total_value.toLocaleString()}원
          </p>
          {/* 하단: 투자금액 / 수익률 */}
          <div className="flex justify-between text-sm">
            <div>
              <p className="text-white/60 text-xs">투자금액</p>
              <p className="font-semibold">{summary.total_investment.toLocaleString()}원</p>
            </div>
            <div className="text-right">
              <p className="text-white/60 text-xs">수익률</p>
              <p className={`font-semibold ${isPositive ? 'text-green-300' : 'text-red-300'}`}>
                {isPositive ? '+' : ''}{summary.total_profit_loss_rate.toFixed(2)}%
              </p>
            </div>
          </div>
        </div>

        {/* 퀵 액션 그리드 - 카드 스타일 */}
        <div className="mt-6 flex-shrink-0">
          <div className="grid grid-cols-3 gap-3">
            {quickActions.map(({ icon: Icon, label, bgColor, iconColor, path }) => (
              <button
                key={path}
                onClick={() => navigate(path)}
                className="bg-white rounded-2xl p-4 shadow-sm hover:shadow-md transition-all active:scale-95 flex flex-col items-center border border-gray-100"
              >
                <div className={`w-12 h-12 ${bgColor} rounded-xl flex items-center justify-center mb-2`}>
                  <Icon size={26} className={iconColor} />
                </div>
                <span className="text-xs font-medium text-gray-700 text-center whitespace-pre-line leading-tight">
                  {label}
                </span>
              </button>
            ))}
          </div>
          {/* 면책 조항 - 아이콘 바로 아래 */}
          <p className="text-center text-xs text-gray-400 mt-3">
            본 서비스의 정보는 투자 권유가 아니며, 투자 책임은 본인에게 있습니다.
          </p>
        </div>
      </div>
    </div>
  );
}
