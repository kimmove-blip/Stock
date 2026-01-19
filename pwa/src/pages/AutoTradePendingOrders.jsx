import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { autoTradeAPI } from '../api/client';
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
} from 'lucide-react';

export default function AutoTradePendingOrders() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const queryClient = useQueryClient();

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

  const handleCancel = (order) => {
    const side = order.side === 'buy' ? '매수' : '매도';
    if (confirm(`${order.stock_name} ${side} 주문을 취소하시겠습니까?`)) {
      cancelMutation.mutate(order.order_id);
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

  return (
    <div className="max-w-md mx-auto space-y-4">
      {/* 새로고침 */}
      <div className="flex justify-between items-center">
        <p className="text-sm text-gray-500">
          {orders.length}건의 미체결 주문
        </p>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1 text-sm text-gray-600 hover:text-purple-600 transition-colors"
        >
          <RefreshCw size={16} className={isFetching ? 'animate-spin' : ''} />
          새로고침
        </button>
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
        <div className="space-y-3">
          {orders.map((order) => (
            <div
              key={order.order_id}
              className="bg-white rounded-xl p-4 shadow-sm"
            >
              <div className="flex items-start justify-between mb-3">
                <div
                  className="flex-1 cursor-pointer"
                  onClick={() => navigate(`/stock/${order.stock_code}`)}
                >
                  <div className="flex items-center gap-2">
                    {order.side === 'buy' ? (
                      <ShoppingCart size={16} className="text-red-500" />
                    ) : (
                      <Banknote size={16} className="text-blue-500" />
                    )}
                    <span
                      className={`text-xs px-2 py-0.5 rounded font-medium ${
                        order.side === 'buy'
                          ? 'bg-red-100 text-red-600'
                          : 'bg-blue-100 text-blue-600'
                      }`}
                    >
                      {order.side === 'buy' ? '매수' : '매도'}
                    </span>
                    <p className="font-bold text-gray-800">{order.stock_name}</p>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">{order.stock_code}</p>
                </div>
                <button
                  onClick={() => handleCancel(order)}
                  disabled={cancelMutation.isLoading}
                  className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50"
                >
                  <XCircle size={20} />
                </button>
              </div>

              <div className="grid grid-cols-3 gap-2 bg-gray-50 rounded-lg p-3">
                <div>
                  <p className="text-xs text-gray-500">주문 가격</p>
                  <p className="font-bold text-gray-800">
                    {order.order_type === 'market'
                      ? '시장가'
                      : order.price?.toLocaleString() + '원'}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">주문 수량</p>
                  <p className="font-bold text-gray-800">{order.quantity}주</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">미체결</p>
                  <p className="font-bold text-orange-600">
                    {order.remaining_quantity || order.quantity}주
                  </p>
                </div>
              </div>

              <div className="flex items-center justify-between mt-3 text-xs text-gray-500">
                <span className="flex items-center gap-1">
                  <Clock size={12} />
                  {order.order_time}
                </span>
                <span>
                  주문금액: {((order.price || 0) * (order.quantity || 0)).toLocaleString()}원
                </span>
              </div>
            </div>
          ))}
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
    </div>
  );
}
