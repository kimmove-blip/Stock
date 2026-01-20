import { useState, useEffect, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { autoTradeAPI, realtimeAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import Loading from '../components/Loading';
import {
  Clock,
  X,
  AlertCircle,
  RefreshCw,
  ShoppingCart,
  Banknote,
  XCircle,
  Edit3,
  TrendingUp,
  TrendingDown,
  Star,
  Zap,
} from 'lucide-react';

export default function AutoTradePendingOrders() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [modifyModal, setModifyModal] = useState(null);
  const [modifyPrice, setModifyPrice] = useState('');
  const [modifyQuantity, setModifyQuantity] = useState('');
  const [isMarketOrder, setIsMarketOrder] = useState(false);
  const [realtimePrices, setRealtimePrices] = useState({});
  const [lastPriceUpdate, setLastPriceUpdate] = useState(null);
  const [autoRefreshPrice, setAutoRefreshPrice] = useState(true);

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

  // 미체결 내역 조회
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['autoTradePendingOrders'],
    queryFn: () => autoTradeAPI.getPendingOrders().then((res) => res.data),
    staleTime: 1000 * 10, // 10초 캐시
    refetchOnWindowFocus: true,
    refetchInterval: 1000 * 30, // 30초마다 자동 새로고침
  });

  // 실시간 시세 조회 함수
  const fetchRealtimePrices = useCallback(async (codes) => {
    if (!codes || codes.length === 0) return;
    try {
      const response = await realtimeAPI.prices(codes);
      if (response.data?.prices) {
        const priceMap = {};
        response.data.prices.forEach((p) => {
          priceMap[p.stock_code] = {
            current_price: p.current_price,
            change: p.change,
            change_rate: p.change_rate,
          };
        });
        setRealtimePrices(priceMap);
        setLastPriceUpdate(new Date());
      }
    } catch (error) {
      console.error('실시간 시세 조회 실패:', error);
    }
  }, []);

  // 미체결 주문이 있을 때 실시간 시세 조회
  useEffect(() => {
    const orders = data?.orders || [];
    if (orders.length > 0) {
      const codes = [...new Set(orders.map((o) => o.stock_code))];
      fetchRealtimePrices(codes);
    }
  }, [data?.orders, fetchRealtimePrices]);

  // 자동 갱신 (10초 간격)
  useEffect(() => {
    if (!autoRefreshPrice) return;
    const orders = data?.orders || [];
    if (orders.length === 0) return;

    const interval = setInterval(() => {
      const codes = [...new Set(orders.map((o) => o.stock_code))];
      fetchRealtimePrices(codes);
    }, 10000); // 10초

    return () => clearInterval(interval);
  }, [autoRefreshPrice, data?.orders, fetchRealtimePrices]);

  // 주문 취소
  const cancelMutation = useMutation({
    mutationFn: (orderId) => autoTradeAPI.cancelOrder(orderId),
    onSuccess: () => {
      queryClient.invalidateQueries(['autoTradePendingOrders']);
      queryClient.invalidateQueries(['autoTradeAccount']);
    },
    onError: (error) => {
      alert(error.response?.data?.detail || '주문 취소에 실패했습니다.');
    },
  });

  // 주문 정정
  const modifyMutation = useMutation({
    mutationFn: ({ orderId, data }) => autoTradeAPI.modifyOrder(orderId, data),
    onSuccess: () => {
      queryClient.invalidateQueries(['autoTradePendingOrders']);
      setModifyModal(null);
      setModifyPrice('');
      setModifyQuantity('');
    },
    onError: (error) => {
      alert(error.response?.data?.detail || '주문 정정에 실패했습니다.');
    },
  });

  const handleCancel = (order) => {
    const side = order.side === 'buy' ? '매수' : '매도';
    if (confirm(`${order.stock_name} ${side} 주문을 취소하시겠습니까?`)) {
      cancelMutation.mutate(order.order_id);
    }
  };

  const handleModifyOpen = (order) => {
    setModifyModal(order);
    setModifyPrice(order.price?.toString() || '');
    setModifyQuantity(order.remaining_quantity?.toString() || order.quantity?.toString() || '');
    setIsMarketOrder(false);
  };

  const handleModifySubmit = () => {
    if (!modifyModal) return;
    const quantity = parseInt(modifyQuantity);

    if (!quantity || quantity <= 0) {
      alert('정정 수량을 입력하세요.');
      return;
    }

    if (!isMarketOrder) {
      const price = parseInt(modifyPrice);
      if (!price || price <= 0) {
        alert('정정 가격을 입력하세요.');
        return;
      }
      modifyMutation.mutate({
        orderId: modifyModal.order_id,
        data: {
          order_id: modifyModal.order_id,
          stock_code: modifyModal.stock_code,
          quantity: quantity,
          price: price,
        }
      });
    } else {
      // 시장가 정정
      modifyMutation.mutate({
        orderId: modifyModal.order_id,
        data: {
          order_id: modifyModal.order_id,
          stock_code: modifyModal.stock_code,
          quantity: quantity,
          price: 0,
          order_type: 'market',
        }
      });
    }
  };

  if (isLoading) return <Loading text="미체결 내역 불러오는 중..." />;

  if (error) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="text-center">
          <AlertCircle size={48} className="mx-auto text-red-400 mb-4" />
          <h2 className="text-lg font-bold text-gray-700 mb-2">오류 발생</h2>
          <p className="text-gray-500 text-sm mb-4">
            {error.response?.data?.detail || '미체결 내역을 불러올 수 없습니다.'}
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

  const { orders = [], summary = {} } = data || {};

  // 실시간 시세를 병합한 주문 데이터
  const getOrderWithRealtime = (order) => {
    const realtime = realtimePrices[order.stock_code];
    if (realtime) {
      return {
        ...order,
        current_price: realtime.current_price || order.current_price,
        change_rate: realtime.change_rate ?? order.change_rate,
      };
    }
    return order;
  };

  return (
    <div className="max-w-md mx-auto space-y-4">
      {/* 새로고침 */}
      <div className="flex justify-between items-center">
        <div>
          <p className="text-sm text-gray-500">
            {orders.length}건의 미체결 주문
          </p>
          {lastPriceUpdate && (
            <p className="text-xs text-gray-400">
              시세: {lastPriceUpdate.toLocaleTimeString('ko-KR')}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setAutoRefreshPrice(!autoRefreshPrice)}
            className={`px-2 py-1 rounded-full text-xs font-medium transition-colors ${
              autoRefreshPrice
                ? 'bg-green-100 text-green-600'
                : 'bg-gray-100 text-gray-500'
            }`}
          >
            {autoRefreshPrice ? '실시간 ON' : '실시간 OFF'}
          </button>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-1 text-sm text-gray-600 hover:text-purple-600 transition-colors"
          >
            <RefreshCw size={16} className={isFetching ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* 요약 */}
      {orders.length > 0 && (
        <div className="bg-white rounded-xl p-4 shadow-sm">
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-red-50 rounded-lg p-3 text-center">
              <p className="text-xs text-red-600">매수 대기</p>
              <p className="text-lg font-bold text-red-700">
                {summary.buy_count || 0}건
              </p>
              <p className="text-xs text-red-500">
                {summary.buy_amount?.toLocaleString() || 0}원
              </p>
            </div>
            <div className="bg-blue-50 rounded-lg p-3 text-center">
              <p className="text-xs text-blue-600">매도 대기</p>
              <p className="text-lg font-bold text-blue-700">
                {summary.sell_count || 0}건
              </p>
              <p className="text-xs text-blue-500">
                {summary.sell_amount?.toLocaleString() || 0}원
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 미체결 주문 목록 */}
      {orders.length > 0 ? (
        <div className="space-y-2">
          {orders.map((rawOrder) => {
            const order = getOrderWithRealtime(rawOrder);
            return (
            <div
              key={order.order_id}
              className="bg-white rounded-xl p-3 shadow-sm"
            >
              {/* 헤더: 종목명 + 매수/매도 + 버튼 */}
              <div className="flex items-center justify-between mb-2">
                <div
                  className="flex items-center gap-2 flex-1 cursor-pointer"
                  onClick={() => navigate(`/stock/${order.stock_code}`)}
                >
                  <span
                    className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                      order.side === 'buy'
                        ? 'bg-red-100 text-red-600'
                        : 'bg-blue-100 text-blue-600'
                    }`}
                  >
                    {order.side === 'buy' ? '매수' : '매도'}
                  </span>
                  <span className="font-bold text-gray-800">{order.stock_name}</span>
                  {order.score !== null && order.score !== undefined && (
                    <span className={`text-sm font-medium ${
                      order.score >= 80 ? 'text-green-600' : order.score >= 60 ? 'text-yellow-600' : 'text-gray-500'
                    }`}>
                      {order.score}점
                    </span>
                  )}
                </div>
                <div className="flex gap-0.5">
                  {order.order_type !== 'market' && (
                    <button
                      onClick={() => handleModifyOpen(order)}
                      disabled={modifyMutation.isPending}
                      className="p-1.5 text-gray-400 hover:text-blue-500 hover:bg-blue-50 rounded-lg transition-colors disabled:opacity-50"
                      title="정정"
                    >
                      <Edit3 size={16} />
                    </button>
                  )}
                  <button
                    onClick={() => handleCancel(order)}
                    disabled={cancelMutation.isPending}
                    className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50"
                    title="취소"
                  >
                    <XCircle size={16} />
                  </button>
                </div>
              </div>

              {/* 주문 정보 그리드 */}
              <div className="grid grid-cols-4 gap-1 bg-gray-50 rounded-lg p-2.5 text-center">
                <div>
                  <p className="text-xs text-gray-500">현재가</p>
                  <p className="text-sm font-bold text-gray-800">
                    {order.current_price ? order.current_price.toLocaleString() : '-'}
                  </p>
                  {order.change_rate !== null && order.change_rate !== undefined && (
                    <p className={`text-xs ${
                      order.change_rate > 0 ? 'text-red-500' : order.change_rate < 0 ? 'text-blue-500' : 'text-gray-400'
                    }`}>
                      {order.change_rate > 0 ? '+' : ''}{order.change_rate.toFixed(1)}%
                    </p>
                  )}
                </div>
                <div>
                  <p className="text-xs text-gray-500">주문가</p>
                  <p className="text-sm font-bold text-gray-800">
                    {order.order_type === 'market'
                      ? '시장가'
                      : order.price?.toLocaleString()}
                  </p>
                  {order.current_price && order.price && order.price > 0 && order.current_price !== order.price && (
                    <p className="text-xs text-orange-500">
                      ⇄ {Math.abs(((order.current_price - order.price) / order.price) * 100).toFixed(1)}%
                    </p>
                  )}
                </div>
                <div>
                  <p className="text-xs text-gray-500">수량</p>
                  <p className="text-sm font-bold text-gray-800">{order.quantity}주</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">미체결</p>
                  <p className="text-sm font-bold text-orange-600">
                    {order.remaining_quantity || order.quantity}주
                  </p>
                  <p className="text-xs text-gray-400 text-right">{order.order_time}</p>
                </div>
              </div>
            </div>
          );})}
        </div>
      ) : (
        <div className="bg-white rounded-xl p-8 shadow-sm text-center">
          <Clock size={48} className="mx-auto text-gray-300 mb-3" />
          <p className="text-gray-500">미체결 주문이 없습니다</p>
          <p className="text-xs text-gray-400 mt-2">
            주문이 체결 대기 중이면 이곳에 표시됩니다
          </p>
        </div>
      )}

      {/* 안내 */}
      <div className="bg-blue-50 rounded-xl p-4 border border-blue-200">
        <div className="flex items-start gap-2">
          <Clock size={18} className="text-blue-600 mt-0.5" />
          <div className="text-sm text-blue-700">
            <p className="font-medium mb-1">미체결 주문 안내</p>
            <ul className="space-y-1 text-blue-600">
              <li>• 미체결 주문은 장 마감 시 자동 취소됩니다</li>
              <li>• 시장가 주문은 즉시 체결되어 표시되지 않습니다</li>
              <li>• 주문 취소 후 반영까지 시간이 걸릴 수 있습니다</li>
            </ul>
          </div>
        </div>
      </div>

      {/* 주문 정정 모달 */}
      {modifyModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-sm p-5">
            <h3 className="text-lg font-bold mb-4">주문 정정</h3>

            <div className="bg-gray-50 rounded-lg p-3 mb-4">
              <p className="font-bold">{modifyModal.stock_name}</p>
              <p className="text-sm text-gray-500">{modifyModal.stock_code}</p>
              <span
                className={`inline-block text-xs px-2 py-0.5 rounded mt-1 ${
                  modifyModal.side === 'buy'
                    ? 'bg-red-100 text-red-600'
                    : 'bg-blue-100 text-blue-600'
                }`}
              >
                {modifyModal.side === 'buy' ? '매수' : '매도'}
              </span>
            </div>

            <div className="space-y-3">
              {/* 시장가 토글 */}
              <div className="flex items-center justify-between bg-gray-50 rounded-lg p-3">
                <div className="flex items-center gap-2">
                  <Zap size={18} className={isMarketOrder ? 'text-yellow-500' : 'text-gray-400'} />
                  <span className="text-sm font-medium text-gray-700">시장가로 정정</span>
                </div>
                <button
                  type="button"
                  onClick={() => setIsMarketOrder(!isMarketOrder)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    isMarketOrder ? 'bg-yellow-500' : 'bg-gray-300'
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      isMarketOrder ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>

              {/* 가격 입력 (시장가 아닐 때만) */}
              {!isMarketOrder && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    정정 가격
                  </label>
                  <input
                    type="number"
                    value={modifyPrice}
                    onChange={(e) => setModifyPrice(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="가격 입력"
                  />
                </div>
              )}

              {/* 수량 입력 */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  정정 수량
                </label>
                <input
                  type="number"
                  value={modifyQuantity}
                  onChange={(e) => setModifyQuantity(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="수량 입력"
                />
              </div>

              {/* 시장가 안내 */}
              {isMarketOrder && (
                <p className="text-xs text-yellow-600 bg-yellow-50 p-2 rounded">
                  시장가 주문은 현재 호가에 즉시 체결됩니다.
                </p>
              )}
            </div>

            <div className="flex gap-2 mt-5">
              <button
                onClick={() => {
                  setModifyModal(null);
                  setModifyPrice('');
                  setModifyQuantity('');
                }}
                className="flex-1 py-2 border border-gray-300 rounded-lg text-gray-600 hover:bg-gray-50"
              >
                취소
              </button>
              <button
                onClick={handleModifySubmit}
                disabled={modifyMutation.isPending}
                className="flex-1 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
              >
                {modifyMutation.isPending ? '처리 중...' : '정정'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
