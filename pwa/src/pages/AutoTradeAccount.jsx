import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { autoTradeAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import Loading from '../components/Loading';
import {
  Wallet,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  AlertCircle,
  PiggyBank,
  BarChart3,
} from 'lucide-react';

export default function AutoTradeAccount() {
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
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['autoTradeAccount'],
    queryFn: () => autoTradeAPI.getAccount().then((res) => res.data),
    staleTime: 1000 * 30, // 30초 캐시
    refetchOnWindowFocus: true,
  });

  if (isLoading) return <Loading text="계좌 현황 불러오는 중..." />;

  if (error) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="text-center">
          <AlertCircle size={48} className="mx-auto text-red-400 mb-4" />
          <h2 className="text-lg font-bold text-gray-700 mb-2">
            {error.response?.status === 403 ? 'API 연동 필요' : '오류 발생'}
          </h2>
          <p className="text-gray-500 text-sm mb-4">
            {error.response?.data?.detail || '계좌 정보를 불러올 수 없습니다.'}
          </p>
          {error.response?.status === 403 && (
            <button
              onClick={() => navigate('/auto-trade/api-key')}
              className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
            >
              API 키 설정하기
            </button>
          )}
        </div>
      </div>
    );
  }

  const { balance, holdings, summary } = data || {};

  return (
    <div className="max-w-md mx-auto space-y-4">
      {/* 새로고침 버튼 */}
      <div className="flex justify-end">
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1 text-sm text-gray-600 hover:text-purple-600 transition-colors"
        >
          <RefreshCw size={16} className={isFetching ? 'animate-spin' : ''} />
          새로고침
        </button>
      </div>

      {/* 총 자산 */}
      <div className={`bg-gradient-to-r ${data?.is_mock ? 'from-blue-500 to-indigo-600' : 'from-green-500 to-emerald-600'} rounded-xl p-4 text-white`}>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Wallet size={20} />
            <span className="font-medium">계좌 잔고</span>
          </div>
          <span className={`text-xs px-2 py-0.5 rounded-full ${data?.is_mock ? 'bg-white/20' : 'bg-white/20'}`}>
            {data?.is_mock ? '🎮 모의투자' : '💰 실제투자'}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <p className="text-xs text-green-100">총 자산</p>
            <p className="text-2xl font-bold">{summary?.total_asset?.toLocaleString() || 0}원</p>
          </div>
          <div>
            <p className="text-xs text-green-100">예수금</p>
            <p className="text-xl font-bold">{balance?.cash?.toLocaleString() || 0}원</p>
          </div>
        </div>
      </div>

      {/* 평가손익 */}
      <div className="bg-white rounded-xl p-4 shadow-sm">
        <div className="flex items-center gap-2 mb-3">
          <BarChart3 size={20} className="text-blue-600" />
          <span className="font-bold">평가손익</span>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-gray-50 rounded-lg p-3">
            <p className="text-xs text-gray-500">매입금액</p>
            <p className="text-lg font-bold">{summary?.total_purchase?.toLocaleString() || 0}원</p>
          </div>
          <div className="bg-gray-50 rounded-lg p-3">
            <p className="text-xs text-gray-500">평가금액</p>
            <p className="text-lg font-bold">{summary?.total_evaluation?.toLocaleString() || 0}원</p>
          </div>
          <div className="bg-gray-50 rounded-lg p-3 col-span-2">
            <div className="flex justify-between items-center">
              <p className="text-xs text-gray-500">평가손익</p>
              <p
                className={`text-xl font-bold ${
                  (summary?.total_profit || 0) >= 0 ? 'text-red-500' : 'text-blue-500'
                }`}
              >
                {(summary?.total_profit || 0) >= 0 ? '+' : ''}
                {summary?.total_profit?.toLocaleString() || 0}원
                <span className="text-sm ml-1">
                  ({(summary?.profit_rate || 0) >= 0 ? '+' : ''}
                  {summary?.profit_rate?.toFixed(2) || 0}%)
                </span>
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* 보유 종목 */}
      <div className="bg-white rounded-xl p-4 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <PiggyBank size={20} className="text-purple-600" />
            <span className="font-bold">보유 종목</span>
          </div>
          <span className="text-sm text-gray-500">{holdings?.length || 0}종목</span>
        </div>

        {holdings?.length > 0 ? (
          <div className="space-y-3">
            {holdings.map((holding) => (
              <div
                key={holding.stock_code}
                className="flex justify-between items-center p-3 bg-gray-50 rounded-lg cursor-pointer hover:bg-gray-100 transition-colors"
                onClick={() => navigate(`/stock/${holding.stock_code}`)}
              >
                <div className="flex-1">
                  <p className="font-medium text-gray-800">
                    {holding.stock_name || holding.stock_code}
                  </p>
                  <p className="text-xs text-gray-500">
                    {holding.quantity?.toLocaleString()}주 | 평단가{' '}
                    {holding.avg_price?.toLocaleString()}원
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-medium">
                    {holding.current_price?.toLocaleString() || '-'}원
                  </p>
                  <p
                    className={`text-sm font-bold ${
                      (holding.profit_rate || 0) >= 0 ? 'text-red-500' : 'text-blue-500'
                    }`}
                  >
                    {(holding.profit_rate || 0) >= 0 ? (
                      <TrendingUp size={12} className="inline mr-1" />
                    ) : (
                      <TrendingDown size={12} className="inline mr-1" />
                    )}
                    {(holding.profit_rate || 0) >= 0 ? '+' : ''}
                    {holding.profit_rate?.toFixed(2) || 0}%
                  </p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-gray-400">
            <PiggyBank size={32} className="mx-auto mb-2" />
            <p>보유 종목이 없습니다</p>
          </div>
        )}
      </div>
    </div>
  );
}
