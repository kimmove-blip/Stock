import { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { stockAPI, portfolioAPI, watchlistAPI, realtimeAPI } from '../api/client';
import Loading from '../components/Loading';
import { ArrowLeft, Star, Plus, TrendingUp, TrendingDown, FileText, Check, RefreshCw, Share2 } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

export default function StockDetail() {
  const { code } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();

  // 보유종목 추가 모달 상태
  const [showAddModal, setShowAddModal] = useState(false);
  const [buyPrice, setBuyPrice] = useState('');
  const [quantity, setQuantity] = useState('1');

  // 페이지 진입 시 스크롤 맨 위로
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [code]);

  // RealtimePicks에서 전달된 데이터 (있으면 사용)
  const top100Score = location.state?.top100Score;
  const preloadedData = location.state?.preloadedData;

  // 상세 정보 조회 (2분 캐시) - 기술적 지표용
  const { data: detailBase, isLoading: detailLoading } = useQuery({
    queryKey: ['stock', code],
    queryFn: () => stockAPI.detail(code).then((res) => res.data),
    // preloadedData가 있으면 초기값으로 사용 (기본 정보만) - 즉시 stale 처리
    initialData: preloadedData ? {
      code: preloadedData.code,
      name: preloadedData.name,
      current_price: preloadedData.current_price,
      change: preloadedData.change,
      change_rate: preloadedData.change_rate,
      volume: preloadedData.volume,
    } : undefined,
    initialDataUpdatedAt: 0,  // initialData를 즉시 stale로 처리하여 전체 데이터 가져오기
    staleTime: 1000 * 60 * 2,  // 2분 캐시 (API에서 받은 데이터)
    refetchOnWindowFocus: false,
  });

  // 실시간 시세 조회 - 항상 활성화
  const { data: realtimePrice, refetch: refetchPrice, isFetching: isPriceFetching } = useQuery({
    queryKey: ['realtime-price', code],
    queryFn: () => realtimeAPI.price(code).then((res) => res.data),
    staleTime: 1000 * 30,  // 30초 캐시
    refetchOnWindowFocus: false,
  });

  // 상세 정보 + 실시간 가격 병합
  const detail = detailBase ? {
    ...detailBase,
    current_price: realtimePrice?.current_price ?? detailBase.current_price,
    change: realtimePrice?.change ?? detailBase.change,
    change_rate: realtimePrice?.change_rate ?? detailBase.change_rate,
    volume: realtimePrice?.volume ?? detailBase.volume,
  } : null;

  const { data: analysis, isLoading: analysisLoading } = useQuery({
    queryKey: ['stock-analysis', code],
    queryFn: () => stockAPI.analysis(code).then((res) => res.data),
    enabled: !!detail,
    // preloadedData의 score가 있으면 초기값 사용 (점수만) - 즉시 stale 처리
    initialData: preloadedData?.score ? {
      code: preloadedData.code,
      name: preloadedData.name,
      score: preloadedData.score,
      opinion: preloadedData.score >= 70 ? '매수' : preloadedData.score >= 50 ? '관망' : '주의',
      signals: preloadedData.signals || [],
      comment: '',
    } : undefined,
    initialDataUpdatedAt: 0,  // initialData를 즉시 stale로 처리하여 항상 API 호출
    staleTime: 1000 * 60 * 5,  // 5분 캐시 (API에서 받은 데이터)
    refetchOnWindowFocus: false,
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

  // 펀더멘탈 분석 데이터
  const { data: fundamental, isLoading: fundamentalLoading } = useQuery({
    queryKey: ['fundamental', code],
    queryFn: () => stockAPI.fundamental(code).then((res) => res.data),
    enabled: !!detail,
    staleTime: 1000 * 60 * 30, // 30분 캐시
    retry: 1,
  });

  // 보유/관심 여부 확인
  const portfolioItem = portfolio?.items?.find((item) => item.stock_code === code);
  const isInPortfolio = !!portfolioItem;
  const isInWatchlist = watchlist?.items?.some((item) => item.stock_code === code);

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

  // 공유 기능
  const handleShare = async () => {
    const stockName = detail?.name || '';
    const stockCode = detail?.code || code;
    const currentPrice = detail?.current_price?.toLocaleString() || '-';
    const changeRate = detail?.change_rate || 0;
    const changeSign = changeRate >= 0 ? '+' : '';
    const score = analysis?.score || top100Score || 0;
    const opinion = analysis?.opinion || (score >= 70 ? '매수' : score >= 50 ? '관망' : '');

    // 공유 내용 생성
    let shareText = `📊 ${stockName} (${stockCode})\n💰 현재가: ${currentPrice}원 (${changeSign}${changeRate}%)`;
    if (score > 0) {
      shareText += `\n🎯 AI 점수: ${score}점${opinion ? ` (${opinion})` : ''}`;
    }
    shareText += `\n\n📱 앱 다운로드:\n▶ Android: https://play.google.com/store/apps/details?id=com.kimsai.stock\n▶ iOS: 앱스토어 출시 준비중\n\nKim's AI 주식분석`;

    const shareTitle = `[${stockName}] AI 점수 ${score > 0 ? score + '점' : '-'}`;

    // Web Share API 지원 확인
    if (navigator.share) {
      try {
        await navigator.share({
          title: shareTitle,
          text: shareText,
        });
      } catch (err) {
        // 사용자가 공유 취소한 경우 무시
        if (err.name !== 'AbortError') {
          console.error('공유 실패:', err);
        }
      }
    } else {
      // 폴백: 클립보드 복사
      try {
        await navigator.clipboard.writeText(shareText);
        alert('클립보드에 복사되었습니다!');
      } catch (err) {
        console.error('클립보드 복사 실패:', err);
        alert('공유 기능을 사용할 수 없습니다.');
      }
    }
  };

  if (detailLoading) return <Loading text="종목 정보 불러오는 중..." />;

  if (!detail) {
    return (
      <div className="alert alert-error">
        <span>종목을 찾을 수 없습니다</span>
      </div>
    );
  }

  const isPositive = (detail.change_rate || 0) >= 0;

  // AI 점수 (analysis 또는 top100Score에서)
  const aiScore = analysis?.score || top100Score || 0;

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
        {/* AI 점수 */}
        {aiScore > 0 && (
          <div className="text-center">
            <div className={`text-3xl font-bold ${
              aiScore >= 80 ? 'text-success' :
              aiScore >= 60 ? 'text-warning' : 'text-error'
            }`}>
              {aiScore}
            </div>
            <div className="text-xs text-base-content/60">AI점수</div>
          </div>
        )}
        {/* 공유 버튼 */}
        <button onClick={handleShare} className="btn btn-ghost btn-sm">
          <Share2 size={20} />
        </button>
      </div>

      {/* 가격 정보 */}
      <div className="card bg-base-100 shadow mb-4">
        <div className="card-body p-4">
          <div className="flex justify-between items-end">
            <div>
              <div className="flex items-center gap-2">
                <p className="text-3xl font-bold">{detail.current_price?.toLocaleString()}원</p>
                <button
                  onClick={() => refetchPrice()}
                  disabled={isPriceFetching}
                  className="btn btn-ghost btn-xs"
                  title="실시간 시세 갱신"
                >
                  <RefreshCw size={14} className={isPriceFetching ? 'animate-spin' : ''} />
                </button>
              </div>
              <p className={`flex items-center ${isPositive ? 'text-error' : 'text-info'}`}>
                {isPositive ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
                <span className="ml-1">
                  {isPositive ? '+' : ''}{detail.change?.toLocaleString()}원
                  ({isPositive ? '+' : ''}{detail.change_rate}%)
                </span>
              </p>
            </div>
            {/* 추천 매수가 표시 (점수 50 초과시만) */}
            {aiScore > 50 && (
              <div className="text-right">
                <div className="text-xs text-base-content/50">추천 매수가</div>
                {detail.bb_mid ? (
                  <div className="text-lg font-bold text-primary">
                    {Math.round(detail.bb_mid).toLocaleString()}원
                  </div>
                ) : (
                  <div className="flex items-center justify-end gap-1 text-base-content/40 py-1">
                    <RefreshCw size={14} className="animate-spin" />
                    <span className="text-xs">분석중</span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 액션 버튼 */}
          <div className="flex flex-col gap-2 mt-4">
            {isInPortfolio ? (
              <div className="bg-blue-50 rounded-lg p-3 border border-blue-200">
                <div className="flex items-center gap-1 text-blue-600 font-medium text-sm mb-1">
                  <Check size={14} /> 보유중
                </div>
                <div className="text-xs text-base-content/70">
                  매수가 {portfolioItem.buy_price?.toLocaleString()}원 · {portfolioItem.quantity}주
                </div>
                <div className={`text-sm font-medium ${portfolioItem.profit_loss_rate >= 0 ? 'text-red-500' : 'text-blue-500'}`}>
                  {portfolioItem.profit_loss >= 0 ? '+' : ''}{portfolioItem.profit_loss?.toLocaleString()}원
                  ({portfolioItem.profit_loss_rate >= 0 ? '+' : ''}{portfolioItem.profit_loss_rate?.toFixed(2)}%)
                </div>
              </div>
            ) : (
              <button
                onClick={handleOpenAddModal}
                className="btn btn-primary btn-sm flex-1"
              >
                <Plus size={16} /> 보유종목
              </button>
            )}
            {isInWatchlist ? (
              <button disabled className="btn btn-ghost btn-sm flex-1 text-yellow-500">
                <Star size={16} /> 관심중
              </button>
            ) : (
              <button
                onClick={() => addToWatchlistMutation.mutate()}
                className="btn btn-outline btn-sm flex-1"
                disabled={addToWatchlistMutation.isPending}
              >
                <Star size={16} /> 관심종목
              </button>
            )}
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
        <div className="card bg-base-100 shadow mb-4">
          <div className="card-body p-4">
            <div className="flex justify-between items-center mb-3">
              <h3 className="font-bold">AI 분석</h3>
              <span className={`badge ${
                analysis.opinion === '매수' ? 'badge-success' :
                analysis.opinion === '과열 주의' ? 'badge-error' :
                analysis.opinion === '주의' ? 'badge-warning' :
                'badge-ghost'
              }`}>
                {analysis.opinion}
              </span>
            </div>

            {/* 상승확률 & 신뢰도 */}
            <div className="grid grid-cols-2 gap-3 mb-4">
              <div className="bg-base-200 p-3 rounded text-center">
                <p className="text-xs text-base-content/60 mb-1">상승 확률</p>
                <p className={`text-2xl font-bold ${
                  (analysis.probability || 50) >= 60 ? 'text-success' :
                  (analysis.probability || 50) <= 40 ? 'text-error' : ''
                }`}>
                  {analysis.probability?.toFixed(1) || '50.0'}%
                </p>
              </div>
              <div className="bg-base-200 p-3 rounded text-center">
                <p className="text-xs text-base-content/60 mb-1">신뢰도</p>
                <p className="text-2xl font-bold">
                  {analysis.confidence?.toFixed(1) || '50.0'}%
                </p>
                <div className="w-full bg-base-300 rounded-full h-1.5 mt-1">
                  <div
                    className={`h-1.5 rounded-full ${
                      (analysis.confidence || 50) >= 70 ? 'bg-success' :
                      (analysis.confidence || 50) >= 50 ? 'bg-warning' : 'bg-error'
                    }`}
                    style={{ width: `${analysis.confidence || 50}%` }}
                  ></div>
                </div>
              </div>
            </div>

            {/* 신호 불릿 리스트 */}
            {analysis.signal_descriptions?.length > 0 && (
              <div className="mb-3">
                <div className="space-y-1">
                  {analysis.signal_descriptions.map((desc, idx) => (
                    <p key={idx} className="text-sm">{desc}</p>
                  ))}
                </div>
              </div>
            )}

            {/* AI 코멘트 */}
            {analysis.comment && (
              <div className="bg-base-200 p-3 rounded">
                <p className="text-sm text-base-content/80 leading-relaxed">
                  {analysis.comment}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 20일 가격 추이 차트 */}
      {analysis?.price_history?.length > 0 && (
        <div className="card bg-base-100 shadow mb-4">
          <div className="card-body p-4">
            <h3 className="font-bold mb-3">20일 추이</h3>
            <div className="h-40">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={analysis.price_history}>
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10 }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis
                    domain={['auto', 'auto']}
                    hide
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'var(--fallback-b1,oklch(var(--b1)))',
                      border: '1px solid var(--fallback-b3,oklch(var(--b3)))',
                      borderRadius: '8px',
                      fontSize: '12px'
                    }}
                    formatter={(value, name) => {
                      const labels = { close: '종가', ma5: '5일선', ma20: '20일선' };
                      return [value?.toLocaleString() + '원', labels[name] || name];
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="close"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="ma5"
                    stroke="#f59e0b"
                    strokeWidth={1}
                    dot={false}
                    strokeDasharray="3 3"
                  />
                  <Line
                    type="monotone"
                    dataKey="ma20"
                    stroke="#ef4444"
                    strokeWidth={1}
                    dot={false}
                    strokeDasharray="3 3"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="flex gap-4 text-xs justify-center mt-2">
              <span className="flex items-center gap-1">
                <span className="w-3 h-0.5 bg-blue-500 inline-block"></span> 종가
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-0.5 bg-amber-500 inline-block"></span> 5일선
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-0.5 bg-red-500 inline-block"></span> 20일선
              </span>
            </div>
          </div>
        </div>
      )}

      {/* 지지/저항선 */}
      {analysis?.support_resistance && (
        <div className="card bg-base-100 shadow mb-4">
          <div className="card-body p-4">
            <h3 className="font-bold mb-3">지지/저항선</h3>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-xs text-base-content/60 mb-2">저항선</p>
                <div className="space-y-1">
                  <div className="flex justify-between">
                    <span className="text-error">2차</span>
                    <span className="font-medium">{analysis.support_resistance.resistance_2?.toLocaleString()}원</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-error">1차</span>
                    <span className="font-medium">{analysis.support_resistance.resistance_1?.toLocaleString()}원</span>
                  </div>
                </div>
              </div>
              <div>
                <p className="text-xs text-base-content/60 mb-2">지지선</p>
                <div className="space-y-1">
                  <div className="flex justify-between">
                    <span className="text-info">1차</span>
                    <span className="font-medium">{analysis.support_resistance.support_1?.toLocaleString()}원</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-info">2차</span>
                    <span className="font-medium">{analysis.support_resistance.support_2?.toLocaleString()}원</span>
                  </div>
                </div>
              </div>
            </div>
            <div className="divider my-2"></div>
            <div className="flex justify-between text-xs text-base-content/60">
              <span>20일 저점: {analysis.support_resistance.recent_low?.toLocaleString()}원</span>
              <span>20일 고점: {analysis.support_resistance.recent_high?.toLocaleString()}원</span>
            </div>
          </div>
        </div>
      )}

      {/* 펀더멘탈 분석 */}
      {fundamentalLoading ? (
        <Loading text="펀더멘탈 분석 중..." />
      ) : fundamental && (
        <div className="card bg-base-100 shadow mb-4">
          <div className="card-body p-4">
            <h3 className="font-bold mb-3 flex items-center gap-2">
              <FileText size={18} /> 펀더멘탈 분석
            </h3>

            {/* 점수 게이지 바 */}
            <div className="flex items-center gap-2 mb-4">
              <span className="text-xs text-base-content/60">낮음</span>
              <div className="flex-1 h-2 bg-base-200 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all ${
                    fundamental.level === '높음' ? 'bg-success' :
                    fundamental.level === '보통' ? 'bg-warning' : 'bg-error'
                  }`}
                  style={{ width: `${fundamental.score}%` }}
                />
              </div>
              <span className="text-xs text-base-content/60">높음</span>
              <span className={`text-sm font-bold ml-1 ${
                fundamental.level === '높음' ? 'text-success' :
                fundamental.level === '보통' ? 'text-warning' : 'text-error'
              }`}>{fundamental.level}</span>
            </div>

            {/* 주요 비율 */}
            <div className="grid grid-cols-4 gap-2 mb-4">
              <div className="bg-base-200 rounded p-2 text-center">
                <p className="text-xs text-base-content/60">ROE</p>
                <p className={`font-semibold text-sm ${
                  fundamental.roe && fundamental.roe >= 10 ? 'text-success' :
                  fundamental.roe && fundamental.roe < 0 ? 'text-error' : ''
                }`}>
                  {fundamental.roe != null ? `${fundamental.roe.toFixed(1)}%` : '-'}
                </p>
              </div>
              <div className="bg-base-200 rounded p-2 text-center">
                <p className="text-xs text-base-content/60">부채비율</p>
                <p className={`font-semibold text-sm ${
                  fundamental.debt_ratio && fundamental.debt_ratio < 100 ? 'text-success' :
                  fundamental.debt_ratio && fundamental.debt_ratio > 200 ? 'text-error' : ''
                }`}>
                  {fundamental.debt_ratio != null ? `${fundamental.debt_ratio.toFixed(0)}%` : '-'}
                </p>
              </div>
              <div className="bg-base-200 rounded p-2 text-center">
                <p className="text-xs text-base-content/60">유동비율</p>
                <p className={`font-semibold text-sm ${
                  fundamental.liquidity_ratio && fundamental.liquidity_ratio >= 150 ? 'text-success' :
                  fundamental.liquidity_ratio && fundamental.liquidity_ratio < 100 ? 'text-error' : ''
                }`}>
                  {fundamental.liquidity_ratio != null ? `${fundamental.liquidity_ratio.toFixed(0)}%` : '-'}
                </p>
              </div>
              <div className="bg-base-200 rounded p-2 text-center">
                <p className="text-xs text-base-content/60">영업이익률</p>
                <p className={`font-semibold text-sm ${
                  fundamental.operating_margin && fundamental.operating_margin >= 10 ? 'text-success' :
                  fundamental.operating_margin && fundamental.operating_margin < 0 ? 'text-error' : ''
                }`}>
                  {fundamental.operating_margin != null ? `${fundamental.operating_margin.toFixed(1)}%` : '-'}
                </p>
              </div>
            </div>

            {/* 연도별 실적 */}
            {fundamental.financials?.length > 0 && (
              <div className="overflow-x-auto mb-4">
                <table className="table table-xs w-full">
                  <thead>
                    <tr className="text-base-content/60">
                      <th className="text-left">연도</th>
                      <th className="text-right">매출액</th>
                      <th className="text-right">영업이익</th>
                      <th className="text-right">순이익</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fundamental.financials.map((f) => (
                      <tr key={f.year}>
                        <td>{f.year}</td>
                        <td className="text-right">
                          {f.revenue != null ? `${f.revenue.toLocaleString()}억` : '-'}
                          {f.revenue_yoy != null && (
                            <span className={`text-xs ml-1 ${f.revenue_yoy >= 0 ? 'text-success' : 'text-error'}`}>
                              ({f.revenue_yoy >= 0 ? '+' : ''}{f.revenue_yoy.toFixed(1)}%)
                            </span>
                          )}
                        </td>
                        <td className="text-right">
                          {f.operating_income != null ? `${f.operating_income.toLocaleString()}억` : '-'}
                        </td>
                        <td className="text-right">
                          {f.net_income != null ? `${f.net_income.toLocaleString()}억` : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* AI 코멘트 */}
            {fundamental.comment && (
              <div className="bg-info/10 p-3 rounded">
                <p className="text-sm text-base-content/80 leading-relaxed">
                  {fundamental.comment}
                </p>
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
