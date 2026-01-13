import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { stockAPI, portfolioAPI, watchlistAPI } from '../api/client';
import Loading from '../components/Loading';
import { ArrowLeft, Star, Plus, TrendingUp, TrendingDown } from 'lucide-react';

export default function StockDetail() {
  const { code } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ['stock', code],
    queryFn: () => stockAPI.detail(code).then((res) => res.data),
  });

  const { data: analysis, isLoading: analysisLoading } = useQuery({
    queryKey: ['stock-analysis', code],
    queryFn: () => stockAPI.analysis(code).then((res) => res.data),
    enabled: !!detail,
  });

  const addToPortfolioMutation = useMutation({
    mutationFn: () =>
      portfolioAPI.add({
        stock_code: code,
        stock_name: detail?.name || '',
        buy_price: detail?.current_price || 0,
        quantity: 1,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries(['portfolio']);
      alert('보유종목에 추가되었습니다');
    },
  });

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
              onClick={() => addToPortfolioMutation.mutate()}
              className="btn btn-primary btn-sm flex-1"
              disabled={addToPortfolioMutation.isPending}
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
              <div className="badge badge-primary badge-lg">{analysis.score}점</div>
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
    </div>
  );
}
