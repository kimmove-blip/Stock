import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { autoTradeAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import Loading from '../components/Loading';
import {
  TrendingUp,
  TrendingDown,
  AlertCircle,
  Calendar,
  RefreshCw,
  Trophy,
  Target,
  PieChart,
  BarChart3,
} from 'lucide-react';

export default function AutoTradePerformance() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [days, setDays] = useState(30);

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

  // 성과 분석 조회
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['autoTradePerformance', days],
    queryFn: () => autoTradeAPI.performance(days).then((res) => res.data),
    staleTime: 1000 * 60,
    refetchOnWindowFocus: true,
  });

  if (isLoading) return <Loading text="성과 분석 불러오는 중..." />;

  const dayOptions = [
    { value: 1, label: '당일' },
    { value: 7, label: '7일' },
    { value: 30, label: '30일' },
    { value: 90, label: '90일' },
    { value: 365, label: '1년' },
  ];

  const {
    total_trades = 0,
    win_count = 0,
    loss_count = 0,
    win_rate = 0,
    total_profit = 0,
    total_profit_rate = 0,
    avg_profit_rate = 0,
    avg_hold_days = 0,
    best_trade = null,
    worst_trade = null,
    stock_performance = [],
    monthly_performance = [],
    initial_investment = 0,
    current_total_asset = 0,
    total_profit_from_initial = 0,
    total_profit_rate_from_initial = 0,
  } = data || {};

  return (
    <div className="max-w-md mx-auto space-y-4">
      {/* 기간 선택 */}
      <div className="flex items-center justify-between bg-white rounded-xl p-3 shadow-sm">
        <div className="flex items-center gap-2">
          <Calendar size={18} className="text-gray-500" />
          <span className="text-sm text-gray-600">분석 기간</span>
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

      {/* 총 수익 (초기투자금 기준) */}
      {initial_investment > 0 ? (
        <div
          className={`rounded-xl p-4 ${
            total_profit_from_initial >= 0
              ? 'bg-gradient-to-r from-red-500 to-pink-500'
              : 'bg-gradient-to-r from-blue-500 to-indigo-500'
          } text-white`}
        >
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              {total_profit_from_initial >= 0 ? <TrendingUp size={20} /> : <TrendingDown size={20} />}
              <span className="font-medium">총 수익</span>
            </div>
            <span className="text-xs opacity-70">초기투자금 기준</span>
          </div>
          <div className="flex items-end gap-2">
            <p className="text-3xl font-bold">
              {total_profit_from_initial >= 0 ? '+' : ''}
              {total_profit_from_initial?.toLocaleString()}원
            </p>
            <p className="text-lg opacity-80 mb-1">
              ({total_profit_rate_from_initial >= 0 ? '+' : ''}
              {total_profit_rate_from_initial?.toFixed(2)}%)
            </p>
          </div>
          <div className="mt-3 pt-3 border-t border-white/20 grid grid-cols-2 gap-2 text-sm">
            <div>
              <p className="opacity-70">초기투자금</p>
              <p className="font-medium">{initial_investment?.toLocaleString()}원</p>
            </div>
            <div>
              <p className="opacity-70">현재 총자산</p>
              <p className="font-medium">{current_total_asset?.toLocaleString()}원</p>
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-xl p-4 bg-gradient-to-r from-gray-500 to-gray-600 text-white">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp size={20} />
            <span className="font-medium">총 수익</span>
          </div>
          <p className="text-lg mb-2">초기투자금을 설정하면 총수익을 확인할 수 있습니다</p>
          <p className="text-xs opacity-70">
            자동매매 설정 &gt; 초기 투자금에서 설정하세요
          </p>
        </div>
      )}

      {/* 손익 상세 (실현손익 + 미실현손익) */}
      {initial_investment > 0 && (
        <div className="bg-white rounded-xl p-4 shadow-sm">
          <h3 className="font-bold text-gray-800 mb-3">손익 구성</h3>
          <div className="space-y-3">
            {/* 실현손익 */}
            <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
              <div>
                <p className="text-sm text-gray-500">실현손익</p>
                <p className="text-xs text-gray-400">매도 완료 종목</p>
              </div>
              <p className={`text-lg font-bold ${total_profit >= 0 ? 'text-red-600' : 'text-blue-600'}`}>
                {total_profit >= 0 ? '+' : ''}{total_profit?.toLocaleString()}원
              </p>
            </div>
            {/* 미실현손익 */}
            <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
              <div>
                <p className="text-sm text-gray-500">미실현손익</p>
                <p className="text-xs text-gray-400">보유 중인 종목</p>
              </div>
              <p className={`text-lg font-bold ${(total_profit_from_initial - total_profit) >= 0 ? 'text-red-600' : 'text-blue-600'}`}>
                {(total_profit_from_initial - total_profit) >= 0 ? '+' : ''}{(total_profit_from_initial - total_profit)?.toLocaleString()}원
              </p>
            </div>
            {/* 합계 = 총수익 */}
            <div className="flex items-center justify-between p-3 border-t border-gray-200 pt-3">
              <p className="text-sm font-medium text-gray-700">합계 (= 총수익)</p>
              <p className={`text-lg font-bold ${total_profit_from_initial >= 0 ? 'text-red-600' : 'text-blue-600'}`}>
                {total_profit_from_initial >= 0 ? '+' : ''}{total_profit_from_initial?.toLocaleString()}원
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 실현 손익 (초기투자금 미설정 시만 표시) */}
      {initial_investment <= 0 && (
        <div
          className={`rounded-xl p-4 ${
            total_profit >= 0
              ? 'bg-gradient-to-r from-orange-400 to-red-400'
              : 'bg-gradient-to-r from-cyan-400 to-blue-400'
          } text-white`}
        >
          <div className="flex items-center gap-2 mb-2">
            {total_profit >= 0 ? <TrendingUp size={20} /> : <TrendingDown size={20} />}
            <span className="font-medium">실현 손익</span>
          </div>
          <div className="flex items-end gap-2">
            <p className="text-2xl font-bold">
              {total_profit >= 0 ? '+' : ''}
              {total_profit?.toLocaleString()}원
            </p>
            <p className="text-sm opacity-80 mb-1">
              (매도 완료 종목)
            </p>
          </div>
        </div>
      )}

      {/* 주요 지표 */}
      <div className="bg-white rounded-xl p-4 shadow-sm">
        <h3 className="font-bold text-gray-800 mb-3 flex items-center gap-2">
          <Target size={18} className="text-purple-600" />
          주요 지표
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-gray-50 rounded-lg p-3">
            <p className="text-xs text-gray-500">총 거래</p>
            <p className="text-xl font-bold text-gray-800">{total_trades}건</p>
          </div>
          <div className="bg-gray-50 rounded-lg p-3">
            <p className="text-xs text-gray-500">승률</p>
            <p
              className={`text-xl font-bold ${
                win_rate >= 50 ? 'text-green-600' : 'text-red-600'
              }`}
            >
              {win_rate?.toFixed(1)}%
            </p>
          </div>
          <div className="bg-green-50 rounded-lg p-3">
            <p className="text-xs text-green-600">수익</p>
            <p className="text-xl font-bold text-green-700">{win_count}건</p>
          </div>
          <div className="bg-red-50 rounded-lg p-3">
            <p className="text-xs text-red-600">손실</p>
            <p className="text-xl font-bold text-red-700">{loss_count}건</p>
          </div>
          <div className="bg-gray-50 rounded-lg p-3">
            <p className="text-xs text-gray-500">평균 수익률</p>
            <p
              className={`text-xl font-bold ${
                avg_profit_rate >= 0 ? 'text-red-600' : 'text-blue-600'
              }`}
            >
              {avg_profit_rate >= 0 ? '+' : ''}
              {avg_profit_rate?.toFixed(2)}%
            </p>
          </div>
          <div className="bg-gray-50 rounded-lg p-3">
            <p className="text-xs text-gray-500">평균 보유일</p>
            <p className="text-xl font-bold text-gray-800">{avg_hold_days?.toFixed(1)}일</p>
          </div>
        </div>
      </div>

      {/* 승률 게이지 */}
      <div className="bg-white rounded-xl p-4 shadow-sm">
        <h3 className="font-bold text-gray-800 mb-3 flex items-center gap-2">
          <PieChart size={18} className="text-blue-600" />
          승률 분포
        </h3>
        <div className="relative h-4 bg-gray-200 rounded-full overflow-hidden">
          <div
            className="absolute left-0 top-0 h-full bg-green-500 transition-all"
            style={{ width: `${win_rate}%` }}
          />
        </div>
        <div className="flex justify-between mt-2 text-sm">
          <span className="text-green-600">수익 {win_count}건 ({win_rate?.toFixed(1)}%)</span>
          <span className="text-red-600">
            손실 {loss_count}건 ({(100 - win_rate)?.toFixed(1)}%)
          </span>
        </div>
      </div>

      {/* 최고/최저 거래 */}
      {(best_trade || worst_trade) && (
        <div className="bg-white rounded-xl p-4 shadow-sm">
          <h3 className="font-bold text-gray-800 mb-3 flex items-center gap-2">
            <Trophy size={18} className="text-yellow-600" />
            베스트/워스트 거래
          </h3>
          <div className="space-y-3">
            {best_trade && (
              <div
                className="flex items-center justify-between p-3 bg-green-50 rounded-lg cursor-pointer hover:bg-green-100 transition-colors"
                onClick={() => navigate(`/stock/${best_trade.stock_code}`)}
              >
                <div className="flex items-center gap-2">
                  <Trophy size={18} className="text-yellow-500" />
                  <div>
                    <p className="font-medium text-gray-800">{best_trade.stock_name}</p>
                    <p className="text-xs text-gray-500">{best_trade.trade_date}</p>
                  </div>
                </div>
                <p className="text-lg font-bold text-red-600">
                  +{best_trade.profit_rate?.toFixed(2)}%
                </p>
              </div>
            )}
            {worst_trade && (
              <div
                className="flex items-center justify-between p-3 bg-red-50 rounded-lg cursor-pointer hover:bg-red-100 transition-colors"
                onClick={() => navigate(`/stock/${worst_trade.stock_code}`)}
              >
                <div className="flex items-center gap-2">
                  <TrendingDown size={18} className="text-blue-500" />
                  <div>
                    <p className="font-medium text-gray-800">{worst_trade.stock_name}</p>
                    <p className="text-xs text-gray-500">{worst_trade.trade_date}</p>
                  </div>
                </div>
                <p className="text-lg font-bold text-blue-600">
                  {worst_trade.profit_rate?.toFixed(2)}%
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 종목별 성과 */}
      {stock_performance?.length > 0 && (
        <div className="bg-white rounded-xl p-4 shadow-sm">
          <h3 className="font-bold text-gray-800 mb-3 flex items-center gap-2">
            <BarChart3 size={18} className="text-indigo-600" />
            종목별 성과
          </h3>
          <div className="space-y-2">
            {stock_performance.slice(0, 5).map((stock, index) => (
              <div
                key={stock.stock_code}
                className="flex items-center justify-between p-2 hover:bg-gray-50 rounded-lg cursor-pointer transition-colors"
                onClick={() => navigate(`/stock/${stock.stock_code}`)}
              >
                <div className="flex items-center gap-2">
                  <span className="w-6 h-6 bg-gray-100 rounded-full flex items-center justify-center text-xs font-medium text-gray-600">
                    {index + 1}
                  </span>
                  <div>
                    <p className="font-medium text-gray-800">{stock.stock_name}</p>
                    <p className="text-xs text-gray-500">{stock.trade_count}회 거래</p>
                  </div>
                </div>
                <p
                  className={`font-bold ${
                    stock.profit_rate >= 0 ? 'text-red-600' : 'text-blue-600'
                  }`}
                >
                  {stock.profit_rate >= 0 ? '+' : ''}
                  {stock.profit_rate?.toFixed(2)}%
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 데이터 없음 */}
      {total_trades === 0 && (
        <div className="bg-white rounded-xl p-8 shadow-sm text-center">
          <TrendingUp size={48} className="mx-auto text-gray-300 mb-3" />
          <p className="text-gray-500">분석할 거래 데이터가 없습니다</p>
          <p className="text-xs text-gray-400 mt-2">
            자동매매가 실행되면 성과를 분석해드립니다
          </p>
        </div>
      )}
    </div>
  );
}
