import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { portfolioAPI } from '../api/client';
import Loading from '../components/Loading';
import {
  Stethoscope,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  CheckCircle,
  XCircle,
  RefreshCw,
  AlertCircle,
  ArrowUpDown,
} from 'lucide-react';

const SORT_OPTIONS = [
  { value: 'holding_value', label: '보유금액순' },
  { value: 'profit_amount', label: '수익액순' },
  { value: 'profit_rate', label: '수익률순' },
  { value: 'buy_date', label: '매입일순' },
];

export default function PortfolioDiagnosis() {
  const navigate = useNavigate();
  const [sortBy, setSortBy] = useState('holding_value');

  // 보유종목 진단 조회
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['portfolioDiagnosis', sortBy],
    queryFn: () => portfolioAPI.diagnosis(sortBy).then((res) => res.data),
    staleTime: 1000 * 60 * 5, // 5분 캐시
    refetchOnWindowFocus: true,
  });

  if (isLoading) return <Loading text="보유종목 진단 중..." />;

  if (error) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="text-center">
          <AlertCircle size={48} className="mx-auto text-red-400 mb-4" />
          <h2 className="text-lg font-bold text-gray-700 mb-2">오류 발생</h2>
          <p className="text-gray-500 text-sm mb-4">
            {error.response?.data?.detail || '진단 정보를 불러올 수 없습니다.'}
          </p>
          <button
            onClick={() => refetch()}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
          >
            다시 시도
          </button>
        </div>
      </div>
    );
  }

  const { holdings = [], summary = {} } = data || {};

  const getSignalColor = (signal) => {
    switch (signal) {
      case 'strong_buy':
        return 'bg-red-500 text-white';
      case 'buy':
        return 'bg-red-100 text-red-600';
      case 'hold':
        return 'bg-gray-100 text-gray-600';
      case 'take_profit':
        return 'bg-green-100 text-green-600';
      case 'sell':
        return 'bg-blue-100 text-blue-600';
      case 'strong_sell':
        return 'bg-blue-500 text-white';
      default:
        return 'bg-gray-100 text-gray-600';
    }
  };

  const getSignalText = (signal) => {
    switch (signal) {
      case 'strong_buy':
        return '강력 매수';
      case 'buy':
        return '매수';
      case 'hold':
        return '보유';
      case 'take_profit':
        return '익절 고려';
      case 'sell':
        return '매도';
      case 'strong_sell':
        return '강력 매도';
      default:
        return '-';
    }
  };

  const getHealthIcon = (health) => {
    if (health >= 80) return <CheckCircle size={20} className="text-green-500" />;
    if (health >= 60) return <AlertTriangle size={20} className="text-yellow-500" />;
    return <XCircle size={20} className="text-red-500" />;
  };

  return (
    <div className="max-w-md mx-auto space-y-4">
      {/* 정렬 및 새로고침 */}
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-2">
          <ArrowUpDown size={16} className="text-gray-500" />
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="text-sm border border-gray-200 rounded-lg px-2 py-1 bg-white"
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1 text-sm text-gray-600 hover:text-purple-600 transition-colors"
        >
          <RefreshCw size={16} className={isFetching ? 'animate-spin' : ''} />
          새로고침
        </button>
      </div>

      {/* 전체 요약 */}
      <div className="bg-gradient-to-r from-cyan-500 to-blue-600 rounded-xl p-4 text-white">
        <div className="flex items-center gap-2 mb-3">
          <Stethoscope size={20} />
          <span className="font-medium">포트폴리오 건강도</span>
        </div>
        <div className="grid grid-cols-3 gap-3 text-center">
          <div>
            <p className="text-3xl font-bold">{summary.health_score || 0}</p>
            <p className="text-xs text-cyan-100">건강 점수</p>
          </div>
          <div>
            <p className="text-3xl font-bold">{holdings.length || 0}</p>
            <p className="text-xs text-cyan-100">보유 종목</p>
          </div>
          <div>
            <p className={`text-3xl font-bold ${(summary.total_profit_rate || 0) >= 0 ? '' : 'text-red-200'}`}>
              {(summary.total_profit_rate || 0) >= 0 ? '+' : ''}
              {summary.total_profit_rate?.toFixed(1) || 0}%
            </p>
            <p className="text-xs text-cyan-100">총 수익률</p>
          </div>
        </div>
      </div>

      {/* 주의 종목 알림 */}
      {summary.warning_count > 0 && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4">
          <div className="flex items-center gap-2 text-yellow-700">
            <AlertTriangle size={20} />
            <span className="font-medium">
              {summary.warning_count}개 종목이 주의가 필요합니다
            </span>
          </div>
        </div>
      )}

      {/* 보유 종목 진단 목록 */}
      {holdings.length > 0 ? (
        <div className="space-y-3">
          {holdings.map((holding) => (
            <div
              key={holding.stock_code}
              className="bg-white rounded-xl p-4 shadow-sm"
            >
              {/* 헤더 */}
              <div
                className="flex items-start justify-between mb-3 cursor-pointer"
                onClick={() => navigate(`/stock/${holding.stock_code}`)}
              >
                <div>
                  <div className="flex items-center gap-2">
                    {getHealthIcon(holding.health_score || 50)}
                    <p className="font-bold text-gray-800">{holding.stock_name}</p>
                    <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
                      (holding.health_score || 50) >= 80 ? 'bg-green-100 text-green-600' :
                      (holding.health_score || 50) >= 60 ? 'bg-yellow-100 text-yellow-600' :
                      'bg-red-100 text-red-600'
                    }`}>
                      {holding.health_score || 50}점
                    </span>
                  </div>
                  <p className="text-xs text-gray-500">{holding.stock_code}</p>
                </div>
                <span className={`text-xs px-2 py-1 rounded-full font-medium ${getSignalColor(holding.signal)}`}>
                  {getSignalText(holding.signal)}
                </span>
              </div>

              {/* 가격 정보 */}
              <div className="grid grid-cols-2 gap-2 mb-3 bg-gray-50 rounded-lg p-3">
                <div>
                  <p className="text-xs text-gray-500">현재가</p>
                  <p className="font-bold text-gray-800">
                    {holding.current_price?.toLocaleString()}원
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">평균단가</p>
                  <p className="font-bold text-gray-800">
                    {holding.avg_price?.toLocaleString()}원
                  </p>
                </div>
              </div>

              {/* 보유금액, 수익액, 수익률 */}
              <div className="grid grid-cols-3 gap-2 bg-gray-50 rounded-lg p-3">
                <div>
                  <p className="text-xs text-gray-500">보유금액</p>
                  <p className="font-bold text-gray-800 text-sm">
                    {holding.holding_value?.toLocaleString()}원
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">수익액</p>
                  <p className={`font-bold text-sm ${
                    (holding.profit_amount || 0) >= 0 ? 'text-red-600' : 'text-blue-600'
                  }`}>
                    {(holding.profit_amount || 0) >= 0 ? '+' : ''}
                    {holding.profit_amount?.toLocaleString()}원
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">수익률</p>
                  <p className={`font-bold flex items-center text-sm ${
                    (holding.profit_rate || 0) >= 0 ? 'text-red-600' : 'text-blue-600'
                  }`}>
                    {(holding.profit_rate || 0) >= 0 ? (
                      <TrendingUp size={14} className="mr-1" />
                    ) : (
                      <TrendingDown size={14} className="mr-1" />
                    )}
                    {(holding.profit_rate || 0) >= 0 ? '+' : ''}
                    {holding.profit_rate?.toFixed(2)}%
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="bg-white rounded-xl p-8 shadow-sm text-center">
          <Stethoscope size={48} className="mx-auto text-gray-300 mb-3" />
          <p className="text-gray-500">보유 종목이 없습니다</p>
          <p className="text-xs text-gray-400 mt-2">
            포트폴리오에 종목을 추가하면 AI가 자동으로 진단해드립니다
          </p>
        </div>
      )}
    </div>
  );
}
