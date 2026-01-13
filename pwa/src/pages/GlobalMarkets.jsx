import { useQuery } from '@tanstack/react-query';
import { Globe, TrendingUp, TrendingDown, RefreshCw, AlertCircle } from 'lucide-react';
import { marketAPI } from '../api/client';

export default function GlobalMarkets() {
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['market-global'],
    queryFn: () => marketAPI.global().then((res) => res.data),
    staleTime: 5 * 60 * 1000, // 5분 캐시
  });

  return (
    <div className="max-w-md mx-auto">
      {/* 헤더 */}
      <div className="bg-gradient-to-r from-pink-500 to-rose-500 -mx-4 -mt-4 px-4 py-6 mb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center">
              <Globe size={28} className="text-white" />
            </div>
            <div className="text-white">
              <h1 className="text-xl font-bold">해외주식 현황</h1>
              <p className="text-sm opacity-80">글로벌 시장 지수</p>
            </div>
          </div>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="p-2 bg-white/20 rounded-lg hover:bg-white/30 transition-colors"
          >
            <RefreshCw size={20} className={`text-white ${isFetching ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* 에러 상태 */}
      {error && (
        <div className="bg-red-50 rounded-xl p-4 mb-4 flex items-center gap-3">
          <AlertCircle className="text-red-500" size={20} />
          <div>
            <p className="text-red-700 font-medium">데이터를 불러올 수 없습니다</p>
            <p className="text-red-500 text-sm">{error.response?.data?.detail || error.message}</p>
          </div>
        </div>
      )}

      {/* 로딩 상태 */}
      {isLoading ? (
        <div className="space-y-3 mb-6">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="bg-white rounded-xl p-4 shadow-sm animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-1/3 mb-2"></div>
              <div className="h-6 bg-gray-200 rounded w-1/2"></div>
            </div>
          ))}
        </div>
      ) : (
        <>
          {/* 주요 지수 */}
          <div className="space-y-3 mb-6">
            {data?.indices?.map((index) => (
              <div key={index.symbol} className="bg-white rounded-xl p-4 shadow-sm">
                <div className="flex justify-between items-center">
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="font-semibold text-gray-800">{index.name}</p>
                      <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded">
                        {index.country}
                      </span>
                    </div>
                    <p className="text-lg font-bold text-gray-800 mt-1">
                      {index.value.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </p>
                  </div>
                  <div className={`text-right ${index.positive ? 'text-red-500' : 'text-blue-500'}`}>
                    <div className="flex items-center gap-1 justify-end">
                      {index.positive ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
                      <span className="font-semibold">
                        {index.positive ? '+' : ''}
                        {index.change_rate.toFixed(2)}%
                      </span>
                    </div>
                    <p className="text-sm">
                      {index.positive ? '+' : ''}
                      {index.change.toFixed(2)}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* 환율 */}
          {data?.currencies?.length > 0 && (
            <div className="bg-white rounded-xl p-4 shadow-sm">
              <h3 className="font-semibold text-gray-800 mb-4">환율</h3>
              <div className="space-y-3">
                {data.currencies.map((curr) => (
                  <div key={curr.symbol} className="flex justify-between items-center">
                    <span className="text-gray-600">{curr.name}</span>
                    <div className="text-right">
                      <span className="font-semibold text-gray-800">
                        {curr.value.toLocaleString('ko-KR', { minimumFractionDigits: 2 })}
                      </span>
                      <span
                        className={`ml-2 text-sm ${curr.positive ? 'text-red-500' : 'text-blue-500'}`}
                      >
                        {curr.positive ? '+' : ''}
                        {curr.change.toFixed(2)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* 마지막 업데이트 시간 */}
      {data?.updated_at && (
        <p className="text-center text-xs text-gray-400 py-4">
          마지막 업데이트: {new Date(data.updated_at).toLocaleTimeString('ko-KR')}
        </p>
      )}
    </div>
  );
}
