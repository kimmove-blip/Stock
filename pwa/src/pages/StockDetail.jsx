import { useState } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { stockAPI, portfolioAPI, watchlistAPI } from '../api/client';
import Loading from '../components/Loading';
import { ArrowLeft, Star, Plus, TrendingUp, TrendingDown } from 'lucide-react';

export default function StockDetail() {
  const { code } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();

  // 보유종목 추가 모달 상태
  const [showAddModal, setShowAddModal] = useState(false);
  const [buyPrice, setBuyPrice] = useState('');
  const [quantity, setQuantity] = useState('1');

  // RealtimePicks에서 전달된 데이터 (있으면 사용)
  const top100Score = location.state?.top100Score;
  const preloadedData = location.state?.preloadedData;

  // 상세 정보 조회 (preloadedData 있으면 스킵 가능)
  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ['stock', code],
    queryFn: () => stockAPI.detail(code).then((res) => res.data),
    // preloadedData가 있으면 초기값으로 사용
    initialData: preloadedData ? {
      code: preloadedData.code,
      name: preloadedData.name,
      current_price: preloadedData.current_price,
      change: preloadedData.change,
      change_rate: preloadedData.change_rate,
      volume: preloadedData.volume,
    } : undefined,
    // preloadedData가 있으면 백그라운드에서 갱신
    staleTime: preloadedData ? 60000 : 0,
  });

  const { data: analysis, isLoading: analysisLoading } = useQuery({
    queryKey: ['stock-analysis', code],
    queryFn: () => stockAPI.analysis(code).then((res) => res.data),
    enabled: !!detail,
    // preloadedData의 score가 있으면 초기값 사용
    initialData: preloadedData?.score ? {
      code: preloadedData.code,
      name: preloadedData.name,
      score: preloadedData.score,
      opinion: preloadedData.score >= 70 ? '매수' : preloadedData.score >= 50 ? '관망' : '주의',
      signals: preloadedData.signals || [],
      comment: '',
    } : undefined,
    staleTime: preloadedData?.score ? 60000 : 0,
  });

  const addToPortfolioMutation = useMutation({
    mutationFn: (data) =>
      portfolioAPI.add({
        stock_code: code,
        stock_name: detail?.name || '',
        buy_price: data.buyPrice,
        quantity: data.quantity,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries(['portfolio']);
      setShowAddModal(false);
      setBuyPrice('');
      setQuantity('1');
      alert('보유종목에 추가되었습니다');
    },
    onError: (error) => {
      alert(error.response?.data?.detail || '추가에 실패했습니다');
    },
  });

  // 모달 열기 (현재가를 기본 매수가로 설정)
  const handleOpenAddModal = () => {
    setBuyPrice(detail?.current_price?.toString() || '');
    setQuantity('1');
    setShowAddModal(true);
  };

  // 보유종목 추가 제출
  const handleAddToPortfolio = () => {
    const price = parseInt(buyPrice) || 0;
    const qty = parseInt(quantity) || 1;

    if (price <= 0) {
      alert('매수가를 입력해주세요');
      return;
    }

    addToPortfolioMutation.mutate({ buyPrice: price, quantity: qty });
  };

  const addToWatchlistMutation = useMutation({
    mutationFn: () =>
      watchlistAPI.add({
        stock_code: code,
        stock_name: detail?.name || '',
        category: '기본',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries(['watchlist']);
      alert('관심종목에 추가되었습니다');
    },
    onError: (error) => {
      alert(error.response?.data?.detail || '추가에 실패했습니다');
    },
  });

  if (detailLoading) return <Loading text="종목 정보 불러오는 중..." />;

  if (!detail) {
    return (
      <div className="alert alert-error">
        <span>종목을 찾을 수 없습니다</span>
      </div>
    );
  }

  const isPositive = (detail.change_rate || 0) >= 0;

  return (
    <div>
      {/* 헤더 */}
      <div className="flex items-center gap-3 mb-4">
        <button onClick={() => navigate(-1)} className="btn btn-ghost btn-sm">
          <ArrowLeft size={20} />
        </button>
        <div className="flex-1">
          <h1 className="text-xl font-bold">{detail.name}</h1>
          <p className="text-sm text-base-content/60">{detail.code} | {detail.market}</p>
        </div>
      </div>

      {/* 가격 정보 */}
      <div className="card bg-base-100 shadow mb-4">
        <div className="card-body p-4">
          <div className="flex justify-between items-end">
            <div>
              <p className="text-3xl font-bold">{detail.current_price?.toLocaleString()}원</p>
              <p className={`flex items-center ${isPositive ? 'text-error' : 'text-info'}`}>
                {isPositive ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
                <span className="ml-1">
                  {isPositive ? '+' : ''}{detail.change?.toLocaleString()}원
                  ({isPositive ? '+' : ''}{detail.change_rate}%)
                </span>
              </p>
            </div>
          </div>

          {/* 액션 버튼 */}
          <div className="flex gap-2 mt-4">
            <button
              onClick={handleOpenAddModal}
              className="btn btn-primary btn-sm flex-1"
            >
              <Plus size={16} /> 보유종목
            </button>
            <button
              onClick={() => addToWatchlistMutation.mutate()}
              className="btn btn-outline btn-sm flex-1"
              disabled={addToWatchlistMutation.isPending}
            >
              <Star size={16} /> 관심종목
            </button>
          </div>
        </div>
      </div>

      {/* 기술적 지표 */}
      <div className="card bg-base-100 shadow mb-4">
        <div className="card-body p-4">
          <h3 className="font-bold mb-3">기술적 지표</h3>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="flex justify-between">
              <span className="text-base-content/60">거래량</span>
              <span>{detail.volume?.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-base-content/60">시가총액</span>
              <span>{detail.market_cap ? `${Math.round(detail.market_cap / 100000000).toLocaleString()}억` : '-'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-base-content/60">5일 이평</span>
              <span>{detail.ma5?.toLocaleString() || '-'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-base-content/60">20일 이평</span>
              <span>{detail.ma20?.toLocaleString() || '-'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-base-content/60">60일 이평</span>
              <span>{detail.ma60?.toLocaleString() || '-'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-base-content/60">RSI</span>
              <span className={
                detail.rsi > 70 ? 'text-error' :
                detail.rsi < 30 ? 'text-info' : ''
              }>
                {detail.rsi?.toFixed(1) || '-'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* AI 분석 */}
      {analysisLoading ? (
        <Loading text="AI 분석 중..." />
      ) : analysis && (
        <div className="card bg-base-100 shadow">
          <div className="card-body p-4">
            <div className="flex justify-between items-center mb-3">
              <h3 className="font-bold">AI 분석</h3>
              <div className="badge badge-primary badge-lg">{top100Score ?? analysis.score}점</div>
            </div>

            <div className="flex items-center gap-2 mb-3">
              <span className="text-base-content/60">투자 의견:</span>
              <span className={`badge ${
                analysis.opinion === '매수' ? 'badge-success' :
                analysis.opinion === '매도' ? 'badge-error' :
                'badge-ghost'
              }`}>
                {analysis.opinion}
              </span>
            </div>

            {analysis.comment && (
              <div className="bg-base-200 p-3 rounded space-y-1">
                {analysis.comment.split('\n').map((line, idx) => (
                  <p key={idx} className="text-sm text-base-content/80">
                    {line}
                  </p>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 보유종목 추가 모달 */}
      {showAddModal && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">보유종목 추가</h3>

            <div className="mt-4 p-3 bg-base-200 rounded">
              <p className="font-bold">{detail?.name}</p>
              <p className="text-sm text-base-content/60">{detail?.code}</p>
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
                  setBuyPrice('');
                  setQuantity('1');
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
