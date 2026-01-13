import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { top100API } from '../api/client';
import StockCard from '../components/StockCard';
import Loading from '../components/Loading';
import { RefreshCw, Calendar } from 'lucide-react';

export default function Top100() {
  const navigate = useNavigate();
  const [selectedDate, setSelectedDate] = useState('');

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['top100', selectedDate],
    queryFn: () => top100API.list(selectedDate).then((res) => res.data),
    staleTime: 1000 * 60 * 5, // 5분
  });

  if (isLoading) return <Loading text="AI 추천 종목 불러오는 중..." />;

  if (error) {
    return (
      <div className="alert alert-error">
        <span>데이터를 불러올 수 없습니다</span>
      </div>
    );
  }

  return (
    <div>
      {/* 헤더 */}
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="text-xl font-bold">AI 추천 TOP 100</h2>
          <p className="text-sm text-base-content/60">
            {data?.date?.replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3')} 기준
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => refetch()}
            className="btn btn-ghost btn-sm"
            disabled={isFetching}
          >
            <RefreshCw size={18} className={isFetching ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* 통계 */}
      <div className="stats stats-horizontal shadow w-full mb-4">
        <div className="stat place-items-center py-2">
          <div className="stat-title text-xs">종목 수</div>
          <div className="stat-value text-lg text-primary">{data?.total_count || 0}</div>
        </div>
        <div className="stat place-items-center py-2">
          <div className="stat-title text-xs">평균 점수</div>
          <div className="stat-value text-lg">
            {data?.items?.length > 0
              ? Math.round(
                  data.items.reduce((acc, s) => acc + (s.score || 0), 0) / data.items.length
                )
              : 0}
          </div>
        </div>
      </div>

      {/* 종목 리스트 */}
      <div className="space-y-3">
        {data?.items?.map((stock) => (
          <div key={stock.code} className="relative">
            <div className="absolute -left-2 top-1/2 -translate-y-1/2 bg-primary text-primary-content text-xs font-bold w-6 h-6 rounded-full flex items-center justify-center">
              {stock.rank}
            </div>
            <div className="ml-4">
              <StockCard
                stock={stock}
                onClick={() => navigate(`/stock/${stock.code}`)}
              />
            </div>
          </div>
        ))}
      </div>

      {data?.items?.length === 0 && (
        <div className="text-center py-10 text-base-content/60">
          오늘의 추천 종목이 없습니다
        </div>
      )}
    </div>
  );
}
