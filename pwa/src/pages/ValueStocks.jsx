import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { valueStocksAPI, realtimeAPI, portfolioAPI, watchlistAPI } from '../api/client';
import { TrendingUp, TrendingDown, Shield, Percent, Building2, RefreshCw, Sparkles, Star, Plus } from 'lucide-react';
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
  const queryClient = useQueryClient();
  const [showAnalyzing, setShowAnalyzing] = useState(true);
  const [realtimePrices, setRealtimePrices] = useState({});
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedStock, setSelectedStock] = useState(null);
  const [buyPrice, setBuyPrice] = useState('');
  const [quantity, setQuantity] = useState('1');

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['valueStocks'],
    queryFn: () => valueStocksAPI.list(30).then((res) => res.data),
    staleTime: 1000 * 60 * 30, // 30분 캐시
  });

  // 관심종목 추가
  const addToWatchlistMutation = useMutation({
    mutationFn: (stock) => watchlistAPI.add({
      stock_code: stock.code,
      stock_name: stock.name,
      category: '가치주',
    }),
    onSuccess: () => {
      queryClient.invalidateQueries(['watchlist']);
      alert('관심종목에 추가되었습니다');
    },
    onError: (error) => {
      alert(error.response?.data?.detail || '추가에 실패했습니다');
    },
  });

  // 보유종목 추가
  const addToPortfolioMutation = useMutation({
    mutationFn: (data) => portfolioAPI.add(data),
    onSuccess: () => {
      queryClient.invalidateQueries(['portfolio']);
      setShowAddModal(false);
      setSelectedStock(null);
      setBuyPrice('');
      setQuantity('1');
      alert('보유종목에 추가되었습니다');
    },
    onError: (error) => {
      alert(error.response?.data?.detail || '추가에 실패했습니다');
    },
  });

  const handleOpenAddModal = (stock, currentPrice) => {
    setSelectedStock(stock);
    setBuyPrice(currentPrice?.toString() || '');
    setQuantity('1');
    setShowAddModal(true);
  };

  const handleAddToPortfolio = () => {
    if (!selectedStock) return;
    addToPortfolioMutation.mutate({
      stock_code: selectedStock.code,
      stock_name: selectedStock.name,
      buy_price: parseInt(buyPrice) || 0,
      quantity: parseInt(quantity) || 1,
    });
  };

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
      {/* 상단 컨트롤 */}
      <div className="flex items-center justify-between mb-3">
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="btn btn-sm btn-ghost gap-2"
        >
          <RefreshCw size={16} className={isFetching ? 'animate-spin' : ''} />
          새로고침
        </button>
        <span className="text-xs text-gray-500">
          {data?.generated_at ? new Date(data.generated_at).toLocaleTimeString('ko-KR') : ''}
        </span>
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

      {/* 안내 문구 */}
      <p className="text-xs text-gray-500 mb-4 flex items-start gap-1">
        <span>💡</span>
        <span>저평가된 우량주를 AI가 선별했습니다. 단기 시세보다 기업 가치에 집중하는 중장기 투자자분들께 추천드립니다.</span>
      </p>

      {/* 종목 리스트 */}
      <div className="space-y-3">
        {items.map((stock) => {
          const stockData = getStockData(stock);
          const changeRate = stockData.change_rate || 0;

          return (
            <div
              key={stock.code}
              className="bg-white rounded-xl p-4 shadow-sm"
            >
              <div className="flex justify-between items-start mb-2">
                <div>
                  <h3 className="font-semibold text-gray-800">{stock.name}</h3>
                  <p className="text-sm text-gray-500">{stock.code}</p>
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

              {/* 액션 버튼 */}
              <div className="flex gap-2 mt-3 pt-3 border-t border-gray-100">
                <button
                  onClick={() => handleOpenAddModal(stock, stockData.current_price)}
                  className="btn btn-sm btn-primary flex-1"
                >
                  <Plus size={14} /> 보유종목
                </button>
                <button
                  onClick={() => addToWatchlistMutation.mutate(stock)}
                  disabled={addToWatchlistMutation.isPending}
                  className="btn btn-sm btn-outline flex-1"
                >
                  <Star size={14} /> 관심종목
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {items.length === 0 && (
        <div className="text-center py-10 text-gray-500">
          가치주 데이터가 없습니다
        </div>
      )}

      {/* 보유종목 추가 모달 */}
      {showAddModal && selectedStock && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">보유종목 추가</h3>

            <div className="mt-4 p-3 bg-base-200 rounded">
              <p className="font-bold">{selectedStock.name}</p>
              <p className="text-sm text-base-content/60">{selectedStock.code}</p>
            </div>

            <div className="form-control mt-4">
              <label className="label">
                <span className="label-text">매수가</span>
              </label>
              <input
                type="number"
                value={buyPrice}
                onChange={(e) => setBuyPrice(e.target.value)}
                className="input input-bordered"
                placeholder="매수가 입력"
              />
            </div>

            <div className="form-control mt-4">
              <label className="label">
                <span className="label-text">수량</span>
              </label>
              <input
                type="number"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                className="input input-bordered"
                min="1"
              />
            </div>

            <div className="modal-action">
              <button
                onClick={() => {
                  setShowAddModal(false);
                  setSelectedStock(null);
                }}
                className="btn btn-ghost"
              >
                취소
              </button>
              <button
                onClick={handleAddToPortfolio}
                className="btn btn-primary"
                disabled={addToPortfolioMutation.isPending}
              >
                {addToPortfolioMutation.isPending ? (
                  <span className="loading loading-spinner"></span>
                ) : (
                  '추가'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
