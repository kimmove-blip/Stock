import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { top100API } from '../api/client';
import { Flame, ArrowLeft, TrendingUp, TrendingDown } from 'lucide-react';
import Loading from '../components/Loading';

export default function PopularStocks() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('volume');

  const { data, isLoading } = useQuery({
    queryKey: ['top100'],
    queryFn: () => top100API.list().then((res) => res.data),
  });

  if (isLoading) return <Loading text="인기 종목 로딩 중..." />;

  const items = data?.items || [];

  // 탭별 정렬
  const getSortedItems = () => {
    switch (activeTab) {
      case 'volume':
        return [...items].sort((a, b) => (b.volume || 0) - (a.volume || 0)).slice(0, 20);
      case 'gainers':
        return [...items].sort((a, b) => (b.change_rate || 0) - (a.change_rate || 0)).slice(0, 20);
      case 'losers':
        return [...items].sort((a, b) => (a.change_rate || 0) - (b.change_rate || 0)).slice(0, 20);
      default:
        return items.slice(0, 20);
    }
  };

  const sortedItems = getSortedItems();

  const tabs = [
    { id: 'volume', label: '거래량' },
    { id: 'gainers', label: '상승률' },
    { id: 'losers', label: '하락률' },
  ];

  return (
    <div className="max-w-md mx-auto">
      {/* 헤더 */}
      <div className="bg-gradient-to-r from-orange-400 to-amber-500 -mx-4 -mt-4 px-4 py-6 mb-4">
        <button onClick={() => navigate('/')} className="text-white mb-4">
          <ArrowLeft size={24} />
        </button>
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center">
            <Flame size={28} className="text-white" />
          </div>
          <div className="text-white">
            <h1 className="text-xl font-bold">인기 종목</h1>
            <p className="text-sm opacity-80">거래량/등락률 상위</p>
          </div>
        </div>
      </div>

      {/* 탭 */}
      <div className="flex gap-2 mb-4">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'bg-orange-500 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* 종목 리스트 */}
      <div className="space-y-3">
        {sortedItems.map((stock, idx) => (
          <div
            key={stock.code}
            onClick={() => navigate(`/stock/${stock.code}`)}
            className="bg-white rounded-xl p-4 shadow-sm flex items-center gap-3 cursor-pointer hover:shadow-md transition-shadow"
          >
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white font-bold text-sm ${
              idx < 3 ? 'bg-orange-500' : 'bg-gray-400'
            }`}>
              {idx + 1}
            </div>
            <div className="flex-1">
              <h3 className="font-semibold text-gray-800">{stock.name}</h3>
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

      {sortedItems.length === 0 && (
        <div className="text-center py-10 text-gray-500">
          데이터가 없습니다
        </div>
      )}
    </div>
  );
}
