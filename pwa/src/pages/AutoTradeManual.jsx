import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { autoTradeAPI, stockAPI, realtimeAPI, top100API } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import Loading from '../components/Loading';
import {
  Search,
  ShoppingCart,
  Banknote,
  AlertCircle,
  X,
  TrendingUp,
  TrendingDown,
  Zap,
  Star,
  RefreshCw,
} from 'lucide-react';

// 호가단위 계산 함수
const getPriceUnit = (price) => {
  if (price < 2000) return 1;
  if (price < 5000) return 5;
  if (price < 20000) return 10;
  if (price < 50000) return 50;
  if (price < 200000) return 100;
  if (price < 500000) return 500;
  return 1000;
};

// 호가단위에 맞게 가격 조정 (내림)
const adjustToValidPrice = (price, isBuy = true) => {
  if (!price || price <= 0) return price;
  const unit = getPriceUnit(price);
  // 매수는 내림, 매도는 올림
  if (isBuy) {
    return Math.floor(price / unit) * unit;
  } else {
    return Math.ceil(price / unit) * unit;
  }
};

export default function AutoTradeManual() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState('buy');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedStock, setSelectedStock] = useState(null);
  const [stockPrice, setStockPrice] = useState(null);
  const [priceLoading, setPriceLoading] = useState(false);
  const [orderData, setOrderData] = useState({
    quantity: '',
    price: '',
    order_type: 'limit',
  });

  // URL 파라미터로 전달된 종목 자동 선택
  useEffect(() => {
    const code = searchParams.get('code');
    const name = searchParams.get('name');
    if (code && name) {
      setSelectedStock({ stock_code: code, stock_name: name });
      // URL 파라미터 제거 (히스토리 정리)
      setSearchParams({}, { replace: true });
    }
  }, []);

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

  // 계좌 정보 조회
  const { data: accountData } = useQuery({
    queryKey: ['autoTradeAccount'],
    queryFn: () => autoTradeAPI.getAccount().then((res) => res.data),
    staleTime: 1000 * 30,
  });

  // TOP100 종목 조회 (빠른 매수용)
  const { data: top100Data } = useQuery({
    queryKey: ['top100'],
    queryFn: () => top100API.list().then((res) => res.data),
    staleTime: 1000 * 60 * 5,
    enabled: activeTab === 'buy',
  });

  // 미체결 주문 조회 (매도 주문 중복 방지용)
  const { data: pendingOrdersData } = useQuery({
    queryKey: ['autoTradePendingOrders'],
    queryFn: () => autoTradeAPI.getPendingOrders().then((res) => res.data),
    staleTime: 1000 * 10,
    enabled: activeTab === 'sell',
  });

  // 미체결 매도 주문이 있는 종목 코드 Set
  const pendingSellCodes = new Set(
    (pendingOrdersData?.orders || [])
      .filter(o => o.side === 'sell')
      .map(o => o.stock_code)
  );

  // 종목 검색
  const { data: searchResults, isLoading: searchLoading } = useQuery({
    queryKey: ['stockSearch', searchQuery],
    queryFn: () => stockAPI.search(searchQuery).then((res) => res.data),
    enabled: searchQuery.length >= 2 && activeTab === 'buy',
    staleTime: 1000 * 60,
  });

  // 실시간 시세 조회
  const fetchStockPrice = async (code, isBuy = true) => {
    setPriceLoading(true);
    try {
      const response = await realtimeAPI.prices([code]);
      if (response.data?.prices?.[0]) {
        const price = response.data.prices[0];
        setStockPrice(price);
        // 호가단위에 맞게 가격 조정
        const validPrice = adjustToValidPrice(price.current_price, isBuy);
        setOrderData((prev) => ({
          ...prev,
          price: validPrice?.toString() || '',
        }));
      }
    } catch (error) {
      console.error('시세 조회 실패:', error);
    } finally {
      setPriceLoading(false);
    }
  };

  // 종목 선택 시 시세 조회
  useEffect(() => {
    if (selectedStock) {
      const code = selectedStock.stock_code || selectedStock.code;
      fetchStockPrice(code, activeTab === 'buy');
    } else {
      setStockPrice(null);
    }
  }, [selectedStock, activeTab]);

  // 주문 실행
  const orderMutation = useMutation({
    mutationFn: (data) => autoTradeAPI.placeOrder(data),
    onSuccess: (res) => {
      alert(res.data.message || '주문이 접수되었습니다.');
      setSelectedStock(null);
      setStockPrice(null);
      setOrderData({ quantity: '', price: '', order_type: 'limit' });
      queryClient.invalidateQueries(['autoTradeAccount']);
      queryClient.invalidateQueries(['autoTradePendingOrders']);
    },
    onError: (error) => {
      alert(error.response?.data?.detail || '주문 실행에 실패했습니다.');
    },
  });

  const handleSelectStock = (stock, fromSearch = false) => {
    const stockData = fromSearch
      ? { stock_code: stock.code, stock_name: stock.name }
      : stock;
    setSelectedStock(stockData);
    setSearchQuery('');
    setOrderData({ quantity: '', price: '', order_type: 'limit' });
  };

  const handleOrder = () => {
    if (!selectedStock) {
      alert('종목을 선택해주세요.');
      return;
    }
    if (!orderData.quantity || parseInt(orderData.quantity) <= 0) {
      alert('수량을 입력해주세요.');
      return;
    }
    if (orderData.order_type === 'limit' && (!orderData.price || parseInt(orderData.price) <= 0)) {
      alert('가격을 입력해주세요.');
      return;
    }

    const stockName = selectedStock.stock_name || selectedStock.name;
    const priceText = orderData.order_type === 'market' ? '시장가' : `${parseInt(orderData.price).toLocaleString()}원`;
    const confirmMsg = activeTab === 'buy'
      ? `${stockName} ${orderData.quantity}주를 ${priceText}에 매수하시겠습니까?`
      : `${stockName} ${orderData.quantity}주를 ${priceText}에 매도하시겠습니까?`;

    if (confirm(confirmMsg)) {
      orderMutation.mutate({
        stock_code: selectedStock.stock_code || selectedStock.code,
        side: activeTab,
        quantity: parseInt(orderData.quantity),
        price: orderData.order_type === 'market' ? 0 : parseInt(orderData.price),
        order_type: orderData.order_type,
      });
    }
  };

  // 가격 조절 함수 (호가단위 자동 적용)
  const adjustPrice = (percent) => {
    const currentPrice = stockPrice?.current_price || parseInt(orderData.price);
    if (currentPrice) {
      const rawPrice = Math.round(currentPrice * (1 + percent / 100));
      const validPrice = adjustToValidPrice(rawPrice, activeTab === 'buy');
      setOrderData({ ...orderData, price: validPrice.toString() });
    }
  };

  // 금액 기준 수량 추가 (누적)
  const addQuantityByAmount = (amount) => {
    const price = parseInt(orderData.price) || stockPrice?.current_price;
    if (price && price > 0) {
      const currentQty = parseInt(orderData.quantity) || 0;
      const addQty = Math.floor(amount / price);
      if (addQty > 0) {
        setOrderData({ ...orderData, quantity: (currentQty + addQty).toString() });
      }
    }
  };

  // 최대 수량 설정
  const setMaxQuantity = () => {
    const price = parseInt(orderData.price) || stockPrice?.current_price;
    if (price && price > 0 && cashBalance > 0) {
      const maxQty = Math.floor(cashBalance / price);
      if (maxQty > 0) {
        setOrderData({ ...orderData, quantity: maxQty.toString() });
      }
    }
  };

  // 호가 단위로 가격 조정
  const adjustPriceByTick = (ticks) => {
    const currentPrice = parseInt(orderData.price) || stockPrice?.current_price;
    if (currentPrice && currentPrice > 0) {
      const unit = getPriceUnit(currentPrice);
      const newPrice = currentPrice + (unit * ticks);
      if (newPrice > 0) {
        setOrderData({ ...orderData, price: newPrice.toString() });
      }
    }
  };

  const totalAmount = (parseInt(orderData.quantity) || 0) * (parseInt(orderData.price) || 0);
  const holdings = accountData?.holdings || [];
  const cashBalance = accountData?.cash_balance || 0;

  return (
    <div className="max-w-md mx-auto space-y-3">
      {/* 매수/매도 탭 */}
      <div className="flex gap-2 bg-white rounded-xl p-1.5 shadow-sm">
        <button
          onClick={() => {
            setActiveTab('buy');
            setSelectedStock(null);
            setStockPrice(null);
            setOrderData({ quantity: '', price: '', order_type: 'limit' });
          }}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg font-bold transition-colors ${
            activeTab === 'buy'
              ? 'bg-red-500 text-white'
              : 'bg-gray-100 text-gray-600'
          }`}
        >
          <ShoppingCart size={18} />
          매수
        </button>
        <button
          onClick={() => {
            setActiveTab('sell');
            setSelectedStock(null);
            setStockPrice(null);
            setOrderData({ quantity: '', price: '', order_type: 'limit' });
          }}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg font-bold transition-colors ${
            activeTab === 'sell'
              ? 'bg-blue-500 text-white'
              : 'bg-gray-100 text-gray-600'
          }`}
        >
          <Banknote size={18} />
          매도
        </button>
      </div>

      {/* 예수금 표시 */}
      {activeTab === 'buy' && cashBalance > 0 && (
        <div className="bg-green-50 rounded-lg px-3 py-2 flex justify-between items-center">
          <span className="text-sm text-green-700">주문가능금액</span>
          <span className="font-bold text-green-700">{cashBalance.toLocaleString()}원</span>
        </div>
      )}

      {/* 종목 선택 영역 */}
      {!selectedStock ? (
        <div className="bg-white rounded-xl p-4 shadow-sm">
          {activeTab === 'buy' ? (
            <>
              {/* 검색 */}
              <div className="relative mb-3">
                <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="종목명 또는 코드 검색"
                  className="w-full pl-10 pr-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 focus:border-transparent"
                />
                {/* 검색 결과 */}
                {searchQuery.length >= 2 && (
                  <div className="absolute z-20 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                    {searchLoading ? (
                      <div className="p-3 text-center text-gray-500 text-sm">검색 중...</div>
                    ) : searchResults?.length > 0 ? (
                      searchResults.slice(0, 8).map((stock) => (
                        <button
                          key={stock.code}
                          onClick={() => handleSelectStock(stock, true)}
                          className="w-full px-3 py-2 text-left hover:bg-red-50 border-b border-gray-100 last:border-0"
                        >
                          <span className="font-medium">{stock.name}</span>
                          <span className="text-xs text-gray-500 ml-2">{stock.code}</span>
                        </button>
                      ))
                    ) : (
                      <div className="p-3 text-center text-gray-500 text-sm">검색 결과 없음</div>
                    )}
                  </div>
                )}
              </div>

              {/* TOP100 빠른 선택 */}
              <div>
                <p className="text-xs text-gray-500 mb-2 flex items-center gap-1">
                  <Star size={12} />
                  TOP100 추천종목
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {top100Data?.items?.slice(0, 10).map((stock) => (
                    <button
                      key={stock.code}
                      onClick={() => handleSelectStock({ stock_code: stock.code, stock_name: stock.name })}
                      className="px-2.5 py-1.5 bg-gray-100 hover:bg-red-100 text-gray-700 hover:text-red-700 rounded-lg text-xs font-medium transition-colors"
                    >
                      {stock.name}
                    </button>
                  ))}
                </div>
              </div>
            </>
          ) : (
            /* 매도: 보유 종목 */
            <div>
              <p className="text-sm font-medium text-gray-700 mb-2">보유 종목 선택</p>
              {holdings.length > 0 ? (
                <div className="space-y-2">
                  {holdings.map((h) => {
                    const hasPendingSell = pendingSellCodes.has(h.stock_code);
                    return (
                      <button
                        key={h.stock_code}
                        onClick={() => !hasPendingSell && handleSelectStock(h)}
                        disabled={hasPendingSell}
                        className={`w-full p-3 text-left rounded-lg border transition-colors ${
                          hasPendingSell
                            ? 'border-gray-200 bg-gray-100 opacity-60 cursor-not-allowed'
                            : 'border-gray-200 hover:border-blue-400 hover:bg-blue-50'
                        }`}
                      >
                        <div className="flex justify-between">
                          <div>
                            <p className={`font-bold ${hasPendingSell ? 'text-gray-500' : 'text-gray-800'}`}>
                              {h.stock_name}
                              {hasPendingSell && <span className="ml-2 text-xs text-orange-500 font-normal">매도주문중</span>}
                            </p>
                            <p className="text-xs text-gray-500">
                              {h.quantity}주 보유
                              {h.score != null && (
                                <span className={`ml-2 font-medium ${
                                  h.score >= 80 ? 'text-red-500' :
                                  h.score >= 60 ? 'text-orange-500' :
                                  h.score >= 40 ? 'text-gray-600' : 'text-blue-500'
                                }`}>
                                  {h.score}점
                                </span>
                              )}
                            </p>
                          </div>
                          <div className="text-right">
                            <p className="font-medium">{h.current_price?.toLocaleString()}원</p>
                            <p className={`text-xs ${(h.profit_rate || 0) >= 0 ? 'text-red-500' : 'text-blue-500'}`}>
                              {(h.profit_rate || 0) >= 0 ? '+' : ''}{h.profit_rate?.toFixed(1)}%
                            </p>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <div className="text-center py-8 text-gray-400">보유 종목이 없습니다</div>
              )}
            </div>
          )}
        </div>
      ) : (
        /* 주문 입력 영역 */
        <div className="bg-white rounded-xl p-4 shadow-sm space-y-3">
          {/* 선택된 종목 */}
          <div className="flex justify-between items-center pb-3 border-b">
            <div>
              <p className="font-bold text-lg text-gray-800">
                {selectedStock.stock_name || selectedStock.name}
              </p>
              <div className="flex items-center gap-2 mt-1">
                {priceLoading ? (
                  <span className="text-sm text-gray-400">시세 조회 중...</span>
                ) : stockPrice ? (
                  <>
                    <span className="font-bold text-gray-800">
                      {stockPrice.current_price?.toLocaleString()}원
                    </span>
                    <span className={`text-sm ${stockPrice.change_rate >= 0 ? 'text-red-500' : 'text-blue-500'}`}>
                      {stockPrice.change_rate >= 0 ? '+' : ''}{stockPrice.change_rate?.toFixed(2)}%
                    </span>
                  </>
                ) : null}
              </div>
            </div>
            <button
              onClick={() => {
                setSelectedStock(null);
                setStockPrice(null);
              }}
              className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg"
            >
              <X size={20} />
            </button>
          </div>

          {/* 주문 유형 */}
          <div className="flex gap-2">
            <button
              onClick={() => setOrderData({ ...orderData, order_type: 'limit' })}
              className={`flex-1 py-2 rounded-lg font-medium text-sm transition-colors ${
                orderData.order_type === 'limit'
                  ? 'bg-purple-600 text-white'
                  : 'bg-gray-100 text-gray-600'
              }`}
            >
              지정가
            </button>
            <button
              onClick={() => setOrderData({ ...orderData, order_type: 'market' })}
              className={`flex-1 py-2 rounded-lg font-medium text-sm transition-colors flex items-center justify-center gap-1 ${
                orderData.order_type === 'market'
                  ? 'bg-yellow-500 text-white'
                  : 'bg-gray-100 text-gray-600'
              }`}
            >
              <Zap size={14} />
              시장가
            </button>
          </div>

          {/* 가격 입력 (지정가) */}
          {orderData.order_type === 'limit' && (
            <div>
              <div className="flex justify-between items-center mb-1">
                <label className="text-sm font-medium text-gray-700">가격</label>
                <button
                  onClick={() => fetchStockPrice(selectedStock.stock_code || selectedStock.code, activeTab === 'buy')}
                  className="text-xs text-purple-600 hover:underline flex items-center gap-1"
                >
                  <RefreshCw size={12} />
                  현재가
                </button>
              </div>
              <input
                type="number"
                value={orderData.price}
                onChange={(e) => setOrderData({ ...orderData, price: e.target.value })}
                onBlur={(e) => {
                  const price = parseInt(e.target.value);
                  if (price > 0) {
                    const validPrice = adjustToValidPrice(price, activeTab === 'buy');
                    setOrderData({ ...orderData, price: validPrice.toString() });
                  }
                }}
                className="w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 text-right font-bold text-lg"
                placeholder="0"
              />
              {/* 호가단위 안내 */}
              {orderData.price && parseInt(orderData.price) > 0 && (
                <p className="text-xs text-gray-500 mt-1 text-right">
                  호가단위: {getPriceUnit(parseInt(orderData.price)).toLocaleString()}원
                </p>
              )}
              {/* 가격 조절 버튼 (호가 단위) */}
              <div className="flex gap-1 mt-2">
                <button
                  onClick={() => adjustPriceByTick(-5)}
                  className="flex-1 py-1.5 text-xs bg-blue-50 text-blue-600 hover:bg-blue-100 rounded font-medium"
                >
                  -5호가
                </button>
                <button
                  onClick={() => adjustPriceByTick(-1)}
                  className="flex-1 py-1.5 text-xs bg-blue-50 text-blue-600 hover:bg-blue-100 rounded font-medium"
                >
                  -1호가
                </button>
                <button
                  onClick={() => {
                    if (stockPrice?.current_price) {
                      const validPrice = adjustToValidPrice(stockPrice.current_price, activeTab === 'buy');
                      setOrderData({ ...orderData, price: validPrice.toString() });
                    }
                  }}
                  className="flex-1 py-1.5 text-xs bg-purple-100 text-purple-700 hover:bg-purple-200 rounded font-medium"
                >
                  현재가
                </button>
                <button
                  onClick={() => adjustPriceByTick(1)}
                  className="flex-1 py-1.5 text-xs bg-red-50 text-red-600 hover:bg-red-100 rounded font-medium"
                >
                  +1호가
                </button>
                <button
                  onClick={() => adjustPriceByTick(5)}
                  className="flex-1 py-1.5 text-xs bg-red-50 text-red-600 hover:bg-red-100 rounded font-medium"
                >
                  +5호가
                </button>
              </div>
            </div>
          )}

          {/* 수량 입력 */}
          <div>
            <label className="text-sm font-medium text-gray-700 mb-1 block">수량</label>
            <input
              type="number"
              value={orderData.quantity}
              onChange={(e) => setOrderData({ ...orderData, quantity: e.target.value })}
              className="w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 text-right font-bold text-lg"
              placeholder="0"
            />
            {/* 수량 버튼 */}
            <div className="flex gap-1 mt-2">
              {activeTab === 'sell' && selectedStock?.quantity ? (
                /* 매도: 비율 버튼 */
                <>
                  {[
                    { label: '25%', value: 0.25 },
                    { label: '50%', value: 0.5 },
                    { label: '75%', value: 0.75 },
                    { label: '전량', value: 1 },
                  ].map((btn) => (
                    <button
                      key={btn.label}
                      onClick={() => {
                        const qty = Math.floor(selectedStock.quantity * btn.value);
                        if (qty > 0) setOrderData({ ...orderData, quantity: qty.toString() });
                      }}
                      className="flex-1 py-1.5 text-xs bg-blue-50 text-blue-600 hover:bg-blue-100 rounded font-medium"
                    >
                      {btn.label}
                    </button>
                  ))}
                </>
              ) : (
                /* 매수: 금액 버튼 (누적 추가) */
                <>
                  <button
                    onClick={() => setOrderData({ ...orderData, quantity: '' })}
                    className="py-1.5 px-2 text-xs bg-gray-100 text-gray-600 hover:bg-gray-200 rounded font-medium"
                  >
                    초기화
                  </button>
                  <button
                    onClick={() => addQuantityByAmount(10000)}
                    className="flex-1 py-1.5 text-xs bg-red-50 text-red-600 hover:bg-red-100 rounded font-medium"
                  >
                    +1만
                  </button>
                  <button
                    onClick={() => addQuantityByAmount(100000)}
                    className="flex-1 py-1.5 text-xs bg-red-50 text-red-600 hover:bg-red-100 rounded font-medium"
                  >
                    +10만
                  </button>
                  <button
                    onClick={() => addQuantityByAmount(500000)}
                    className="flex-1 py-1.5 text-xs bg-red-50 text-red-600 hover:bg-red-100 rounded font-medium"
                  >
                    +50만
                  </button>
                  <button
                    onClick={setMaxQuantity}
                    className="flex-1 py-1.5 text-xs bg-red-100 text-red-700 hover:bg-red-200 rounded font-bold"
                  >
                    최대
                  </button>
                </>
              )}
            </div>
          </div>

          {/* 총 금액 */}
          <div className="bg-gray-50 rounded-lg p-3">
            <div className="flex justify-between items-center">
              <span className="text-gray-600">주문금액</span>
              <span className="text-xl font-bold">
                {orderData.order_type === 'market'
                  ? '시장가'
                  : totalAmount > 0
                  ? `${totalAmount.toLocaleString()}원`
                  : '-'}
              </span>
            </div>
          </div>

          {/* 주문 버튼 */}
          <button
            onClick={handleOrder}
            disabled={orderMutation.isPending}
            className={`w-full py-3.5 rounded-xl font-bold text-white text-lg transition-colors disabled:opacity-50 ${
              activeTab === 'buy'
                ? 'bg-red-500 hover:bg-red-600 active:bg-red-700'
                : 'bg-blue-500 hover:bg-blue-600 active:bg-blue-700'
            }`}
          >
            {orderMutation.isPending
              ? '주문 처리 중...'
              : activeTab === 'buy'
              ? '매수'
              : '매도'}
          </button>
        </div>
      )}

      {/* 시장가 안내 */}
      {orderData.order_type === 'market' && selectedStock && (
        <div className="bg-yellow-50 rounded-lg p-3 border border-yellow-200">
          <p className="text-xs text-yellow-700">
            <Zap size={12} className="inline mr-1" />
            시장가 주문은 현재 호가에 즉시 체결됩니다. 체결가가 예상과 다를 수 있습니다.
          </p>
        </div>
      )}
    </div>
  );
}
