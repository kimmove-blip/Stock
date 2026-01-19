import { useState } from 'react';
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
} from 'lucide-react';

export default function AutoTradeSuggestions() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState('buy'); // buy, sell
  const [filter, setFilter] = useState('pending');

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

  // 매수 제안 목록 조회
  const { data: buySuggestions, isLoading: buyLoading, refetch: refetchBuy, isFetching: buyFetching } = useQuery({
    queryKey: ['autoTradeSuggestions', 'buy', filter],
    queryFn: () => autoTradeAPI.suggestions(filter).then((res) => res.data),
    staleTime: 1000 * 30,
    refetchOnWindowFocus: true,
  });

  // 매도 제안 목록 조회
  const { data: sellSuggestions, isLoading: sellLoading, refetch: refetchSell, isFetching: sellFetching } = useQuery({
    queryKey: ['autoTradeSuggestions', 'sell', filter],
    queryFn: () => autoTradeAPI.sellSuggestions(filter).then((res) => res.data),
    staleTime: 1000 * 30,
    refetchOnWindowFocus: true,
  });

  // 매수 승인
  const approveBuyMutation = useMutation({
    mutationFn: (id) => autoTradeAPI.approveSuggestion(id),
    onSuccess: () => {
      queryClient.invalidateQueries(['autoTradeSuggestions']);
      queryClient.invalidateQueries(['autoTradeStatus']);
    },
    onError: (error) => {
      alert(error.response?.data?.detail || '승인 처리에 실패했습니다.');
    },
  });

  // 매수 거부
  const rejectBuyMutation = useMutation({
    mutationFn: (id) => autoTradeAPI.rejectSuggestion(id),
    onSuccess: () => {
      queryClient.invalidateQueries(['autoTradeSuggestions']);
      queryClient.invalidateQueries(['autoTradeStatus']);
    },
    onError: (error) => {
      alert(error.response?.data?.detail || '거부 처리에 실패했습니다.');
    },
  });

  // 매도 승인
  const approveSellMutation = useMutation({
    mutationFn: (id) => autoTradeAPI.approveSellSuggestion(id),
    onSuccess: () => {
      queryClient.invalidateQueries(['autoTradeSuggestions']);
      queryClient.invalidateQueries(['autoTradeStatus']);
    },
    onError: (error) => {
      alert(error.response?.data?.detail || '승인 처리에 실패했습니다.');
    },
  });

  // 매도 거부
  const rejectSellMutation = useMutation({
    mutationFn: (id) => autoTradeAPI.rejectSellSuggestion(id),
    onSuccess: () => {
      queryClient.invalidateQueries(['autoTradeSuggestions']);
      queryClient.invalidateQueries(['autoTradeStatus']);
    },
    onError: (error) => {
      alert(error.response?.data?.detail || '거부 처리에 실패했습니다.');
    },
  });

  const handleApprove = (id, stockName, isSell) => {
    const action = isSell ? '매도' : '매수';
    if (confirm(`${stockName} ${action}를 승인하시겠습니까?`)) {
      if (isSell) {
        approveSellMutation.mutate(id);
      } else {
        approveBuyMutation.mutate(id);
      }
    }
  };

  const handleReject = (id, stockName, isSell) => {
    const action = isSell ? '매도' : '매수';
    if (confirm(`${stockName} ${action}를 거부하시겠습니까?`)) {
      if (isSell) {
        rejectSellMutation.mutate(id);
      } else {
        rejectBuyMutation.mutate(id);
      }
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

  const isLoading = activeTab === 'buy' ? buyLoading : sellLoading;
  const isFetching = activeTab === 'buy' ? buyFetching : sellFetching;
  const suggestions = activeTab === 'buy' ? buySuggestions : sellSuggestions;
  const refetch = activeTab === 'buy' ? refetchBuy : refetchSell;

  if (isLoading) return <Loading text="매매 제안 불러오는 중..." />;

  const filters = [
    { value: 'pending', label: '대기중' },
    { value: 'approved', label: '승인됨' },
    { value: 'all', label: '전체' },
  ];

  const buyPendingCount = buySuggestions?.filter(s => s.status === 'pending')?.length || 0;
  const sellPendingCount = sellSuggestions?.filter(s => s.status === 'pending')?.length || 0;

  return (
    <div className="max-w-md mx-auto space-y-4">
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
            <span className={`text-xs px-1.5 py-0.5 rounded-full ${
              activeTab === 'buy' ? 'bg-white/20' : 'bg-red-100 text-red-600'
            }`}>
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
            <span className={`text-xs px-1.5 py-0.5 rounded-full ${
              activeTab === 'sell' ? 'bg-white/20' : 'bg-blue-100 text-blue-600'
            }`}>
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
          onClick={() => refetch()}
          disabled={isFetching}
          className="p-2 text-gray-600 hover:text-purple-600 transition-colors"
        >
          <RefreshCw size={18} className={isFetching ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* 제안 목록 */}
      {suggestions?.length > 0 ? (
        <div className="space-y-3">
          {suggestions.map((suggestion) => (
            <div
              key={suggestion.id}
              className="bg-white rounded-xl p-4 shadow-sm"
            >
              {/* 헤더 */}
              <div className="flex items-start justify-between mb-3">
                <div
                  className="flex-1 cursor-pointer"
                  onClick={() => navigate(`/stock/${suggestion.stock_code}`)}
                >
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                      activeTab === 'buy' ? 'bg-red-100 text-red-600' : 'bg-blue-100 text-blue-600'
                    }`}>
                      {activeTab === 'buy' ? '매수' : '매도'}
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

              {/* 정보 */}
              <div className="grid grid-cols-3 gap-2 mb-3 bg-gray-50 rounded-lg p-3">
                <div>
                  <p className="text-xs text-gray-500">제안 가격</p>
                  <p className="font-bold text-gray-800">
                    {suggestion.suggested_price?.toLocaleString()}원
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">수량</p>
                  <p className="font-bold text-gray-800">{suggestion.quantity}주</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">
                    {activeTab === 'buy' ? 'AI 점수' : '수익률'}
                  </p>
                  {activeTab === 'buy' ? (
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
                  <p className={`text-sm p-2 rounded-lg ${
                    activeTab === 'buy' ? 'text-gray-700 bg-blue-50' : 'text-gray-700 bg-orange-50'
                  }`}>
                    {suggestion.reason}
                  </p>
                </div>
              )}

              {/* 제안 시간 */}
              <div className="flex items-center justify-between text-xs text-gray-500 mb-3">
                <span>제안 시간: {suggestion.created_at}</span>
                <span>
                  예상 금액:{' '}
                  {(suggestion.suggested_price * suggestion.quantity)?.toLocaleString()}원
                </span>
              </div>

              {/* 승인/거부 버튼 (대기중일 때만) */}
              {suggestion.status === 'pending' && (
                <div className="flex gap-2">
                  <button
                    onClick={() => handleApprove(suggestion.id, suggestion.stock_name, activeTab === 'sell')}
                    disabled={approveBuyMutation.isLoading || approveSellMutation.isLoading}
                    className={`flex-1 flex items-center justify-center gap-2 text-white py-2 rounded-lg font-medium hover:opacity-90 disabled:opacity-50 transition-colors ${
                      activeTab === 'buy' ? 'bg-red-500' : 'bg-blue-500'
                    }`}
                  >
                    <Check size={18} />
                    {activeTab === 'buy' ? '매수 승인' : '매도 승인'}
                  </button>
                  <button
                    onClick={() => handleReject(suggestion.id, suggestion.stock_name, activeTab === 'sell')}
                    disabled={rejectBuyMutation.isLoading || rejectSellMutation.isLoading}
                    className="flex-1 flex items-center justify-center gap-2 bg-gray-500 text-white py-2 rounded-lg font-medium hover:bg-gray-600 disabled:opacity-50 transition-colors"
                  >
                    <X size={18} />
                    거부
                  </button>
                </div>
              )}
            </div>
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

      {/* 안내 */}
      <div className={`rounded-xl p-4 border ${
        activeTab === 'buy' ? 'bg-blue-50 border-blue-200' : 'bg-orange-50 border-orange-200'
      }`}>
        <div className="flex items-start gap-2">
          {activeTab === 'buy' ? (
            <TrendingUp size={18} className="text-blue-600 mt-0.5" />
          ) : (
            <TrendingDown size={18} className="text-orange-600 mt-0.5" />
          )}
          <div className={`text-sm ${activeTab === 'buy' ? 'text-blue-700' : 'text-orange-700'}`}>
            <p className="font-medium mb-1">
              {activeTab === 'buy' ? '매수 제안 안내' : '매도 제안 안내'}
            </p>
            <ul className={`space-y-1 ${activeTab === 'buy' ? 'text-blue-600' : 'text-orange-600'}`}>
              {activeTab === 'buy' ? (
                <>
                  <li>• AI 점수가 높을수록 좋은 매수 기회입니다</li>
                  <li>• 승인 시 지정 가격으로 매수 주문이 실행됩니다</li>
                  <li>• 제안은 당일 장 종료 시 자동 만료됩니다</li>
                </>
              ) : (
                <>
                  <li>• 익절/손절 조건 충족 시 매도 제안이 생성됩니다</li>
                  <li>• 승인 시 시장가로 매도 주문이 실행됩니다</li>
                  <li>• 보유 종목의 수익률을 확인 후 결정하세요</li>
                </>
              )}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
