import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Newspaper, ExternalLink, RefreshCw, AlertCircle } from 'lucide-react';
import { newsAPI } from '../api/client';

const categories = [
  { key: 'all', label: '전체', query: '주식 증시' },
  { key: '시장', label: '시장', query: '코스피 코스닥 증시' },
  { key: '기업', label: '기업', query: '삼성전자 현대차 SK하이닉스' },
  { key: '해외', label: '해외', query: '미국증시 나스닥 다우존스' },
  { key: '테마', label: '테마', query: '2차전지 AI반도체 바이오' },
];

export default function MarketNews() {
  const [selectedCategory, setSelectedCategory] = useState('all');

  const currentQuery = categories.find((c) => c.key === selectedCategory)?.query || '주식 증시';

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['news', selectedCategory],
    queryFn: () => newsAPI.search(currentQuery, 30).then((res) => res.data),
    staleTime: 5 * 60 * 1000, // 5분 캐시
    refetchOnWindowFocus: false,
  });

  const getCategoryColor = (category) => {
    const colors = {
      시장: 'bg-purple-100 text-purple-600',
      기업: 'bg-blue-100 text-blue-600',
      해외: 'bg-green-100 text-green-600',
      테마: 'bg-orange-100 text-orange-600',
    };
    return colors[category] || 'bg-gray-100 text-gray-600';
  };

  // 뉴스 카테고리 자동 분류
  const categorizeNews = (title) => {
    if (/코스피|코스닥|증시|지수|외국인|기관/.test(title)) return '시장';
    if (/삼성|현대|SK|LG|카카오|네이버/.test(title)) return '기업';
    if (/미국|나스닥|다우|S&P|연준|달러/.test(title)) return '해외';
    if (/2차전지|반도체|AI|바이오|테마/.test(title)) return '테마';
    return '시장';
  };

  return (
    <div className="max-w-md mx-auto">
      {/* 헤더 */}
      <div className="bg-gradient-to-r from-orange-500 to-amber-500 -mx-4 -mt-4 px-4 py-6 mb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center">
              <Newspaper size={28} className="text-white" />
            </div>
            <div className="text-white">
              <h1 className="text-xl font-bold">시장 뉴스</h1>
              <p className="text-sm opacity-80">증권/경제 주요 소식</p>
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

      {/* 카테고리 필터 */}
      <div className="flex gap-2 mb-4 overflow-x-auto pb-2">
        {categories.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setSelectedCategory(key)}
            className={`px-4 py-2 rounded-full whitespace-nowrap text-sm font-medium transition-all ${
              selectedCategory === key
                ? 'bg-orange-500 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* 에러 상태 */}
      {error && (
        <div className="bg-red-50 rounded-xl p-4 mb-4 flex items-center gap-3">
          <AlertCircle className="text-red-500" size={20} />
          <div>
            <p className="text-red-700 font-medium">뉴스를 불러올 수 없습니다</p>
            <p className="text-red-500 text-sm">{error.response?.data?.detail || error.message}</p>
          </div>
        </div>
      )}

      {/* 로딩 상태 */}
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="bg-white rounded-xl p-4 shadow-sm animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-3/4 mb-2"></div>
              <div className="h-3 bg-gray-200 rounded w-1/2"></div>
            </div>
          ))}
        </div>
      ) : (
        /* 뉴스 리스트 */
        <div className="space-y-3">
          {data?.items?.map((item, idx) => {
            // 전체 선택 시에만 제목에서 카테고리 추측, 그 외에는 선택한 카테고리 사용
            const category = selectedCategory === 'all' ? categorizeNews(item.title) : selectedCategory;
            return (
              <a
                key={idx}
                href={item.link}
                target="_blank"
                rel="noopener noreferrer"
                className="block bg-white rounded-xl p-4 shadow-sm hover:shadow-md transition-shadow"
              >
                <div className="flex justify-between items-start gap-3">
                  <div className="flex-1">
                    <h3 className="font-medium text-gray-800 leading-snug line-clamp-2">
                      {item.title}
                    </h3>
                    <p className="text-sm text-gray-500 mt-1 line-clamp-1">{item.description}</p>
                    <div className="flex items-center gap-2 mt-2">
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-medium ${getCategoryColor(category)}`}
                      >
                        {category}
                      </span>
                      <span className="text-xs text-gray-400">{item.source}</span>
                      <span className="text-xs text-gray-400">{item.pub_date}</span>
                    </div>
                  </div>
                  <ExternalLink size={16} className="text-gray-400 flex-shrink-0 mt-1" />
                </div>
              </a>
            );
          })}
        </div>
      )}

      {/* 데이터 없음 */}
      {!isLoading && !error && data?.items?.length === 0 && (
        <div className="text-center py-12">
          <Newspaper size={48} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-500">뉴스가 없습니다</p>
        </div>
      )}

      {/* 마지막 업데이트 시간 */}
      {data?.fetched_at && (
        <p className="text-center text-xs text-gray-400 py-4">
          마지막 업데이트: {new Date(data.fetched_at).toLocaleTimeString('ko-KR')}
        </p>
      )}
    </div>
  );
}
