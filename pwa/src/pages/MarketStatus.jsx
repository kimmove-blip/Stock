import { useQuery } from '@tanstack/react-query';
import { BarChart3, TrendingUp, TrendingDown, RefreshCw, AlertCircle } from 'lucide-react';
import { marketAPI } from '../api/client';

export default function MarketStatus() {
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['market-domestic'],
    queryFn: () => marketAPI.domestic().then((res) => res.data),
    staleTime: 60 * 1000, // 1분 캐시
    refetchInterval: 60 * 1000, // 1분마다 자동 갱신
  });

  const getStatusText = (status) => {
    switch (status) {
      case 'open':
        return { text: '장중', color: 'bg-green-500' };
      case 'pre-market':
        return { text: '장전', color: 'bg-yellow-500' };
      default:
        return { text: '장마감', color: 'bg-gray-500' };
    }
  };

  const marketStatus = data?.market_status ? getStatusText(data.market_status) : null;

  return (
    <div className="max-w-md mx-auto">
      {/* 헤더 */}
      <div className="bg-gradient-to-r from-indigo-500 to-purple-500 -mx-4 -mt-4 px-4 py-6 mb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center">
              <BarChart3 size={28} className="text-white" />
            </div>
            <div className="text-white">
              <h1 className="text-xl font-bold">코스피/코스닥</h1>
              <p className="text-sm opacity-80">국내 시장 현황</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {marketStatus && (
              <span className={`px-2 py-1 rounded-full text-xs text-white ${marketStatus.color}`}>
                {marketStatus.text}
              </span>
            )}
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="p-2 bg-white/20 rounded-lg hover:bg-white/30 transition-colors"
            >
              <RefreshCw size={20} className={`text-white ${isFetching ? 'animate-spin' : ''}`} />
            </button>
          </div>
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
          {[1, 2].map((i) => (
            <div key={i} className="bg-white rounded-xl p-4 shadow-sm animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-1/4 mb-2"></div>
              <div className="h-8 bg-gray-200 rounded w-1/2"></div>
            </div>
          ))}
        </div>
      ) : (
        <>
          {/* 지수 카드 */}
          <div className="space-y-3 mb-6">
            {data?.indices?.map((index) => (
              <div key={index.code} className="bg-white rounded-xl p-4 shadow-sm">
                <div className="flex justify-between items-center">
                  <div>
                    <p className="text-sm text-gray-500">{index.name}</p>
                    <p className="text-2xl font-bold text-gray-800">
                      {index.value.toLocaleString('ko-KR', { minimumFractionDigits: 2 })}
                    </p>
                  </div>
                  <div className={`text-right ${index.positive ? 'text-red-500' : 'text-blue-500'}`}>
                    <div className="flex items-center gap-1 justify-end">
                      {index.positive ? <TrendingUp size={20} /> : <TrendingDown size={20} />}
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
                {index.trading_value && (
                  <div className="mt-2 pt-2 border-t border-gray-100 text-xs text-gray-400">
                    거래대금: {index.trading_value.toLocaleString()}억
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* 시장 정보 */}
          {data?.market_info && (
            <div className="bg-white rounded-xl p-4 shadow-sm">
              <h3 className="font-semibold text-gray-800 mb-4">시장 정보</h3>
              <div className="grid grid-cols-2 gap-4">
                {data.market_info.total_volume && (
                  <div className="flex justify-between">
                    <span className="text-gray-500 text-sm">거래량</span>
                    <span className="font-medium text-gray-800">{data.market_info.total_volume}</span>
                  </div>
                )}
                {data.market_info.total_value && (
                  <div className="flex justify-between">
                    <span className="text-gray-500 text-sm">거래대금</span>
                    <span className="font-medium text-gray-800">{data.market_info.total_value}</span>
                  </div>
                )}
                {data.market_info.advancing !== null && (
                  <div className="flex justify-between">
                    <span className="text-gray-500 text-sm">상승</span>
                    <span className="font-medium text-red-500">{data.market_info.advancing}</span>
                  </div>
                )}
                {data.market_info.declining !== null && (
                  <div className="flex justify-between">
                    <span className="text-gray-500 text-sm">하락</span>
                    <span className="font-medium text-blue-500">{data.market_info.declining}</span>
                  </div>
                )}
                {data.market_info.unchanged !== null && (
                  <div className="flex justify-between">
                    <span className="text-gray-500 text-sm">보합</span>
                    <span className="font-medium text-gray-800">{data.market_info.unchanged}</span>
                  </div>
                )}
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
