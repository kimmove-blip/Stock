import { useState, useEffect, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { top100API, realtimeAPI, portfolioAPI, watchlistAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { Zap, TrendingUp, TrendingDown, RefreshCw, Brain, Activity } from 'lucide-react';

// AI 분석 중 로딩 컴포넌트
function AnalyzingLoader() {
  const [step, setStep] = useState(0);
  const steps = [
    { text: '시장 데이터 수집 중...', icon: Activity },
    { text: 'AI 기술적 분석 중...', icon: Brain },
    { text: '매수 신호 탐지 중...', icon: Zap },
    { text: '종목 순위 계산 중...', icon: TrendingUp },
  ];

  useEffect(() => {
    const interval = setInterval(() => {
      setStep((prev) => (prev + 1) % steps.length);
    }, 500);
    return () => clearInterval(interval);
  }, []);

  const CurrentIcon = steps[step].icon;

  return (
    <div className="min-h-screen bg-gradient-to-br from-red-500 to-orange-500 flex items-center justify-center">
      <div className="text-center text-white">
        <div className="w-20 h-20 mx-auto mb-6 bg-white/20 rounded-full flex items-center justify-center animate-pulse">
          <CurrentIcon size={40} className="animate-bounce" />
        </div>
        <h2 className="text-xl font-bold mb-2">AI 실시간 분석</h2>
        <p className="text-white/80 mb-4">{steps[step].text}</p>
        <div className="flex justify-center gap-2">
          {steps.map((_, idx) => (
            <div
              key={idx}
              className={`w-2 h-2 rounded-full transition-all ${
                idx === step ? 'bg-white w-6' : 'bg-white/40'
              }`}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function RealtimePicks() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const scoreVersion = user?.score_version || 'v5';
  const [realtimePrices, setRealtimePrices] = useState({});
  const [lastUpdate, setLastUpdate] = useState(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);

  // 세션에서 이미 본 적 있으면 애니메이션 스킵
  const hasSeenAnimation = sessionStorage.getItem('realtimeAnalyzingSeen');
  const [showAnalyzing, setShowAnalyzing] = useState(!hasSeenAnimation);

  // TOP100 데이터 조회 (종목 목록) - 사용자의 스코어 엔진 사용
  const { data, isLoading } = useQuery({
    queryKey: ['top100', scoreVersion],
    queryFn: () => top100API.list(null, scoreVersion).then((res) => res.data),
  });

  // 보유종목/관심종목 데이터
  const { data: portfolio } = useQuery({
    queryKey: ['portfolio'],
    queryFn: () => portfolioAPI.list().then((res) => res.data),
    staleTime: 1000 * 60 * 5,
  });

  const { data: watchlist } = useQuery({
    queryKey: ['watchlist'],
    queryFn: () => watchlistAPI.list().then((res) => res.data),
    staleTime: 1000 * 60 * 5,
  });

  // 보유/관심 여부 확인 함수
  const isInPortfolio = (code) =>
    portfolio?.items?.some((item) => item.stock_code === code);
  const isInWatchlist = (code) =>
    watchlist?.items?.some((item) => item.stock_code === code);

  // 초기 로딩 시 2초간 분석 애니메이션 표시 (첫 방문시만)
  useEffect(() => {
    if (!hasSeenAnimation) {
      const timer = setTimeout(() => {
        setShowAnalyzing(false);
        sessionStorage.setItem('realtimeAnalyzingSeen', 'true');
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [hasSeenAnimation]);

  // 실시간 시세 조회 함수 (캐시 스킵 - 항상 최신 데이터만)
  const fetchRealtimePrices = useCallback(async (codes) => {
    if (!codes || codes.length === 0) return;

    try {
      setIsRefreshing(true);

      // 실시간 시세만 조회 (캐시된 데이터 사용 안함 - 오래된 데이터 표시 방지)
      const response = await realtimeAPI.prices(codes);
      if (response.data?.prices) {
        const priceMap = {};
        response.data.prices.forEach((p) => {
          priceMap[p.stock_code] = {
            current_price: p.current_price,
            change: p.change,
            change_rate: p.change_rate,
            volume: p.volume,
          };
        });
        setRealtimePrices(priceMap);
        setLastUpdate(new Date());
      }
    } catch (error) {
      console.error('시세 조회 실패:', error);
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  // 데이터 로드 후 실시간 시세 조회
  useEffect(() => {
    if (data?.items && !showAnalyzing) {
      const codes = data.items.slice(0, 20).map((item) => item.code);
      fetchRealtimePrices(codes);
    }
  }, [data, fetchRealtimePrices, showAnalyzing]);

  // 자동 갱신 (30초 간격)
  useEffect(() => {
    if (!autoRefresh || !data?.items || showAnalyzing) return;

    const interval = setInterval(() => {
      const codes = data.items.slice(0, 20).map((item) => item.code);
      fetchRealtimePrices(codes);
    }, 30000); // 30초

    return () => clearInterval(interval);
  }, [autoRefresh, data, fetchRealtimePrices, showAnalyzing]);

  // 수동 새로고침 (이전 데이터 즉시 삭제 후 새로 조회)
  const handleRefresh = () => {
    if (data?.items) {
      // 이전 실시간 데이터 삭제 (오래된 데이터 표시 방지)
      setRealtimePrices({});
      const codes = data.items.slice(0, 20).map((item) => item.code);
      fetchRealtimePrices(codes);
    }
  };

  // 분석 애니메이션 또는 데이터 로딩 중 또는 실시간 시세 첫 로딩 중
  // (실시간 데이터 없으면 로딩 표시 - 오래된 TOP100 데이터 표시 방지)
  const hasRealtimeData = Object.keys(realtimePrices).length > 0;
  if (showAnalyzing || isLoading || (!hasRealtimeData && data?.items)) {
    return <AnalyzingLoader />;
  }

  const items = data?.items?.slice(0, 20) || [];

  // 종목 데이터에 실시간 시세 병합 (실시간 데이터 없으면 TOP100 데이터 사용)
  const getStockData = (stock) => {
    const realtime = realtimePrices[stock.code];
    if (realtime) {
      return {
        ...stock,
        current_price: realtime.current_price || stock.current_price,
        change: realtime.change,
        // 실시간 change_rate가 없으면 TOP100의 change_rate 사용
        change_rate: realtime.change_rate ?? stock.change_rate,
        volume: realtime.volume,
      };
    }
    return stock;
  };

  return (
    <div className="max-w-md mx-auto">
      {/* 상단 컨트롤 바 */}
      <div className="flex items-center justify-between mb-3">
        <button
          onClick={handleRefresh}
          disabled={isRefreshing}
          className="btn btn-sm btn-ghost gap-2"
        >
          <RefreshCw size={16} className={isRefreshing ? 'animate-spin' : ''} />
          새로고침
        </button>
        <button
          onClick={() => setAutoRefresh(!autoRefresh)}
          className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
            autoRefresh
              ? 'bg-green-100 text-green-600'
              : 'bg-gray-100 text-gray-500'
          }`}
        >
          {autoRefresh ? '자동갱신 ON' : '자동갱신 OFF'}
        </button>
      </div>

      {/* 마지막 업데이트 시간 */}
      <div className="text-xs text-gray-500 mb-3">
        {lastUpdate
          ? `실시간 시세: ${lastUpdate.toLocaleTimeString('ko-KR')}`
          : '시세 조회 중...'}
      </div>

      {/* 종목 리스트 */}
      <div className="space-y-3">
        {items.map((stock, idx) => {
          const stockData = getStockData(stock);
          const changeRate = stockData.change_rate;
          const hasChangeRate = changeRate !== null && changeRate !== undefined;

          return (
            <div
              key={stock.code}
              onClick={() => navigate(`/stock/${stock.code}`, {
                state: {
                  top100Score: stockData.score,
                  preloadedData: {
                    code: stockData.code,
                    name: stockData.name,
                    current_price: stockData.current_price,
                    change: stockData.change,
                    change_rate: stockData.change_rate,
                    volume: stockData.volume,
                    score: stockData.score,
                    signals: stockData.signals,
                  }
                }
              })}
              className="bg-white rounded-xl p-4 shadow-sm flex items-center gap-3 cursor-pointer hover:shadow-md transition-shadow"
            >
              <div className="w-8 h-8 bg-red-500 rounded-full flex items-center justify-center text-white font-bold text-sm">
                {idx + 1}
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-gray-800">{stockData.name}</h3>
                <div className="flex items-center gap-1.5">
                  <p className="text-sm text-gray-500">{stockData.code}</p>
                  {isInPortfolio(stock.code) && (
                    <span className="bg-blue-100 text-blue-600 text-[10px] px-1.5 py-0.5 rounded font-medium">
                      보유
                    </span>
                  )}
                  {isInWatchlist(stock.code) && (
                    <span className="bg-yellow-100 text-yellow-600 text-[10px] px-1.5 py-0.5 rounded font-medium">
                      관심
                    </span>
                  )}
                </div>
              </div>
              <div className="text-right">
                <p className="font-semibold">
                  {stockData.current_price?.toLocaleString()}원
                </p>
                {hasChangeRate ? (
                  <p
                    className={`text-sm flex items-center justify-end gap-1 ${
                      changeRate >= 0 ? 'text-red-500' : 'text-blue-500'
                    }`}
                  >
                    {changeRate >= 0 ? (
                      <TrendingUp size={14} />
                    ) : (
                      <TrendingDown size={14} />
                    )}
                    {changeRate >= 0 ? '+' : ''}
                    {changeRate.toFixed(2)}%
                  </p>
                ) : (
                  <p className="text-sm text-gray-400">-</p>
                )}
              </div>
              <div className="bg-orange-100 text-orange-600 px-2 py-1 rounded-lg text-sm font-medium">
                {stockData.score}점
              </div>
            </div>
          );
        })}
      </div>

      {items.length === 0 && (
        <div className="text-center py-10 text-gray-500">
          추천 종목이 없습니다
        </div>
      )}
    </div>
  );
}
