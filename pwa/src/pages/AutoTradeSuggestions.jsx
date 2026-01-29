import { useState, useEffect, useCallback } from 'react';
import { flushSync } from 'react-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { autoTradeAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import Loading from '../components/Loading';
import {
  FileText,
  Check,
  X,
  AlertCircle,
  Clock,
  CheckCircle2,
  XCircle,
  TrendingUp,
  TrendingDown,
  Star,
  RefreshCw,
  ShoppingCart,
  Banknote,
  Zap,
} from 'lucide-react';

// 토스트 컴포넌트
function Toast({ message, type, onClose }) {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    // 마운트 후 바로 visible로 설정 (애니메이션 시작)
    requestAnimationFrame(() => setIsVisible(true));
    const timer = setTimeout(() => {
      setIsVisible(false);
      setTimeout(onClose, 300); // 애니메이션 완료 후 제거
    }, 2700);
    return () => clearTimeout(timer);
  }, [onClose]);

  const bgColor = type === 'success' ? 'bg-green-500' : type === 'error' ? 'bg-red-500' : 'bg-gray-700';
  const icon = type === 'success' ? <CheckCircle2 size={18} /> : type === 'error' ? <XCircle size={18} /> : null;

  return (
    <div
      className={`fixed top-4 left-1/2 -translate-x-1/2 z-50 ${bgColor} text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-2 transition-all duration-300 ${
        isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-4'
      }`}
    >
      {icon}
      <span className="text-sm font-medium">{message}</span>
    </div>
  );
}

// 호가 단위 계산 함수
const getTickSize = (price) => {
  if (price < 1000) return 1;
  if (price < 5000) return 5;
  if (price < 10000) return 10;
  if (price < 50000) return 50;
  if (price < 100000) return 100;
  if (price < 500000) return 500;
  return 1000;
};

// 호가 단위로 반올림/내림
const roundToTick = (price, roundDown = true) => {
  const tick = getTickSize(price);
  if (roundDown) {
    return Math.floor(price / tick) * tick;
  }
  return Math.ceil(price / tick) * tick;
};

// 개별 제안 카드 컴포넌트
function SuggestionCard({ suggestion, activeTab, onApprove, onReject, isApproving, isRejecting, isRemoving }) {
  const navigate = useNavigate();
  const isBuy = activeTab === 'buy';
  const isPending = suggestion.status === 'pending';

  // 가격 관련 상태
  const suggestedPrice = suggestion.suggested_price || 0;
  const currentPrice = suggestion.current_price || suggestedPrice;

  // 매수: 제안가 ~ 현재가, 매도: 현재가 ~ 현재가+10%
  const minPrice = isBuy ? suggestedPrice : currentPrice;
  const maxPrice = isBuy ? currentPrice : Math.round(currentPrice * 1.1);

  const [selectedPrice, setSelectedPrice] = useState(
    isBuy ? suggestedPrice : currentPrice
  );
  const [isMarketOrder, setIsMarketOrder] = useState(false);
  const [customQuantity, setCustomQuantity] = useState(suggestion.quantity || 1);

  // 가격 범위가 동일한 경우 (슬라이더 비활성화)
  const priceRangeEqual = minPrice === maxPrice || minPrice <= 0 || maxPrice <= 0;

  // 슬라이더 값 변경 핸들러
  const handleSliderChange = (e) => {
    const value = parseInt(e.target.value);
    setSelectedPrice(roundToTick(value, isBuy)); // 매수는 내림, 매도는 올림
  };

  // 수량 변경 핸들러
  const handleQuantityChange = (delta) => {
    setCustomQuantity(prev => Math.max(1, prev + delta));
  };

  // 시장가 토글
  const handleMarketOrderToggle = () => {
    setIsMarketOrder(!isMarketOrder);
  };

  // 승인 핸들러
  const handleApproveClick = () => {
    const action = isBuy ? '매수' : '매도';
    const priceText = isMarketOrder
      ? '시장가'
      : `${selectedPrice.toLocaleString()}원`;
    const quantity = customQuantity;
    const totalAmount = isMarketOrder
      ? currentPrice * quantity
      : selectedPrice * quantity;

    if (
      confirm(
        `${suggestion.stock_name} ${action}를 승인하시겠습니까?\n\n` +
          `주문 유형: ${priceText}\n` +
          `수량: ${quantity}주\n` +
          `예상 금액: ${totalAmount.toLocaleString()}원`
      )
    ) {
      onApprove(suggestion.id, {
        custom_price: isMarketOrder ? null : selectedPrice,
        custom_quantity: customQuantity,
        is_market_order: isMarketOrder,
      }, suggestion.stock_name);
    }
  };

  // 거부 핸들러
  const handleRejectClick = () => {
    const action = isBuy ? '매수' : '매도';
    if (confirm(`${suggestion.stock_name} ${action}를 거부하시겠습니까?`)) {
      onReject(suggestion.id, suggestion.stock_name);
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'pending':
        return (
          <span className="flex items-center gap-1 text-xs bg-orange-100 text-orange-600 px-2 py-0.5 rounded-full">
            <Clock size={12} />
            대기중
          </span>
        );
      case 'approved':
        return (
          <span className="flex items-center gap-1 text-xs bg-green-100 text-green-600 px-2 py-0.5 rounded-full">
            <CheckCircle2 size={12} />
            승인됨
          </span>
        );
      case 'rejected':
        return (
          <span className="flex items-center gap-1 text-xs bg-red-100 text-red-600 px-2 py-0.5 rounded-full">
            <XCircle size={12} />
            거부됨
          </span>
        );
      case 'executed':
        return (
          <span className="flex items-center gap-1 text-xs bg-blue-100 text-blue-600 px-2 py-0.5 rounded-full">
            <Check size={12} />
            체결됨
          </span>
        );
      case 'expired':
        return (
          <span className="flex items-center gap-1 text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
            <Clock size={12} />
            만료됨
          </span>
        );
      default:
        return null;
    }
  };

  // 가격 차이 퍼센트
  const priceDiff = currentPrice > 0 ? ((currentPrice - suggestedPrice) / suggestedPrice * 100).toFixed(1) : 0;
  const priceDiffPositive = parseFloat(priceDiff) >= 0;

  return (
    <div
      className={`bg-white rounded-xl p-4 shadow-sm transition-opacity duration-200 ${
        isRemoving ? 'opacity-0' : 'opacity-100'
      }`}
    >
      {/* 헤더 */}
      <div className="flex items-start justify-between mb-3">
        <div
          className="flex-1 cursor-pointer"
          onClick={() => navigate(`/stock/${suggestion.stock_code}`)}
        >
          <div className="flex items-center gap-2">
            <span
              className={`text-xs px-2 py-0.5 rounded font-medium ${
                isBuy ? 'bg-red-100 text-red-600' : 'bg-blue-100 text-blue-600'
              }`}
            >
              {isBuy ? '매수' : '매도'}
            </span>
            <p className="font-bold text-gray-800">
              {suggestion.stock_name || suggestion.stock_code}
            </p>
            {suggestion.score && suggestion.score >= 80 && (
              <Star size={14} className="text-yellow-500 fill-yellow-500" />
            )}
          </div>
          <p className="text-xs text-gray-500">{suggestion.stock_code}</p>
        </div>
        {getStatusBadge(suggestion.status)}
      </div>

      {/* 가격 정보 (제안가 / 현재가) */}
      <div className="grid grid-cols-2 gap-2 mb-3 bg-gray-50 rounded-lg p-3">
        <div>
          <p className="text-xs text-gray-500">제안 가격</p>
          <p className="font-bold text-gray-800">
            {suggestedPrice.toLocaleString()}원
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">현재가</p>
          <p className={`font-bold ${
            suggestion.change_rate > 0 ? 'text-red-600' : suggestion.change_rate < 0 ? 'text-blue-600' : 'text-gray-800'
          }`}>
            {currentPrice.toLocaleString()}원
          </p>
          {suggestion.change_rate !== null && suggestion.change_rate !== undefined && (
            <p className={`text-xs ${
              suggestion.change_rate > 0 ? 'text-red-500' : suggestion.change_rate < 0 ? 'text-blue-500' : 'text-gray-400'
            }`}>
              {suggestion.change_rate > 0 ? '+' : ''}{suggestion.change_rate.toFixed(1)}%
            </p>
          )}
        </div>
      </div>

      {/* 수량 / AI점수(매수) 또는 수익률(매도) */}
      <div className="grid grid-cols-2 gap-2 mb-3 bg-gray-50 rounded-lg p-3">
        <div>
          <p className="text-xs text-gray-500">수량</p>
          {isPending ? (
            <div className="flex items-center gap-1">
              <button
                onClick={() => handleQuantityChange(-1)}
                className="w-7 h-7 flex items-center justify-center bg-gray-200 hover:bg-gray-300 rounded text-gray-700 font-bold"
              >
                -
              </button>
              <input
                type="number"
                value={customQuantity}
                onChange={(e) => setCustomQuantity(Math.max(1, parseInt(e.target.value) || 1))}
                className="w-14 h-7 text-center font-bold text-gray-800 border border-gray-300 rounded"
                min="1"
              />
              <button
                onClick={() => handleQuantityChange(1)}
                className="w-7 h-7 flex items-center justify-center bg-gray-200 hover:bg-gray-300 rounded text-gray-700 font-bold"
              >
                +
              </button>
              <span className="text-sm text-gray-600">주</span>
            </div>
          ) : (
            <p className="font-bold text-gray-800">{suggestion.quantity}주</p>
          )}
        </div>
        <div>
          <p className="text-xs text-gray-500">
            {isBuy ? 'AI 점수' : '수익률'}
          </p>
          {isBuy ? (
            <p
              className={`font-bold ${
                (suggestion.score || 0) >= 80
                  ? 'text-green-600'
                  : (suggestion.score || 0) >= 60
                  ? 'text-yellow-600'
                  : 'text-gray-600'
              }`}
            >
              {suggestion.score || '-'}점
            </p>
          ) : (
            <p
              className={`font-bold ${
                (suggestion.profit_rate || 0) >= 0 ? 'text-red-600' : 'text-blue-600'
              }`}
            >
              {(suggestion.profit_rate || 0) >= 0 ? '+' : ''}
              {suggestion.profit_rate?.toFixed(2) || 0}%
            </p>
          )}
        </div>
      </div>

      {/* 제안 사유 */}
      {suggestion.reason && (
        <div className="mb-3">
          <p className="text-xs text-gray-500 mb-1">제안 사유</p>
          <p
            className={`text-sm p-2 rounded-lg ${
              isBuy ? 'text-gray-700 bg-blue-50' : 'text-gray-700 bg-orange-50'
            }`}
          >
            {suggestion.reason}
          </p>
        </div>
      )}

      {/* 주문 가격 설정 (대기중일 때만) */}
      {isPending && (
        <div className="mb-3 p-3 bg-purple-50 rounded-lg border border-purple-200">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-medium text-purple-700">주문 가격 설정</p>
            <label className="flex items-center gap-2 cursor-pointer">
              <span className="text-xs text-purple-600">시장가</span>
              <div
                onClick={handleMarketOrderToggle}
                className={`relative w-10 h-5 rounded-full transition-colors ${
                  isMarketOrder ? 'bg-purple-600' : 'bg-gray-300'
                }`}
              >
                <div
                  className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                    isMarketOrder ? 'translate-x-5' : 'translate-x-0.5'
                  }`}
                />
              </div>
            </label>
          </div>

          {!isMarketOrder && (
            <>
              {/* 가격 슬라이더 */}
              <div className="mb-2">
                <input
                  type="range"
                  min={minPrice}
                  max={maxPrice}
                  value={selectedPrice}
                  onChange={handleSliderChange}
                  disabled={priceRangeEqual}
                  className="w-full h-2 bg-purple-200 rounded-lg appearance-none cursor-pointer accent-purple-600 disabled:opacity-50"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>{minPrice.toLocaleString()}원</span>
                  <span>{maxPrice.toLocaleString()}원</span>
                </div>
              </div>

              {/* 선택된 가격 표시 */}
              <div className="flex items-center justify-between">
                <span className="text-sm text-purple-700">주문 가격:</span>
                <span className="text-lg font-bold text-purple-800">
                  {selectedPrice.toLocaleString()}원
                </span>
              </div>
            </>
          )}

          {isMarketOrder && (
            <div className="flex items-center gap-2 text-sm text-purple-700">
              <Zap size={16} className="text-yellow-500" />
              <span>시장가로 즉시 체결됩니다</span>
            </div>
          )}

          {/* 예상 금액 */}
          <div className="mt-2 pt-2 border-t border-purple-200 flex items-center justify-between">
            <span className="text-xs text-purple-600">예상 체결금액:</span>
            <span className="text-sm font-medium text-purple-800">
              {(
                (isMarketOrder ? currentPrice : selectedPrice) * customQuantity
              ).toLocaleString()}
              원
            </span>
          </div>
        </div>
      )}

      {/* 제안 시간 */}
      <div className="flex items-center justify-between text-xs text-gray-500 mb-3">
        <span>제안 시간: {suggestion.created_at}</span>
      </div>

      {/* 승인/거부 버튼 (대기중일 때만) */}
      {isPending && (
        <div className="flex gap-2">
          <button
            onClick={handleApproveClick}
            disabled={isApproving}
            className={`flex-1 flex items-center justify-center gap-2 text-white py-2 rounded-lg font-medium hover:opacity-90 disabled:opacity-50 transition-colors ${
              isBuy ? 'bg-red-500' : 'bg-blue-500'
            }`}
          >
            <Check size={18} />
            {isBuy ? '매수 승인' : '매도 승인'}
          </button>
          <button
            onClick={handleRejectClick}
            disabled={isRejecting}
            className="flex-1 flex items-center justify-center gap-2 bg-gray-500 text-white py-2 rounded-lg font-medium hover:bg-gray-600 disabled:opacity-50 transition-colors"
          >
            <X size={18} />
            거부
          </button>
        </div>
      )}
    </div>
  );
}

export default function AutoTradeSuggestions() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState('buy'); // buy, sell
  const [filter, setFilter] = useState('pending');
  const [toast, setToast] = useState(null);
  const [removingIds, setRemovingIds] = useState(new Set());

  const showToast = useCallback((message, type = 'success') => {
    setToast({ message, type });
  }, []);

  const hideToast = useCallback(() => {
    setToast(null);
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

  // 새로고침 키 (변경 시 쿼리 캐시 완전 무효화)
  const [refreshKey, setRefreshKey] = useState(() => Date.now());

  // 매수 제안 목록 조회 - 캐시 완전 비활성화
  const {
    data: buySuggestions,
    isLoading: buyLoading,
    refetch: refetchBuy,
    isFetching: buyFetching,
  } = useQuery({
    queryKey: ['autoTradeSuggestions', 'buy', filter, refreshKey],
    queryFn: () => autoTradeAPI.suggestions(filter).then((res) => res.data),
    staleTime: 0,
    gcTime: 0,
  });

  // 매도 제안 목록 조회 - 캐시 완전 비활성화
  const {
    data: sellSuggestions,
    isLoading: sellLoading,
    refetch: refetchSell,
    isFetching: sellFetching,
  } = useQuery({
    queryKey: ['autoTradeSuggestions', 'sell', filter, refreshKey],
    queryFn: () => autoTradeAPI.sellSuggestions(filter).then((res) => res.data),
    staleTime: 0,
    gcTime: 0,
  });

  // 수량 조정 확인 상태
  const [adjustmentInfo, setAdjustmentInfo] = useState(null);

  // 매수 승인
  const approveBuyMutation = useMutation({
    mutationFn: ({ id, data, stockName }) => autoTradeAPI.approveSuggestion(id, data).then(res => ({ ...res, id, stockName })),
    onMutate: ({ id }) => {
      setRemovingIds(prev => new Set(prev).add(id));
    },
    onSuccess: (result) => {
      // 수량 조정이 필요한 경우
      if (result.data?.status === 'need_adjustment') {
        setRemovingIds(prev => {
          const next = new Set(prev);
          next.delete(result.id);
          return next;
        });
        setAdjustmentInfo({
          suggestionId: result.id,
          stockName: result.stockName,
          ...result.data
        });
        return;
      }

      showToast(`${result.stockName} 매수 주문이 접수되었습니다`, 'success');
      setTimeout(() => {
        refetchBuy();
        queryClient.invalidateQueries(['autoTradeStatus']);
        queryClient.invalidateQueries(['pendingOrders']);
        setRemovingIds(prev => {
          const next = new Set(prev);
          next.delete(result.id);
          return next;
        });
      }, 300);
    },
    onError: (error, variables) => {
      setRemovingIds(prev => {
        const next = new Set(prev);
        next.delete(variables.id);
        return next;
      });
      showToast(error.response?.data?.detail || '승인 처리에 실패했습니다.', 'error');
    },
  });

  // 조정된 수량으로 재주문
  const handleForceAdjusted = () => {
    if (!adjustmentInfo) return;
    approveBuyMutation.mutate({
      id: adjustmentInfo.suggestionId,
      data: { force_adjusted: true },
      stockName: adjustmentInfo.stockName
    });
    setAdjustmentInfo(null);
  };

  // 매수 거부
  const rejectBuyMutation = useMutation({
    mutationFn: ({ id, stockName }) => autoTradeAPI.rejectSuggestion(id).then(res => ({ ...res, id, stockName })),
    onMutate: ({ id }) => {
      setRemovingIds(prev => new Set(prev).add(id));
    },
    onSuccess: (result) => {
      showToast(`${result.stockName} 제안을 거부했습니다`, 'success');
      setTimeout(() => {
        refetchBuy();
        queryClient.invalidateQueries(['autoTradeStatus']);
        setRemovingIds(prev => {
          const next = new Set(prev);
          next.delete(result.id);
          return next;
        });
      }, 300);
    },
    onError: (error, variables) => {
      setRemovingIds(prev => {
        const next = new Set(prev);
        next.delete(variables.id);
        return next;
      });
      showToast(error.response?.data?.detail || '거부 처리에 실패했습니다.', 'error');
    },
  });

  // 매도 승인
  const approveSellMutation = useMutation({
    mutationFn: ({ id, data, stockName }) => autoTradeAPI.approveSellSuggestion(id, data).then(res => ({ ...res, id, stockName })),
    onMutate: ({ id }) => {
      setRemovingIds(prev => new Set(prev).add(id));
    },
    onSuccess: (result) => {
      showToast(`${result.stockName} 매도 주문이 접수되었습니다`, 'success');
      setTimeout(() => {
        refetchSell();
        queryClient.invalidateQueries(['autoTradeStatus']);
        queryClient.invalidateQueries(['pendingOrders']);
        setRemovingIds(prev => {
          const next = new Set(prev);
          next.delete(result.id);
          return next;
        });
      }, 300);
    },
    onError: (error, variables) => {
      setRemovingIds(prev => {
        const next = new Set(prev);
        next.delete(variables.id);
        return next;
      });
      showToast(error.response?.data?.detail || '승인 처리에 실패했습니다.', 'error');
    },
  });

  // 매도 거부
  const rejectSellMutation = useMutation({
    mutationFn: ({ id, stockName }) => autoTradeAPI.rejectSellSuggestion(id).then(res => ({ ...res, id, stockName })),
    onMutate: ({ id }) => {
      setRemovingIds(prev => new Set(prev).add(id));
    },
    onSuccess: (result) => {
      showToast(`${result.stockName} 제안을 거부했습니다`, 'success');
      setTimeout(() => {
        refetchSell();
        queryClient.invalidateQueries(['autoTradeStatus']);
        setRemovingIds(prev => {
          const next = new Set(prev);
          next.delete(result.id);
          return next;
        });
      }, 300);
    },
    onError: (error, variables) => {
      setRemovingIds(prev => {
        const next = new Set(prev);
        next.delete(variables.id);
        return next;
      });
      showToast(error.response?.data?.detail || '거부 처리에 실패했습니다.', 'error');
    },
  });

  const handleApprove = (id, data, isSell, stockName) => {
    if (isSell) {
      approveSellMutation.mutate({ id, data, stockName });
    } else {
      approveBuyMutation.mutate({ id, data, stockName });
    }
  };

  const handleReject = (id, isSell, stockName) => {
    if (isSell) {
      rejectSellMutation.mutate({ id, stockName });
    } else {
      rejectBuyMutation.mutate({ id, stockName });
    }
  };

  const isLoading = activeTab === 'buy' ? buyLoading : sellLoading;
  const isFetching = activeTab === 'buy' ? buyFetching : sellFetching;
  const rawSuggestions = activeTab === 'buy' ? buySuggestions : sellSuggestions;
  const refetch = activeTab === 'buy' ? refetchBuy : refetchSell;

  // 새로고침 중 상태 (refreshKey 변경 직후)
  const [isRefreshing, setIsRefreshing] = useState(false);

  // 새로고침: 캐시 완전 삭제 후 새로 fetch (flushSync로 즉시 UI 업데이트)
  const handleManualRefresh = useCallback(() => {
    // flushSync로 즉시 로딩 화면 표시 (이전 데이터 깜빡임 방지)
    flushSync(() => {
      setIsRefreshing(true);
    });
    // 기존 캐시 완전 삭제 (이전 데이터 표시 방지)
    queryClient.removeQueries({ queryKey: ['autoTradeSuggestions'] });
    setRefreshKey(Date.now());
  }, [queryClient]);

  // 데이터 로드 완료 시 refreshing 상태 해제
  useEffect(() => {
    if (!isFetching && isRefreshing) {
      setIsRefreshing(false);
    }
  }, [isFetching, isRefreshing]);

  // 로딩 중이거나 새로고침 중이면 로딩 표시
  if (isLoading || isRefreshing) {
    return <Loading text="매매 제안 불러오는 중..." />;
  }

  const suggestions = rawSuggestions;

  const filters = [
    { value: 'pending', label: '대기중' },
    { value: 'executed', label: '체결됨' },
    { value: 'all', label: '전체' },
  ];

  const buyPendingCount =
    buySuggestions?.filter((s) => s.status === 'pending')?.length || 0;
  const sellPendingCount =
    sellSuggestions?.filter((s) => s.status === 'pending')?.length || 0;

  return (
    <div className="max-w-md mx-auto space-y-4">
      {/* 토스트 알림 */}
      {toast && <Toast message={toast.message} type={toast.type} onClose={hideToast} />}

      {/* 수량 조정 확인 다이얼로그 */}
      {adjustmentInfo && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl p-5 max-w-sm w-full shadow-xl">
            <h3 className="text-lg font-bold text-gray-800 mb-3">
              주문가능금액 초과
            </h3>
            <p className="text-sm text-gray-600 mb-4">
              <span className="font-medium text-gray-800">{adjustmentInfo.stockName}</span>의
              주문금액이 주문가능금액을 초과합니다.
            </p>
            <div className="bg-gray-50 rounded-lg p-3 mb-4 text-sm space-y-1">
              <div className="flex justify-between">
                <span className="text-gray-500">주문가능금액</span>
                <span className="font-medium">{adjustmentInfo.max_buy_amt?.toLocaleString()}원</span>
              </div>
              <div className="flex justify-between text-red-500">
                <span>원래 주문금액</span>
                <span className="line-through">{adjustmentInfo.original_quantity}주 × {adjustmentInfo.price?.toLocaleString()}원</span>
              </div>
              <div className="flex justify-between text-blue-600 font-medium">
                <span>조정 후</span>
                <span>{adjustmentInfo.adjusted_quantity}주 × {adjustmentInfo.price?.toLocaleString()}원 = {adjustmentInfo.adjusted_amount?.toLocaleString()}원</span>
              </div>
            </div>
            <p className="text-sm text-gray-600 mb-4">
              <span className="font-medium text-blue-600">{adjustmentInfo.adjusted_quantity}주</span>로
              수량을 조정하여 주문하시겠습니까?
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setAdjustmentInfo(null)}
                className="flex-1 py-2.5 rounded-lg bg-gray-100 text-gray-700 font-medium hover:bg-gray-200"
              >
                취소
              </button>
              <button
                onClick={handleForceAdjusted}
                disabled={approveBuyMutation.isPending}
                className="flex-1 py-2.5 rounded-lg bg-blue-500 text-white font-medium hover:bg-blue-600 disabled:opacity-50"
              >
                {approveBuyMutation.isPending ? '주문 중...' : '조정 후 주문'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 매수/매도 탭 */}
      <div className="flex gap-2 bg-white rounded-xl p-2 shadow-sm">
        <button
          onClick={() => setActiveTab('buy')}
          className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-lg font-medium transition-colors ${
            activeTab === 'buy'
              ? 'bg-red-500 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          <ShoppingCart size={18} />
          매수 제안
          {buyPendingCount > 0 && (
            <span
              className={`text-xs px-1.5 py-0.5 rounded-full ${
                activeTab === 'buy' ? 'bg-white/20' : 'bg-red-100 text-red-600'
              }`}
            >
              {buyPendingCount}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveTab('sell')}
          className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-lg font-medium transition-colors ${
            activeTab === 'sell'
              ? 'bg-blue-500 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          <Banknote size={18} />
          매도 제안
          {sellPendingCount > 0 && (
            <span
              className={`text-xs px-1.5 py-0.5 rounded-full ${
                activeTab === 'sell' ? 'bg-white/20' : 'bg-blue-100 text-blue-600'
              }`}
            >
              {sellPendingCount}
            </span>
          )}
        </button>
      </div>

      {/* 필터 탭 */}
      <div className="flex gap-2 bg-white rounded-xl p-2 shadow-sm">
        {filters.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-colors ${
              filter === f.value
                ? 'bg-purple-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {f.label}
          </button>
        ))}
        <button
          onClick={handleManualRefresh}
          disabled={isFetching}
          className="p-2 text-gray-600 hover:text-purple-600 transition-colors"
        >
          <RefreshCw size={18} className={isFetching ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* 제안 목록 - dataKey로 데이터 변경 시 전체 리마운트 */}
      {suggestions?.length > 0 ? (
        <div className="space-y-3" key={JSON.stringify(suggestions.map(s => `${s.id}-${s.change_rate}`))}>
          {suggestions.map((suggestion) => (
            <SuggestionCard
              key={`${suggestion.id}-${suggestion.change_rate}`}
              suggestion={suggestion}
              activeTab={activeTab}
              onApprove={(id, data, stockName) => handleApprove(id, data, activeTab === 'sell', stockName)}
              onReject={(id, stockName) => handleReject(id, activeTab === 'sell', stockName)}
              isApproving={
                activeTab === 'buy'
                  ? approveBuyMutation.isPending
                  : approveSellMutation.isPending
              }
              isRejecting={
                activeTab === 'buy'
                  ? rejectBuyMutation.isPending
                  : rejectSellMutation.isPending
              }
              isRemoving={removingIds.has(suggestion.id)}
            />
          ))}
        </div>
      ) : (
        <div className="bg-white rounded-xl p-8 shadow-sm text-center">
          {activeTab === 'buy' ? (
            <TrendingUp size={48} className="mx-auto text-gray-300 mb-3" />
          ) : (
            <TrendingDown size={48} className="mx-auto text-gray-300 mb-3" />
          )}
          <p className="text-gray-500">
            {filter === 'pending'
              ? `대기 중인 ${activeTab === 'buy' ? '매수' : '매도'} 제안이 없습니다`
              : filter === 'approved'
              ? `승인된 ${activeTab === 'buy' ? '매수' : '매도'} 제안이 없습니다`
              : `${activeTab === 'buy' ? '매수' : '매도'} 제안이 없습니다`}
          </p>
          <p className="text-xs text-gray-400 mt-2">
            {activeTab === 'buy'
              ? 'AI가 좋은 매수 기회를 찾으면 알려드립니다'
              : 'AI가 적절한 매도 시점을 찾으면 알려드립니다'}
          </p>
        </div>
      )}

      {/* 버전 표시 (디버그용) */}
      <div className="text-xs text-gray-400 text-center">v10-flushSync</div>

      {/* 안내 */}
      <div
        className={`rounded-xl p-4 border ${
          activeTab === 'buy'
            ? 'bg-blue-50 border-blue-200'
            : 'bg-orange-50 border-orange-200'
        }`}
      >
        <div className="flex items-start gap-2">
          {activeTab === 'buy' ? (
            <TrendingUp size={18} className="text-blue-600 mt-0.5" />
          ) : (
            <TrendingDown size={18} className="text-orange-600 mt-0.5" />
          )}
          <div
            className={`text-sm ${
              activeTab === 'buy' ? 'text-blue-700' : 'text-orange-700'
            }`}
          >
            <p className="font-medium mb-1">
              {activeTab === 'buy' ? '매수 제안 안내' : '매도 제안 안내'}
            </p>
            <ul
              className={`space-y-1 ${
                activeTab === 'buy' ? 'text-blue-600' : 'text-orange-600'
              }`}
            >
              {activeTab === 'buy' ? (
                <>
                  <li>슬라이더로 주문 가격을 조정할 수 있습니다</li>
                  <li>시장가 옵션을 켜면 즉시 체결됩니다</li>
                  <li>제안은 당일 장 종료 시 자동 만료됩니다</li>
                </>
              ) : (
                <>
                  <li>현재가 이상으로 지정가 주문이 가능합니다</li>
                  <li>시장가 옵션을 켜면 즉시 체결됩니다</li>
                  <li>수익률을 확인 후 신중하게 결정하세요</li>
                </>
              )}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
