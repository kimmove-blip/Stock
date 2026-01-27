import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
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
  ArrowDownUp,
} from 'lucide-react';

export default function AutoTradeAccount() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [syncMessage, setSyncMessage] = useState(null);

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
    staleTime: 1000 * 30,
    refetchOnWindowFocus: true,
    refetchOnMount: 'always',
    retry: 2,
    retryDelay: 1000,
  });

  // 설정 조회 (초기투자금)
  const { data: settings } = useQuery({
    queryKey: ['autoTradeSettings'],
    queryFn: () => autoTradeAPI.getSettings().then((res) => res.data),
    staleTime: 1000 * 60,
  });

  // 포트폴리오 동기화
  const syncMutation = useMutation({
    mutationFn: () => autoTradeAPI.syncPortfolio(),
    onSuccess: (res) => {
      setSyncMessage(res.data.message);
      queryClient.invalidateQueries(['portfolio']);
      setTimeout(() => setSyncMessage(null), 3000);
    },
    onError: (err) => {
      setSyncMessage(err.response?.data?.detail || '동기화 실패');
      setTimeout(() => setSyncMessage(null), 3000);
    },
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
      {/* 새로고침 & 동기화 버튼 */}
      <div className="flex justify-between items-center">
        <button
          onClick={() => syncMutation.mutate()}
          disabled={syncMutation.isPending}
          className="flex items-center gap-1 text-sm text-purple-600 hover:text-purple-700 transition-colors"
        >
          <ArrowDownUp size={16} className={syncMutation.isPending ? 'animate-pulse' : ''} />
          {syncMutation.isPending ? '동기화 중...' : '홈 보유종목에 동기화'}
        </button>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1 text-sm text-gray-600 hover:text-purple-600 transition-colors"
        >
          <RefreshCw size={16} className={isFetching ? 'animate-spin' : ''} />
          새로고침
        </button>
      </div>

      {/* 동기화 메시지 */}
      {syncMessage && (
        <div className="bg-purple-100 text-purple-700 text-sm px-3 py-2 rounded-lg">
          {syncMessage}
        </div>
      )}

      {/* 총 자산 및 수익률 */}
      {(() => {
        const initialInvestment = settings?.initial_investment || 0;
        const totalAsset = summary?.total_asset || 0;
        const totalProfit = initialInvestment > 0 ? totalAsset - initialInvestment : 0;
        const profitRate = initialInvestment > 0 ? ((totalAsset / initialInvestment) - 1) * 100 : 0;
        const isProfit = totalProfit >= 0;

        return (
          <div className={`bg-gradient-to-r ${
            initialInvestment > 0
              ? (isProfit ? 'from-red-500 to-pink-500' : 'from-blue-500 to-indigo-600')
              : ((summary?.total_profit || 0) >= 0 ? 'from-red-500 to-pink-500' : 'from-blue-500 to-indigo-600')
          } rounded-xl p-4 text-white`}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Wallet size={20} />
                <span className="font-medium">계좌 현황</span>
              </div>
              <span className="text-xs px-2 py-0.5 rounded-full bg-white/20">
                {data?.is_mock ? '🎮 모의투자' : '💰 실제투자'}
              </span>
            </div>

            {/* 초기투자금 대비 수익률 */}
            {initialInvestment > 0 ? (
              <>
                <div className="mb-3">
                  <p className="text-xs opacity-80">총 수익</p>
                  <div className="flex items-end gap-2">
                    <p className="text-3xl font-bold">
                      {isProfit ? '+' : ''}{totalProfit.toLocaleString()}원
                    </p>
                    <p className="text-lg opacity-90 mb-1">
                      ({isProfit ? '+' : ''}{profitRate.toFixed(2)}%)
                    </p>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-2 pt-3 border-t border-white/20">
                  <div>
                    <p className="text-xs opacity-70">초기투자금</p>
                    <p className="text-sm font-medium">{initialInvestment.toLocaleString()}원</p>
                  </div>
                  <div>
                    <p className="text-xs opacity-70">평가금액</p>
                    <p className="text-sm font-medium">{(summary?.total_evaluation || 0).toLocaleString()}원</p>
                  </div>
                  <div>
                    <p className="text-xs opacity-70">예수금</p>
                    <p className="text-sm font-medium">{(balance?.cash || 0).toLocaleString()}원</p>
                  </div>
                </div>
              </>
            ) : (
              <>
                <div className="mb-3">
                  <p className="text-xs opacity-80">평가손익</p>
                  <div className="flex items-end gap-2">
                    <p className="text-3xl font-bold">
                      {(summary?.total_profit || 0) >= 0 ? '+' : ''}{(summary?.total_profit || 0).toLocaleString()}원
                    </p>
                    <p className="text-lg opacity-90 mb-1">
                      ({(summary?.profit_rate || 0) >= 0 ? '+' : ''}{(summary?.profit_rate || 0).toFixed(2)}%)
                    </p>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-2 pt-3 border-t border-white/20">
                  <div>
                    <p className="text-xs opacity-70">매입금액</p>
                    <p className="text-sm font-medium">{(summary?.total_purchase || 0).toLocaleString()}원</p>
                  </div>
                  <div>
                    <p className="text-xs opacity-70">평가금액</p>
                    <p className="text-sm font-medium">{(summary?.total_evaluation || 0).toLocaleString()}원</p>
                  </div>
                  <div>
                    <p className="text-xs opacity-70">예수금</p>
                    <p className="text-sm font-medium">{(balance?.cash || 0).toLocaleString()}원</p>
                  </div>
                </div>
              </>
            )}
          </div>
        );
      })()}

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
