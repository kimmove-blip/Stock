import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { autoTradeAPI, stockAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import Loading from '../components/Loading';
import {
  HandCoins,
  Search,
  ShoppingCart,
  Banknote,
  AlertCircle,
  CheckCircle,
  X,
  TrendingUp,
  TrendingDown,
} from 'lucide-react';

export default function AutoTradeManual() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState('buy');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedStock, setSelectedStock] = useState(null);
  const [orderData, setOrderData] = useState({
    quantity: '',
    price: '',
    order_type: 'limit', // limit: 지정가, market: 시장가
  });

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

  // 보유 종목 조회 (매도용)
  const { data: holdings } = useQuery({
    queryKey: ['autoTradeAccount'],
    queryFn: () => autoTradeAPI.getAccount().then((res) => res.data),
    staleTime: 1000 * 30,
    enabled: activeTab === 'sell',
  });

  // 종목 검색
  const { data: searchResults, isLoading: searchLoading } = useQuery({
    queryKey: ['stockSearch', searchQuery],
    queryFn: () => stockAPI.search(searchQuery).then((res) => res.data),
    enabled: searchQuery.length >= 2 && activeTab === 'buy',
    staleTime: 1000 * 60,
  });

  // 주문 실행
  const orderMutation = useMutation({
    mutationFn: (data) => autoTradeAPI.placeOrder(data),
    onSuccess: (res) => {
      alert(res.data.message || '주문이 접수되었습니다.');
      setSelectedStock(null);
      setOrderData({ quantity: '', price: '', order_type: 'limit' });
      queryClient.invalidateQueries(['autoTradeAccount']);
      queryClient.invalidateQueries(['autoTradePendingOrders']);
    },
    onError: (error) => {
      alert(error.response?.data?.detail || '주문 실행에 실패했습니다.');
    },
  });

  const handleSelectStock = (stock) => {
    setSelectedStock(stock);
    setOrderData({
      ...orderData,
      price: stock.current_price || stock.price || '',
    });
    setSearchQuery('');
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

    const confirmMsg = activeTab === 'buy'
      ? `${selectedStock.stock_name || selectedStock.name} ${orderData.quantity}주를 ${orderData.order_type === 'market' ? '시장가' : orderData.price + '원'}에 매수하시겠습니까?`
      : `${selectedStock.stock_name || selectedStock.name} ${orderData.quantity}주를 ${orderData.order_type === 'market' ? '시장가' : orderData.price + '원'}에 매도하시겠습니까?`;

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

  const totalAmount = (parseInt(orderData.quantity) || 0) * (parseInt(orderData.price) || 0);

  return (
    <div className="max-w-md mx-auto space-y-4">
      {/* 매수/매도 탭 */}
      <div className="flex gap-2 bg-white rounded-xl p-2 shadow-sm">
        <button
          onClick={() => {
            setActiveTab('buy');
            setSelectedStock(null);
            setOrderData({ quantity: '', price: '', order_type: 'limit' });
          }}
          className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-lg font-medium transition-colors ${
            activeTab === 'buy'
              ? 'bg-red-500 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          <ShoppingCart size={18} />
          매수
        </button>
        <button
          onClick={() => {
            setActiveTab('sell');
            setSelectedStock(null);
            setOrderData({ quantity: '', price: '', order_type: 'limit' });
          }}
          className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-lg font-medium transition-colors ${
            activeTab === 'sell'
              ? 'bg-blue-500 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          <Banknote size={18} />
          매도
        </button>
      </div>

      {/* 종목 선택 */}
      <div className="bg-white rounded-xl p-4 shadow-sm">
        <h3 className="font-bold text-gray-800 mb-3">
          {activeTab === 'buy' ? '매수할 종목 검색' : '매도할 종목 선택'}
        </h3>

        {activeTab === 'buy' ? (
          // 매수: 종목 검색
          <div className="relative">
            <div className="relative">
              <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="종목명 또는 종목코드 검색"
                className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
              />
            </div>
            {/* 검색 결과 */}
            {searchQuery.length >= 2 && (
              <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                {searchLoading ? (
                  <div className="p-4 text-center text-gray-500">검색 중...</div>
                ) : searchResults?.length > 0 ? (
                  searchResults.slice(0, 10).map((stock) => (
                    <button
                      key={stock.code}
                      onClick={() => handleSelectStock({ ...stock, stock_code: stock.code, stock_name: stock.name })}
                      className="w-full px-4 py-2 text-left hover:bg-gray-50 border-b border-gray-100 last:border-0"
                    >
                      <p className="font-medium">{stock.name}</p>
                      <p className="text-xs text-gray-500">{stock.code}</p>
                    </button>
                  ))
                ) : (
                  <div className="p-4 text-center text-gray-500">검색 결과가 없습니다</div>
                )}
              </div>
            )}
          </div>
        ) : (
          // 매도: 보유 종목 목록
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {holdings?.holdings?.length > 0 ? (
              holdings.holdings.map((holding) => (
                <button
                  key={holding.stock_code}
                  onClick={() => handleSelectStock(holding)}
                  className={`w-full p-3 text-left rounded-lg border-2 transition-colors ${
                    selectedStock?.stock_code === holding.stock_code
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="flex justify-between items-center">
                    <div>
                      <p className="font-medium">{holding.stock_name}</p>
                      <p className="text-xs text-gray-500">
                        {holding.quantity}주 보유 | 평단가 {holding.avg_price?.toLocaleString()}원
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-medium">{holding.current_price?.toLocaleString()}원</p>
                      <p className={`text-xs ${(holding.profit_rate || 0) >= 0 ? 'text-red-600' : 'text-blue-600'}`}>
                        {(holding.profit_rate || 0) >= 0 ? '+' : ''}{holding.profit_rate?.toFixed(2)}%
                      </p>
                    </div>
                  </div>
                </button>
              ))
            ) : (
              <div className="text-center py-8 text-gray-400">
                보유 종목이 없습니다
              </div>
            )}
          </div>
        )}

        {/* 선택된 종목 */}
        {selectedStock && (
          <div className="mt-3 p-3 bg-gray-50 rounded-lg">
            <div className="flex justify-between items-center">
              <div>
                <p className="font-bold text-gray-800">{selectedStock.stock_name || selectedStock.name}</p>
                <p className="text-xs text-gray-500">{selectedStock.stock_code || selectedStock.code}</p>
              </div>
              <button
                onClick={() => setSelectedStock(null)}
                className="p-1 text-gray-400 hover:text-gray-600"
              >
                <X size={18} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 주문 입력 */}
      {selectedStock && (
        <div className="bg-white rounded-xl p-4 shadow-sm space-y-4">
          <h3 className="font-bold text-gray-800">주문 정보</h3>

          {/* 주문 유형 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">주문 유형</label>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => setOrderData({ ...orderData, order_type: 'limit' })}
                className={`py-2 rounded-lg font-medium transition-colors ${
                  orderData.order_type === 'limit'
                    ? 'bg-purple-600 text-white'
                    : 'bg-gray-100 text-gray-600'
                }`}
              >
                지정가
              </button>
              <button
                onClick={() => setOrderData({ ...orderData, order_type: 'market' })}
                className={`py-2 rounded-lg font-medium transition-colors ${
                  orderData.order_type === 'market'
                    ? 'bg-purple-600 text-white'
                    : 'bg-gray-100 text-gray-600'
                }`}
              >
                시장가
              </button>
            </div>
          </div>

          {/* 수량 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">수량</label>
            <div className="relative">
              <input
                type="number"
                value={orderData.quantity}
                onChange={(e) => setOrderData({ ...orderData, quantity: e.target.value })}
                placeholder="주문 수량"
                className="w-full px-3 py-2 pr-10 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500">주</span>
            </div>
            {activeTab === 'sell' && selectedStock.quantity && (
              <p className="text-xs text-gray-500 mt-1">
                보유 수량: {selectedStock.quantity}주
                <button
                  onClick={() => setOrderData({ ...orderData, quantity: selectedStock.quantity.toString() })}
                  className="ml-2 text-purple-600 hover:underline"
                >
                  전량
                </button>
              </p>
            )}
          </div>

          {/* 가격 (지정가일 때만) */}
          {orderData.order_type === 'limit' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">가격</label>
              <div className="relative">
                <input
                  type="number"
                  value={orderData.price}
                  onChange={(e) => setOrderData({ ...orderData, price: e.target.value })}
                  placeholder="주문 가격"
                  className="w-full px-3 py-2 pr-10 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500">원</span>
              </div>
            </div>
          )}

          {/* 총 금액 */}
          <div className="p-3 bg-gray-50 rounded-lg">
            <div className="flex justify-between items-center">
              <span className="text-gray-600">예상 {activeTab === 'buy' ? '매수' : '매도'} 금액</span>
              <span className="text-xl font-bold text-gray-800">
                {orderData.order_type === 'market' ? '시장가' : totalAmount.toLocaleString() + '원'}
              </span>
            </div>
          </div>

          {/* 주문 버튼 */}
          <button
            onClick={handleOrder}
            disabled={orderMutation.isLoading}
            className={`w-full py-3 rounded-xl font-bold text-white transition-colors disabled:opacity-50 ${
              activeTab === 'buy'
                ? 'bg-red-500 hover:bg-red-600'
                : 'bg-blue-500 hover:bg-blue-600'
            }`}
          >
            {orderMutation.isLoading
              ? '주문 중...'
              : activeTab === 'buy'
              ? '매수 주문'
              : '매도 주문'}
          </button>
        </div>
      )}

      {/* 주의사항 */}
      <div className="bg-yellow-50 rounded-xl p-4 border border-yellow-200">
        <div className="flex items-start gap-2">
          <AlertCircle size={18} className="text-yellow-600 mt-0.5" />
          <div className="text-sm text-yellow-700">
            <p className="font-medium mb-1">주문 시 주의사항</p>
            <ul className="space-y-1 text-yellow-600">
              <li>• 주문 후 취소는 미체결 내역에서 가능합니다</li>
              <li>• 시장가 주문은 즉시 체결되어 취소가 어렵습니다</li>
              <li>• 장 운영 시간에만 주문이 가능합니다</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
