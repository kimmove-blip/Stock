import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../contexts/AuthContext';
import { autoTradeAPI } from '../api/client';
import {
  Key,
  Wallet,
  Settings,
  FileText,
  TrendingUp,
  AlertCircle,
  CheckCircle2,
  XCircle,
  ChevronRight,
  HandCoins,
  Stethoscope,
  Clock,
  History,
  Bot,
  Bell,
} from 'lucide-react';

export default function AutoTrade() {
  const navigate = useNavigate();
  const { user } = useAuth();

  // 자동매매 권한 체크
  if (!user?.auto_trade_enabled) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="text-center">
          <AlertCircle size={48} className="mx-auto text-gray-400 mb-4" />
          <h2 className="text-lg font-bold text-gray-700 mb-2">접근 권한 없음</h2>
          <p className="text-gray-500 text-sm">자동매매 권한이 필요합니다.</p>
        </div>
      </div>
    );
  }

  // 계좌 현황 조회
  const { data: accountData } = useQuery({
    queryKey: ['autoTradeAccount'],
    queryFn: () => autoTradeAPI.getAccount().then((res) => res.data),
    staleTime: 1000 * 60,
    refetchOnWindowFocus: true,
    retry: false,
  });

  // API 키 설정 조회
  const { data: apiKeyData } = useQuery({
    queryKey: ['autoTradeApiKey'],
    queryFn: () => autoTradeAPI.getApiKey().then((res) => res.data),
    staleTime: 1000 * 60 * 5,
  });

  // 자동매매 현황 조회
  const { data: statusData } = useQuery({
    queryKey: ['autoTradeStatus'],
    queryFn: () => autoTradeAPI.status().then((res) => res.data),
    staleTime: 1000 * 60,
    refetchOnWindowFocus: true,
  });

  const isConnected = apiKeyData?.is_connected;
  const pendingCount = statusData?.pending_suggestions?.length || 0;

  // 계좌 요약 정보
  const totalInvestment = accountData?.total_purchase || 0;
  const totalValue = accountData?.total_evaluation || 0;
  const totalProfitLoss = accountData?.total_profit_loss || 0;
  const profitRate = accountData?.profit_rate || 0;
  const isPositive = totalProfitLoss >= 0;

  const menuItems = [
    // 1행: API 키, 계좌, 설정
    {
      id: 'api-key',
      icon: Key,
      label: 'API 키\n설정',
      bgColor: 'bg-blue-100',
      iconColor: 'text-blue-500',
      path: '/auto-trade/api-key',
      badge: isConnected ? (
        <span className="flex items-center justify-center text-[10px] text-green-600">
          <CheckCircle2 size={10} className="mr-0.5" />
          연동됨
        </span>
      ) : (
        <span className="flex items-center justify-center text-[10px] text-gray-400">
          <XCircle size={10} className="mr-0.5" />
          미연동
        </span>
      ),
    },
    {
      id: 'account',
      icon: Wallet,
      label: '계좌 현황',
      bgColor: 'bg-green-100',
      iconColor: 'text-green-500',
      path: '/auto-trade/account',
      disabled: !isConnected,
    },
    {
      id: 'settings',
      icon: Settings,
      label: '자동매매\n설정',
      bgColor: 'bg-purple-100',
      iconColor: 'text-purple-500',
      path: '/auto-trade/settings',
    },
    // 2행: 보유종목 진단, 매매 제안, 수동 매매
    {
      id: 'diagnosis',
      icon: Stethoscope,
      label: '보유종목\n진단',
      bgColor: 'bg-cyan-100',
      iconColor: 'text-cyan-500',
      path: '/auto-trade/diagnosis',
      disabled: !isConnected,
    },
    {
      id: 'suggestions',
      icon: FileText,
      label: '매매 제안',
      bgColor: 'bg-orange-100',
      iconColor: 'text-orange-500',
      path: '/auto-trade/suggestions',
      badge: pendingCount > 0 ? (
        <span className="bg-orange-500 text-white text-[10px] px-1.5 py-0.5 rounded-full">
          {pendingCount}
        </span>
      ) : null,
    },
    {
      id: 'manual',
      icon: HandCoins,
      label: '수동 매매',
      bgColor: 'bg-teal-100',
      iconColor: 'text-teal-500',
      path: '/auto-trade/manual',
      disabled: !isConnected,
    },
    // 3행: 미체결, 거래 내역, 성과 분석
    {
      id: 'pending-orders',
      icon: Clock,
      label: '미체결\n내역',
      bgColor: 'bg-amber-100',
      iconColor: 'text-amber-500',
      path: '/auto-trade/pending-orders',
      disabled: !isConnected,
    },
    {
      id: 'history',
      icon: History,
      label: '거래 내역',
      bgColor: 'bg-indigo-100',
      iconColor: 'text-indigo-500',
      path: '/auto-trade/history',
    },
    {
      id: 'performance',
      icon: TrendingUp,
      label: '성과 분석',
      bgColor: 'bg-pink-100',
      iconColor: 'text-pink-500',
      path: '/auto-trade/performance',
    },
  ];

  return (
    <div className="h-screen bg-gray-50 flex flex-col">
      {/* 헤더 */}
      <div className="bg-gradient-to-r from-purple-600 to-indigo-600 px-4 pt-14 pb-16 flex-shrink-0 sticky top-0 z-10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-white/20 rounded-full flex items-center justify-center text-white font-bold">
              {(user?.name || user?.username)?.charAt(0)?.toUpperCase() || 'U'}
            </div>
            <div className="text-white">
              <p className="text-xs opacity-80">안녕하세요</p>
              <p className="font-bold">{user?.name || user?.username || '사용자'}님</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Bot size={22} className="text-white/70" />
          </div>
        </div>
      </div>

      {/* 메인 컨텐츠 영역 */}
      <div className="px-4 -mt-8 flex-1 flex flex-col pb-20 overflow-hidden">
        {/* 자동매매 계좌 카드 */}
        {isConnected ? (
          <div
            className="bg-gradient-to-br from-purple-500 via-purple-600 to-indigo-600 rounded-2xl p-4 text-white shadow-lg flex-shrink-0 cursor-pointer z-10"
            onClick={() => navigate('/auto-trade/account')}
          >
            {/* 상단: 제목 + 계좌 유형 */}
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Wallet size={18} className="opacity-90" />
                <span className="text-sm font-medium opacity-90">자동매매 계좌</span>
              </div>
              <span className={`text-xs px-2 py-0.5 rounded-full ${apiKeyData?.is_mock ? 'bg-blue-400/30' : 'bg-red-400/30'}`}>
                {apiKeyData?.is_mock ? '모의투자' : '실제투자'}
              </span>
            </div>
            {/* 총 평가금액 */}
            <p className="text-2xl font-bold mb-3">
              {totalValue.toLocaleString()}원
            </p>
            {/* 하단: 투자금액 / 수익률 */}
            <div className="flex justify-between text-sm">
              <div>
                <p className="text-white/60 text-xs">투자금액</p>
                <p className="font-semibold">{totalInvestment.toLocaleString()}원</p>
              </div>
              <div className="text-right">
                <p className="text-white/60 text-xs">수익률</p>
                <p className={`font-semibold ${isPositive ? 'text-green-300' : 'text-red-300'}`}>
                  {isPositive ? '+' : ''}{profitRate.toFixed(2)}%
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div
            className="bg-gradient-to-br from-blue-500 via-blue-600 to-indigo-600 rounded-2xl p-4 text-white shadow-lg flex-shrink-0 cursor-pointer z-10"
            onClick={() => navigate('/auto-trade/api-key')}
          >
            <div className="flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Key size={18} className="opacity-90" />
                  <span className="text-sm font-medium opacity-90">API 연동 필요</span>
                </div>
                <p className="text-lg font-bold mb-1">한국투자증권 API를 연동하세요</p>
                <p className="text-sm text-blue-100">
                  자동매매를 시작하려면 API 키가 필요합니다
                </p>
              </div>
              <ChevronRight size={24} className="text-white/70" />
            </div>
          </div>
        )}

        {/* 퀵 액션 그리드 */}
        <div className="mt-6 flex-1 overflow-y-auto min-h-0">
          <div className="grid grid-cols-3 gap-3">
            {menuItems.map(({ id, icon: Icon, label, bgColor, iconColor, path, badge, disabled }) => (
              <button
                key={id}
                onClick={() => !disabled && navigate(path)}
                disabled={disabled}
                className={`bg-white rounded-2xl p-4 shadow-sm transition-all flex flex-col items-center border border-gray-100 ${
                  disabled
                    ? 'opacity-50 cursor-not-allowed'
                    : 'hover:shadow-md active:scale-95'
                }`}
              >
                <div className={`w-12 h-12 ${bgColor} rounded-xl flex items-center justify-center mb-2`}>
                  <Icon size={26} className={iconColor} />
                </div>
                <span className="text-xs font-medium text-gray-700 text-center whitespace-pre-line leading-tight">
                  {label}
                </span>
                {badge && <div className="mt-1">{badge}</div>}
              </button>
            ))}
          </div>
          {/* 안내 문구 */}
          <p className="text-center text-xs text-gray-400 mt-3">
            자동매매는 투자 손실의 위험이 있으며, 모든 책임은 본인에게 있습니다.
          </p>
        </div>
      </div>
    </div>
  );
}
