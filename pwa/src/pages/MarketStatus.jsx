import { useQuery } from '@tanstack/react-query';
import { BarChart3, Globe, TrendingUp, TrendingDown, RefreshCw, AlertCircle } from 'lucide-react';
import { marketAPI } from '../api/client';

export default function MarketStatus() {
  // 국내 시장 데이터
  const { data: domesticData, isLoading: domesticLoading, error: domesticError, refetch: refetchDomestic, isFetching: domesticFetching } = useQuery({
    queryKey: ['market-domestic'],
    queryFn: () => marketAPI.domestic().then((res) => res.data),
    staleTime: 60 * 1000,
    refetchInterval: 60 * 1000,
  });

  // 해외 시장 데이터
  const { data: globalData, isLoading: globalLoading, refetch: refetchGlobal, isFetching: globalFetching } = useQuery({
    queryKey: ['market-global'],
    queryFn: () => marketAPI.global().then((res) => res.data),
    staleTime: 5 * 60 * 1000,
  });

  const handleRefresh = () => {
    refetchDomestic();
    refetchGlobal();
  };

  const isFetching = domesticFetching || globalFetching;
  const isLoading = domesticLoading || globalLoading;

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

  const marketStatus = domesticData?.market_status ? getStatusText(domesticData.market_status) : null;

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
              <h1 className="text-xl font-bold">국내외증시</h1>
              <p className="text-sm opacity-80">국내 · 해외 시장 현황</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {marketStatus && (
              <span className={`px-2 py-1 rounded-full text-xs text-white ${marketStatus.color}`}>
                {marketStatus.text}
              </span>
            )}
            <button
              onClick={handleRefresh}
              disabled={isFetching}
              className="p-2 bg-white/20 rounded-lg hover:bg-white/30 transition-colors"
            >
              <RefreshCw size={20} className={`text-white ${isFetching ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </div>

      {/* 에러 상태 */}
      {domesticError && (
        <div className="bg-red-50 rounded-xl p-4 mb-4 flex items-center gap-3">
          <AlertCircle className="text-red-500" size={20} />
          <div>
            <p className="text-red-700 font-medium">데이터를 불러올 수 없습니다</p>
            <p className="text-red-500 text-sm">{domesticError.response?.data?.detail || domesticError.message}</p>
          </div>
        </div>
      )}

      {/* 로딩 상태 */}
      {isLoading ? (
        <div className="space-y-3 mb-6">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="bg-white rounded-xl p-4 shadow-sm animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-1/4 mb-2"></div>
              <div className="h-8 bg-gray-200 rounded w-1/2"></div>
            </div>
          ))}
        </div>
      ) : (
        <>
          {/* 국내 지수 */}
          <div className="mb-6">
            <div className="flex items-center gap-2 mb-3">
              <BarChart3 size={18} className="text-indigo-500" />
              <h2 className="font-bold text-gray-800">국내 시장</h2>
            </div>
            <div className="space-y-3">
              {domesticData?.indices?.map((index) => (
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
          </div>

          {/* 해외 지수 */}
          <div className="mb-6">
            <div className="flex items-center gap-2 mb-3">
              <Globe size={18} className="text-pink-500" />
              <h2 className="font-bold text-gray-800">해외 시장</h2>
            </div>
            <div className="space-y-3">
              {globalData?.indices?.map((index) => (
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
          </div>

          {/* 환율 */}
          {globalData?.currencies?.length > 0 && (
            <div className="bg-white rounded-xl p-4 shadow-sm mb-6">
              <h3 className="font-semibold text-gray-800 mb-4">환율</h3>
              <div className="space-y-3">
                {globalData.currencies.map((curr) => (
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
      {(domesticData?.updated_at || globalData?.updated_at) && (
        <p className="text-center text-xs text-gray-400 py-4">
          마지막 업데이트: {new Date(domesticData?.updated_at || globalData?.updated_at).toLocaleTimeString('ko-KR')}
        </p>
      )}
    </div>
  );
}
