import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { popularAPI } from '../api/client';
import { Flame, TrendingUp, TrendingDown, RefreshCw } from 'lucide-react';
import Loading from '../components/Loading';

export default function PopularStocks() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('volume');

  // 거래량 상위
  const { data: volumeData, isLoading: volumeLoading, refetch: refetchVolume } = useQuery({
    queryKey: ['popular-volume'],
    queryFn: () => popularAPI.volume(20).then((res) => res.data),
    enabled: activeTab === 'volume',
  });

  // 상승률 상위
  const { data: gainersData, isLoading: gainersLoading, refetch: refetchGainers } = useQuery({
    queryKey: ['popular-gainers'],
    queryFn: () => popularAPI.gainers(20).then((res) => res.data),
    enabled: activeTab === 'gainers',
  });

  // 하락률 상위
  const { data: losersData, isLoading: losersLoading, refetch: refetchLosers } = useQuery({
    queryKey: ['popular-losers'],
    queryFn: () => popularAPI.losers(20).then((res) => res.data),
    enabled: activeTab === 'losers',
  });

  const isLoading =
    (activeTab === 'volume' && volumeLoading) ||
    (activeTab === 'gainers' && gainersLoading) ||
    (activeTab === 'losers' && losersLoading);

  const getCurrentData = () => {
    switch (activeTab) {
      case 'volume':
        return volumeData;
      case 'gainers':
        return gainersData;
      case 'losers':
        return losersData;
      default:
        return null;
    }
  };

  const handleRefresh = () => {
    switch (activeTab) {
      case 'volume':
        refetchVolume();
        break;
      case 'gainers':
        refetchGainers();
        break;
      case 'losers':
        refetchLosers();
        break;
    }
  };

  const currentData = getCurrentData();
  const items = currentData?.items || [];

  const tabs = [
    { id: 'volume', label: '거래량', icon: '📊' },
    { id: 'gainers', label: '상승률', icon: '🔥' },
    { id: 'losers', label: '하락률', icon: '💧' },
  ];

  return (
    <div className="max-w-md mx-auto">
      {/* 고정 헤더 영역 */}
      <div className="sticky top-0 bg-gray-50 z-10 -mx-4 px-4 pt-1 pb-2">
        {/* 헤더 */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Flame size={24} className="text-orange-500" />
            <h2 className="text-lg font-bold">실시간 인기 종목</h2>
          </div>
          <button
            onClick={handleRefresh}
            disabled={isLoading}
            className="btn btn-ghost btn-sm"
          >
            <RefreshCw size={16} className={isLoading ? 'animate-spin' : ''} />
          </button>
        </div>

        {/* 탭 */}
        <div className="flex gap-2">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-1 ${
                activeTab === tab.id
                  ? 'bg-orange-500 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              <span>{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* 데이터 소스 표시 */}
      {currentData?.source && (
        <p className="text-xs text-gray-400 mt-3 mb-2">
          데이터: {currentData.source} | {new Date(currentData.generated_at).toLocaleTimeString('ko-KR')}
        </p>
      )}

      {/* 로딩 */}
      {isLoading && <Loading text="데이터 로딩 중..." />}

      {/* 종목 리스트 */}
      {!isLoading && (
        <div className="space-y-3">
          {items.map((stock) => (
            <div
              key={stock.code}
              onClick={() => navigate(`/stock/${stock.code}`)}
              className="bg-white rounded-xl p-4 shadow-sm flex items-center gap-3 cursor-pointer hover:shadow-md transition-shadow"
            >
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white font-bold text-sm ${
                stock.rank <= 3 ? 'bg-orange-500' : 'bg-gray-400'
              }`}>
                {stock.rank}
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-gray-800">{stock.name}</h3>
                  {stock.market && (
                    <span className="text-xs text-gray-400">{stock.market}</span>
                  )}
                </div>
                <p className="text-sm text-gray-500">{stock.code}</p>
              </div>
              <div className="text-right">
                <p className="font-semibold">{stock.current_price?.toLocaleString()}원</p>
                <p className={`text-sm flex items-center justify-end gap-1 ${
                  (stock.change_rate || 0) >= 0 ? 'text-red-500' : 'text-blue-500'
                }`}>
                  {(stock.change_rate || 0) >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                  {(stock.change_rate || 0) >= 0 ? '+' : ''}{stock.change_rate?.toFixed(2)}%
                </p>
              </div>
              {activeTab === 'volume' && (
                <div className="text-xs text-gray-400 w-16 text-right">
                  {stock.volume ? `${(stock.volume / 10000).toFixed(0)}만주` : '-'}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {!isLoading && items.length === 0 && (
        <div className="text-center py-10 text-gray-500">
          데이터가 없습니다
        </div>
      )}
    </div>
  );
}
