import { useState } from 'react';
import { ArrowLeft, Newspaper, ExternalLink, RefreshCw } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function MarketNews() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);

  // TODO: 실제 뉴스 API 연동
  const news = [
    {
      id: 1,
      title: '코스피, 외국인 매수세에 상승 출발',
      source: '연합뉴스',
      time: '1시간 전',
      category: '시장',
    },
    {
      id: 2,
      title: '삼성전자, AI 반도체 수요 증가로 실적 개선 기대',
      source: '한국경제',
      time: '2시간 전',
      category: '기업',
    },
    {
      id: 3,
      title: '미 연준 금리 동결 시사, 증시 영향은?',
      source: '머니투데이',
      time: '3시간 전',
      category: '해외',
    },
    {
      id: 4,
      title: '2차전지 관련주 강세, 테마 지속 전망',
      source: '이데일리',
      time: '4시간 전',
      category: '테마',
    },
    {
      id: 5,
      title: '개인투자자 순매수 상위 종목은?',
      source: '조선비즈',
      time: '5시간 전',
      category: '시장',
    },
  ];

  const getCategoryColor = (category) => {
    const colors = {
      시장: 'bg-purple-100 text-purple-600',
      기업: 'bg-blue-100 text-blue-600',
      해외: 'bg-green-100 text-green-600',
      테마: 'bg-orange-100 text-orange-600',
    };
    return colors[category] || 'bg-gray-100 text-gray-600';
  };

  return (
    <div className="max-w-md mx-auto">
      {/* 헤더 */}
      <div className="bg-gradient-to-r from-orange-500 to-amber-500 -mx-4 -mt-4 px-4 py-6 mb-4">
        <button onClick={() => navigate('/')} className="text-white mb-4">
          <ArrowLeft size={24} />
        </button>
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
            onClick={() => setLoading(true)}
            className="p-2 bg-white/20 rounded-lg"
          >
            <RefreshCw size={20} className={`text-white ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* 뉴스 리스트 */}
      <div className="space-y-3">
        {news.map((item) => (
          <div
            key={item.id}
            className="bg-white rounded-xl p-4 shadow-sm cursor-pointer hover:shadow-md transition-shadow"
          >
            <div className="flex justify-between items-start gap-3">
              <div className="flex-1">
                <h3 className="font-medium text-gray-800 leading-snug">{item.title}</h3>
                <div className="flex items-center gap-2 mt-2">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${getCategoryColor(item.category)}`}>
                    {item.category}
                  </span>
                  <span className="text-xs text-gray-400">{item.source}</span>
                  <span className="text-xs text-gray-400">{item.time}</span>
                </div>
              </div>
              <ExternalLink size={16} className="text-gray-400 flex-shrink-0 mt-1" />
            </div>
          </div>
        ))}
      </div>

      <p className="text-center text-sm text-gray-400 py-6">
        뉴스 API 연동 예정
      </p>
    </div>
  );
}
