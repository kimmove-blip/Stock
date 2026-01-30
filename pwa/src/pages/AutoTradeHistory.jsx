import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { autoTradeAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import Loading from '../components/Loading';
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  AlertCircle,
  Calendar,
  RefreshCw,
  Filter,
} from 'lucide-react';

export default function AutoTradeHistory() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [days, setDays] = useState(1);
  const [sideFilter, setSideFilter] = useState('all');

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

  // 거래 내역 조회
  const { data: trades, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['autoTradeTrades', days],
    queryFn: () => autoTradeAPI.trades(days).then((res) => res.data),
    staleTime: 1000 * 60,
    refetchOnWindowFocus: true,
  });

  const filteredTrades = trades?.filter((trade) => {
    if (sideFilter === 'all') return true;
    return trade.side === sideFilter;
  });

  // 요약 통계 계산
  const summary = trades?.reduce(
    (acc, trade) => {
      if (trade.side === 'buy') {
        acc.buyCount++;
        acc.buyAmount += trade.amount || 0;
      } else {
        acc.sellCount++;
        acc.sellAmount += trade.amount || 0;
        if (trade.profit_loss !== null && trade.profit_loss !== undefined) {
          if (trade.profit_loss >= 0) {
            acc.profitCount++;
            acc.profitAmount += trade.profit_loss || 0;
          } else {
            acc.lossCount++;
            acc.lossAmount += trade.profit_loss || 0;
          }
          acc.totalProfitRate += trade.profit_rate || 0;
        } else {
          acc.unknownCount++;  // 손익 미확인
        }
      }
      return acc;
    },
    { buyCount: 0, sellCount: 0, buyAmount: 0, sellAmount: 0, profitCount: 0, lossCount: 0, profitAmount: 0, lossAmount: 0, unknownCount: 0, totalProfitRate: 0 }
  ) || { buyCount: 0, sellCount: 0, buyAmount: 0, sellAmount: 0, profitCount: 0, lossCount: 0, profitAmount: 0, lossAmount: 0, unknownCount: 0, totalProfitRate: 0 };

  if (isLoading) return <Loading text="거래 내역 불러오는 중..." />;

  const dayOptions = [
    { value: 1, label: '당일' },
    { value: 7, label: '7일' },
    { value: 30, label: '30일' },
    { value: 90, label: '90일' },
  ];

  return (
    <div className="max-w-md mx-auto space-y-4">
      {/* 기간 선택 */}
      <div className="flex items-center justify-between bg-white rounded-xl p-3 shadow-sm">
        <div className="flex items-center gap-2">
          <Calendar size={18} className="text-gray-500" />
          <span className="text-sm text-gray-600">조회 기간</span>
        </div>
        <div className="flex gap-1">
          {dayOptions.map((option) => (
            <button
              key={option.value}
              onClick={() => setDays(option.value)}
              className={`px-3 py-1 rounded-lg text-sm font-medium transition-colors ${
                days === option.value
                  ? 'bg-purple-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {option.label}
            </button>
          ))}
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="p-1 text-gray-500 hover:text-purple-600 transition-colors"
          >
            <RefreshCw size={18} className={isFetching ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* 요약 통계 */}
      <div className="bg-white rounded-xl p-4 shadow-sm">
        <h3 className="font-bold text-gray-800 mb-3 flex items-center gap-2">
          <BarChart3 size={18} className="text-indigo-600" />
          거래 요약
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-red-50 rounded-lg p-3">
            <p className="text-xs text-red-600">매수</p>
            <p className="text-lg font-bold text-red-700">{summary.buyCount}건</p>
            <p className="text-xs text-red-500">{summary.buyAmount?.toLocaleString()}원</p>
          </div>
          <div className="bg-blue-50 rounded-lg p-3">
            <p className="text-xs text-blue-600">매도</p>
            <p className="text-lg font-bold text-blue-700">{summary.sellCount}건</p>
            <p className="text-xs text-blue-500">{summary.sellAmount?.toLocaleString()}원</p>
          </div>
          <div className="bg-green-50 rounded-lg p-3">
            <p className="text-xs text-green-600">수익</p>
            <p className="text-lg font-bold text-green-700">{summary.profitCount}건</p>
            <p className="text-xs text-green-500">+{summary.profitAmount?.toLocaleString()}원</p>
          </div>
          <div className="bg-gray-50 rounded-lg p-3">
            <p className="text-xs text-gray-600">손실</p>
            <p className="text-lg font-bold text-gray-700">{summary.lossCount}건</p>
            <p className="text-xs text-red-500">{summary.lossAmount?.toLocaleString()}원</p>
          </div>
        </div>
        {summary.unknownCount > 0 && (
          <p className="text-xs text-gray-400 mt-2 text-center">
            * 손익 미확인 {summary.unknownCount}건 (매수 내역 없음)
          </p>
        )}
      </div>

      {/* 필터 */}
      <div className="flex items-center gap-2 bg-white rounded-xl p-2 shadow-sm">
        <Filter size={16} className="text-gray-500 ml-2" />
        {[
          { value: 'all', label: '전체' },
          { value: 'buy', label: '매수' },
          { value: 'sell', label: '매도' },
        ].map((f) => (
          <button
            key={f.value}
            onClick={() => setSideFilter(f.value)}
            className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-colors ${
              sideFilter === f.value
                ? 'bg-purple-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* 거래 내역 목록 */}
      {filteredTrades?.length > 0 ? (
        <div className="space-y-2">
          {filteredTrades.map((trade) => (
            <div
              key={trade.id}
              className="bg-white rounded-xl p-4 shadow-sm cursor-pointer hover:bg-gray-50 transition-colors"
              onClick={() => navigate(`/stock/${trade.stock_code}`)}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <span
                    className={`text-xs px-2 py-1 rounded font-medium ${
                      trade.side === 'buy'
                        ? 'bg-red-100 text-red-600'
                        : 'bg-blue-100 text-blue-600'
                    }`}
                  >
                    {trade.side === 'buy' ? '매수' : '매도'}
                  </span>
                  <div>
                    <p className="font-medium text-gray-800">
                      {trade.stock_name || trade.stock_code}
                    </p>
                    <p className="text-xs text-gray-500">
                      {trade.trade_date} {trade.trade_time}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="font-medium text-gray-800">
                    {trade.quantity}주 × {trade.price?.toLocaleString()}원
                  </p>
                  <p className="text-sm text-gray-500">{trade.amount?.toLocaleString()}원</p>
                </div>
              </div>

              {/* 매도 시 손익 표시 */}
              {trade.side === 'sell' && trade.profit_rate !== null && (
                <div
                  className={`mt-2 flex items-center justify-between p-2 rounded-lg ${
                    trade.profit_rate >= 0 ? 'bg-red-50' : 'bg-blue-50'
                  }`}
                >
                  <span className="text-xs text-gray-600">손익</span>
                  <span
                    className={`font-bold flex items-center gap-1 ${
                      trade.profit_rate >= 0 ? 'text-red-600' : 'text-blue-600'
                    }`}
                  >
                    {trade.profit_rate >= 0 ? (
                      <TrendingUp size={14} />
                    ) : (
                      <TrendingDown size={14} />
                    )}
                    {trade.profit_rate >= 0 ? '+' : ''}
                    {trade.profit_loss?.toLocaleString()}원 ({trade.profit_rate?.toFixed(2)}%)
                  </span>
                </div>
              )}

              {/* 거래 사유 */}
              {trade.trade_reason && (
                <p className="mt-2 text-xs text-gray-500 bg-gray-50 p-2 rounded-lg">
                  {trade.trade_reason}
                </p>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="bg-white rounded-xl p-8 shadow-sm text-center">
          <BarChart3 size={48} className="mx-auto text-gray-300 mb-3" />
          <p className="text-gray-500">거래 내역이 없습니다</p>
          <p className="text-xs text-gray-400 mt-2">
            자동매매가 실행되면 이곳에 기록됩니다
          </p>
        </div>
      )}
    </div>
  );
}
