import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../contexts/AuthContext';
import { autoTradeAPI } from '../api/client';
import {
  Key,
  Wallet,
  Settings,
  FileText,
  BarChart3,
  TrendingUp,
  AlertCircle,
  CheckCircle2,
  XCircle,
  ChevronRight,
  HandCoins,
  Stethoscope,
  Clock,
  History,
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

  // 자동매매 현황 조회 (연동 상태 확인용)
  const { data: statusData } = useQuery({
    queryKey: ['autoTradeStatus'],
    queryFn: () => autoTradeAPI.status().then((res) => res.data),
    staleTime: 1000 * 60,
    refetchOnWindowFocus: true,
  });

  // API 키 설정 조회
  const { data: apiKeyData } = useQuery({
    queryKey: ['autoTradeApiKey'],
    queryFn: () => autoTradeAPI.getApiKey().then((res) => res.data),
    staleTime: 1000 * 60 * 5,
  });

  const isConnected = apiKeyData?.is_connected;
  const pendingCount = statusData?.pending_suggestions?.length || 0;

  const menuItems = [
    // 1행: API 키, 계좌, 설정
    {
      id: 'api-key',
      icon: Key,
      label: 'API 키 설정',
      description: '한국투자증권 API 연동',
      path: '/auto-trade/api-key',
      color: 'bg-blue-500',
      badge: isConnected ? (
        <span className="flex items-center text-xs text-green-600">
          <CheckCircle2 size={12} className="mr-1" />
          연동됨
        </span>
      ) : (
        <span className="flex items-center text-xs text-gray-400">
          <XCircle size={12} className="mr-1" />
          미연동
        </span>
      ),
    },
    {
      id: 'account',
      icon: Wallet,
      label: '계좌 현황',
      description: '실제 증권 계좌 잔고',
      path: '/auto-trade/account',
      color: 'bg-green-500',
      disabled: !isConnected,
    },
    {
      id: 'settings',
      icon: Settings,
      label: '자동매매 설정',
      description: '매매 모드, 한도 설정',
      path: '/auto-trade/settings',
      color: 'bg-purple-500',
    },
    // 2행: 보유종목 진단, 매매 제안, 수동 매매
    {
      id: 'diagnosis',
      icon: Stethoscope,
      label: '보유종목 진단',
      description: 'AI 보유종목 분석',
      path: '/auto-trade/diagnosis',
      color: 'bg-cyan-500',
      disabled: !isConnected,
    },
    {
      id: 'suggestions',
      icon: FileText,
      label: '매매 제안',
      description: '매수/매도 제안 관리',
      path: '/auto-trade/suggestions',
      color: 'bg-orange-500',
      badge: pendingCount > 0 ? (
        <span className="bg-orange-100 text-orange-600 text-xs px-2 py-0.5 rounded-full">
          {pendingCount}
        </span>
      ) : null,
    },
    {
      id: 'manual',
      icon: HandCoins,
      label: '수동 매매',
      description: '직접 매수/매도 주문',
      path: '/auto-trade/manual',
      color: 'bg-teal-500',
      disabled: !isConnected,
    },
    // 3행: 미체결, 거래 내역, 성과 분석
    {
      id: 'pending-orders',
      icon: Clock,
      label: '미체결 내역',
      description: '대기 중인 주문',
      path: '/auto-trade/pending-orders',
      color: 'bg-amber-500',
      disabled: !isConnected,
    },
    {
      id: 'history',
      icon: History,
      label: '거래 내역',
      description: '체결된 거래 기록',
      path: '/auto-trade/history',
      color: 'bg-indigo-500',
    },
    {
      id: 'performance',
      icon: TrendingUp,
      label: '성과 분석',
      description: '수익률, 승률 통계',
      path: '/auto-trade/performance',
      color: 'bg-pink-500',
    },
  ];

  return (
    <div className="max-w-md mx-auto space-y-4">
      {/* 미연동 시 안내 배너 */}
      {!isConnected && (
        <div
          className="bg-gradient-to-r from-blue-500 to-indigo-600 rounded-xl p-4 text-white cursor-pointer"
          onClick={() => navigate('/auto-trade/api-key')}
        >
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-bold mb-1">API 연동이 필요합니다</h3>
              <p className="text-sm text-blue-100">
                한국투자증권 API를 연동하여 자동매매를 시작하세요
              </p>
            </div>
            <ChevronRight size={24} className="text-white/70" />
          </div>
        </div>
      )}

      {/* 6개 메뉴 아이콘 그리드 */}
      <div className="grid grid-cols-3 gap-3">
        {menuItems.map((item) => (
          <button
            key={item.id}
            onClick={() => !item.disabled && navigate(item.path)}
            disabled={item.disabled}
            className={`bg-white rounded-xl p-4 shadow-sm text-center transition-all ${
              item.disabled
                ? 'opacity-50 cursor-not-allowed'
                : 'hover:shadow-md active:scale-95'
            }`}
          >
            <div
              className={`w-12 h-12 ${item.color} rounded-full flex items-center justify-center mx-auto mb-2`}
            >
              <item.icon size={24} className="text-white" />
            </div>
            <p className="font-medium text-sm text-gray-800">{item.label}</p>
            <p className="text-xs text-gray-500 mt-1 line-clamp-1">{item.description}</p>
            {item.badge && <div className="mt-2">{item.badge}</div>}
          </button>
        ))}
      </div>

      {/* 빠른 현황 요약 (연동된 경우) */}
      {isConnected && statusData?.virtual_balance && (
        <div className="bg-white rounded-xl p-4 shadow-sm">
          <h3 className="font-bold text-gray-800 mb-3">빠른 현황</h3>
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500">총 자산</p>
              <p className="text-lg font-bold text-gray-800">
                {statusData.virtual_balance.total_balance?.toLocaleString()}원
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500">총 수익</p>
              <p
                className={`text-lg font-bold ${
                  statusData.virtual_balance.total_profit >= 0
                    ? 'text-red-500'
                    : 'text-blue-500'
                }`}
              >
                {statusData.virtual_balance.total_profit >= 0 ? '+' : ''}
                {statusData.virtual_balance.total_profit?.toLocaleString()}원
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500">보유 종목</p>
              <p className="text-lg font-bold text-gray-800">
                {statusData.holdings?.length || 0}종목
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500">승률</p>
              <p
                className={`text-lg font-bold ${
                  (statusData.performance?.win_rate || 0) >= 50
                    ? 'text-green-600'
                    : 'text-red-600'
                }`}
              >
                {statusData.performance?.win_rate?.toFixed(1) || 0}%
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
