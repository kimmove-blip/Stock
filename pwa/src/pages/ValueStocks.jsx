import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { valueStocksAPI, realtimeAPI, portfolioAPI, watchlistAPI } from '../api/client';
import { TrendingUp, TrendingDown, Shield, Percent, Building2, Sparkles } from 'lucide-react';
import Loading from '../components/Loading';

// AI 분석 중 로딩 컴포넌트
function AnalyzingLoader() {
  const [step, setStep] = useState(0);
  const steps = [
    { text: '대형우량주 스캔 중...', icon: Building2 },
    { text: 'PER/PBR 분석 중...', icon: Sparkles },
    { text: '배당률 확인 중...', icon: Percent },
    { text: '가치주 선별 중...', icon: Shield },
  ];

  useEffect(() => {
    const interval = setInterval(() => {
      setStep((prev) => (prev + 1) % steps.length);
    }, 500);
    return () => clearInterval(interval);
  }, []);

  const CurrentIcon = steps[step].icon;

  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="text-center">
        <div className="w-16 h-16 mx-auto mb-4 bg-blue-100 rounded-full flex items-center justify-center animate-pulse">
          <CurrentIcon size={32} className="text-blue-600 animate-bounce" />
        </div>
        <h2 className="text-lg font-bold text-gray-700 mb-2">AI 가치주 분석</h2>
        <p className="text-gray-500 text-sm">{steps[step].text}</p>
        <div className="flex justify-center gap-1 mt-4">
          {steps.map((_, idx) => (
            <div
              key={idx}
              className={`w-2 h-2 rounded-full transition-all ${
                idx === step ? 'bg-blue-600 w-4' : 'bg-gray-300'
              }`}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function ValueStocks() {
  const navigate = useNavigate();
  const [showAnalyzing, setShowAnalyzing] = useState(true);
  const [realtimePrices, setRealtimePrices] = useState({});

  const { data, isLoading } = useQuery({
    queryKey: ['valueStocks'],
    queryFn: () => valueStocksAPI.list(30).then((res) => res.data),
    staleTime: 1000 * 60 * 30, // 30분 캐시
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

  // 초기 로딩 시 2초간 분석 애니메이션
  useEffect(() => {
    const timer = setTimeout(() => setShowAnalyzing(false), 2000);
    return () => clearTimeout(timer);
  }, []);

  // 실시간 시세 조회
  useEffect(() => {
    if (data?.items && !showAnalyzing) {
      const codes = data.items.map((item) => item.code);
      realtimeAPI.prices(codes).then((res) => {
        if (res.data?.prices) {
          const priceMap = {};
          res.data.prices.forEach((p) => {
            priceMap[p.stock_code] = {
              current_price: p.current_price,
              change_rate: p.change_rate,
            };
          });
          setRealtimePrices(priceMap);
        }
      }).catch(console.error);
    }
  }, [data, showAnalyzing]);

  if (showAnalyzing || isLoading) {
    return <AnalyzingLoader />;
  }

  const items = data?.items || [];

  // 실시간 가격 병합
  const getStockData = (stock) => {
    const realtime = realtimePrices[stock.code];
    if (realtime) {
      return {
        ...stock,
        current_price: realtime.current_price,
        change_rate: realtime.change_rate,
      };
    }
    return stock;
  };

  return (
    <div className="max-w-md mx-auto">
      {/* 안내 문구 (강조) */}
      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-xl p-4 mb-4 text-white">
        <p className="font-bold text-base mb-1">저평가된 우량주를 AI가 선별했습니다</p>
        <p className="text-sm text-blue-100">단기 시세보다 기업 가치에 집중하는 중장기 투자자분들께 추천드립니다.</p>
      </div>

      {/* 선별 기준 */}
      <div className="bg-blue-50 rounded-xl p-4 mb-4">
        <p className="text-sm text-blue-700 font-medium mb-2">가치주 선별 기준</p>
        <div className="grid grid-cols-2 gap-2 text-xs text-blue-600">
          <div className="flex items-center gap-1">
            <Building2 size={12} /> PER 15 이하
          </div>
          <div className="flex items-center gap-1">
            <Shield size={12} /> PBR 2 이하
          </div>
          <div className="flex items-center gap-1">
            <Percent size={12} /> 배당률 우대
          </div>
          <div className="flex items-center gap-1">
            <Sparkles size={12} /> 대형우량주 포함
          </div>
        </div>
      </div>

      {/* 종목 리스트 */}
      <div className="space-y-3">
        {items.map((stock) => {
          const stockData = getStockData(stock);
          const changeRate = stockData.change_rate || 0;

          return (
            <div
              key={stock.code}
              className="bg-white rounded-xl p-4 shadow-sm active:bg-gray-50 cursor-pointer"
              onClick={() => navigate(`/stock/${stock.code}`, {
                state: {
                  preloadedData: {
                    code: stock.code,
                    name: stock.name,
                    current_price: stockData.current_price,
                    change_rate: stockData.change_rate,
                    score: stock.score,
                  },
                },
              })}
            >
              <div className="flex justify-between items-start mb-2">
                <div>
                  <h3 className="font-semibold text-gray-800">{stock.name}</h3>
                  <div className="flex items-center gap-1.5">
                    <p className="text-sm text-gray-500">{stock.code}</p>
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
                  <p className={`text-sm flex items-center justify-end gap-1 ${
                    changeRate >= 0 ? 'text-red-500' : 'text-blue-500'
                  }`}>
                    {changeRate >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                    {changeRate >= 0 ? '+' : ''}{changeRate.toFixed(2)}%
                  </p>
                </div>
              </div>

              {/* 가치 지표 */}
              <div className="grid grid-cols-4 gap-2 mt-3">
                <div className="bg-gray-50 rounded-lg p-2 text-center">
                  <p className="text-xs text-gray-500">PER</p>
                  <p className={`font-semibold text-sm ${
                    stock.per && stock.per <= 10 ? 'text-green-600' : 'text-gray-700'
                  }`}>
                    {stock.per?.toFixed(1) || '-'}
                  </p>
                </div>
                <div className="bg-gray-50 rounded-lg p-2 text-center">
                  <p className="text-xs text-gray-500">PBR</p>
                  <p className={`font-semibold text-sm ${
                    stock.pbr && stock.pbr <= 1 ? 'text-green-600' : 'text-gray-700'
                  }`}>
                    {stock.pbr?.toFixed(2) || '-'}
                  </p>
                </div>
                <div className="bg-gray-50 rounded-lg p-2 text-center">
                  <p className="text-xs text-gray-500">배당률</p>
                  <p className={`font-semibold text-sm ${
                    stock.dividend_yield && stock.dividend_yield >= 2 ? 'text-green-600' : 'text-gray-700'
                  }`}>
                    {stock.dividend_yield ? `${stock.dividend_yield.toFixed(1)}%` : '-'}
                  </p>
                </div>
                <div className="bg-gray-50 rounded-lg p-2 text-center">
                  <p className="text-xs text-gray-500">점수</p>
                  <p className="font-semibold text-sm text-blue-600">
                    {stock.score}
                  </p>
                </div>
              </div>

              {/* 태그 */}
              {stock.tags && stock.tags.length > 0 && (
                <div className="mt-3 flex gap-2 flex-wrap">
                  {stock.tags.map((tag) => (
                    <span
                      key={tag}
                      className={`px-2 py-0.5 rounded text-xs ${
                        tag.includes('대형') ? 'bg-purple-100 text-purple-600' :
                        tag.includes('PER') ? 'bg-green-100 text-green-600' :
                        tag.includes('PBR') ? 'bg-blue-100 text-blue-600' :
                        tag.includes('배당') ? 'bg-yellow-100 text-yellow-600' :
                        'bg-gray-100 text-gray-600'
                      }`}
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {items.length === 0 && (
        <div className="text-center py-10 text-gray-500">
          가치주 데이터가 없습니다
        </div>
      )}
    </div>
  );
}
