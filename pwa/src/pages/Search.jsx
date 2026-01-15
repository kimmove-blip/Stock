import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { themeAPI } from '../api/client';
import { useStockCache } from '../contexts/StockCacheContext';
import { Search as SearchIcon, X, Tag, TrendingUp, Loader2 } from 'lucide-react';

// 인기 테마 목록
const POPULAR_THEMES = [
  { id: 'ai', name: 'AI/인공지능', icon: '🤖' },
  { id: 'ev', name: '전기차/2차전지', icon: '🔋' },
  { id: 'semiconductor', name: '반도체', icon: '💾' },
  { id: 'bio', name: '바이오/제약', icon: '💊' },
  { id: 'defense', name: '방산/우주항공', icon: '🚀' },
];

// 인기 종목 목록
const POPULAR_STOCKS = ['삼성전자', 'SK하이닉스', 'NAVER', '현대차', '카카오'];

export default function Search() {
  const navigate = useNavigate();
  const { searchStocksPrefix, loading: cacheLoading } = useStockCache();

  const [keyword, setKeyword] = useState('');
  const [themeResults, setThemeResults] = useState({ themes: [], stocks: [] });
  const [themeLoading, setThemeLoading] = useState(false);
  const [showThemeResults, setShowThemeResults] = useState(false);

  // 실시간 종목 검색 (클라이언트 사이드 - 즉시 반영)
  const stockResults = useMemo(() => {
    if (!keyword.trim()) return [];
    return searchStocksPrefix(keyword, 30);
  }, [keyword, searchStocksPrefix]);

  // 테마 검색 (서버 사이드 - debounce)
  useEffect(() => {
    if (!keyword.trim() || keyword.length < 2) {
      setThemeResults({ themes: [], stocks: [] });
      setShowThemeResults(false);
      return;
    }

    const timer = setTimeout(async () => {
      try {
        setThemeLoading(true);
        const res = await themeAPI.search(keyword);
        setThemeResults(res.data || { themes: [], stocks: [] });
        setShowThemeResults(true);
      } catch (error) {
        console.error('Theme search failed:', error);
      } finally {
        setThemeLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [keyword]);

  const handleThemeClick = async (themeId) => {
    setThemeLoading(true);
    try {
      const { data } = await themeAPI.detail(themeId);
      setThemeResults({
        themes: [{ id: data.id, name: data.name, description: data.description }],
        stocks: data.stocks.map((s) => ({ ...s, themes: [data.name] })),
      });
      setKeyword(data.name);
      setShowThemeResults(true);
    } catch (error) {
      console.error('Theme search failed:', error);
    } finally {
      setThemeLoading(false);
    }
  };

  const handleClear = () => {
    setKeyword('');
    setThemeResults({ themes: [], stocks: [] });
    setShowThemeResults(false);
  };

  const handleStockClick = (code) => {
    navigate(`/stock/${code}`);
  };

  const hasResults = stockResults.length > 0 || themeResults.stocks?.length > 0;
  const isSearching = keyword.trim().length > 0;

  // 캐시 로딩 중
  if (cacheLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <Loader2 className="animate-spin text-primary mb-4" size={32} />
        <p className="text-base-content/60">종목 데이터 로딩 중...</p>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-xl font-bold mb-4">종목/테마 검색</h2>

      {/* 검색 입력 */}
      <div className="relative">
        <div className="join w-full">
          <div className="relative flex-1">
            <input
              type="text"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              className="input input-bordered w-full pr-10"
              placeholder="종목명, 종목코드 입력 (예: 삼성, 005930)"
              autoFocus
            />
            {keyword && (
              <button
                onClick={handleClear}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-base-200 rounded"
              >
                <X size={18} className="text-base-content/60" />
              </button>
            )}
          </div>
        </div>

        {/* 실시간 검색 결과 드롭다운 */}
        {isSearching && stockResults.length > 0 && (
          <div className="absolute left-0 right-0 top-full mt-1 bg-base-100 rounded-xl shadow-lg border border-base-200 max-h-[60vh] overflow-y-auto z-50">
            {stockResults.map((stock, index) => (
              <button
                key={stock.code}
                onClick={() => handleStockClick(stock.code)}
                className={`w-full px-4 py-3 flex items-center justify-between hover:bg-base-200 transition ${
                  index !== stockResults.length - 1 ? 'border-b border-base-200' : ''
                }`}
              >
                <div className="text-left">
                  <p className="font-semibold">
                    {highlightMatch(stock.name, keyword)}
                  </p>
                  <p className="text-sm text-base-content/60">{stock.code}</p>
                </div>
                {stock.market && (
                  <span className={`badge badge-sm ${
                    stock.market === 'KOSPI' ? 'badge-primary' : 'badge-secondary'
                  } badge-outline`}>
                    {stock.market}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}

        {/* 검색 중이지만 결과 없음 */}
        {isSearching && stockResults.length === 0 && !themeLoading && (
          <div className="absolute left-0 right-0 top-full mt-1 bg-base-100 rounded-xl shadow-lg border border-base-200 p-4 z-50">
            <p className="text-center text-base-content/60">
              "{keyword}"에 해당하는 종목이 없습니다
            </p>
          </div>
        )}
      </div>

      {/* 빠른 검색 - 검색어가 없을 때만 표시 */}
      {!isSearching && (
        <>
          {/* 인기 테마 */}
          <div className="mt-6">
            <h3 className="text-sm font-medium text-base-content/60 mb-3 flex items-center gap-2">
              <Tag size={14} />
              관련테마
            </h3>
            <div className="flex flex-wrap gap-2">
              {POPULAR_THEMES.map((theme) => (
                <button
                  key={theme.id}
                  onClick={() => handleThemeClick(theme.id)}
                  className="btn btn-sm btn-outline gap-1"
                >
                  <span>{theme.icon}</span>
                  {theme.name}
                </button>
              ))}
            </div>
          </div>

          {/* 인기 종목 */}
          <div className="mt-6">
            <h3 className="text-sm font-medium text-base-content/60 mb-3 flex items-center gap-2">
              <TrendingUp size={14} />
              빠른 검색
            </h3>
            <div className="flex flex-wrap gap-2">
              {POPULAR_STOCKS.map((name) => (
                <button
                  key={name}
                  onClick={() => setKeyword(name)}
                  className="btn btn-sm btn-outline"
                >
                  {name}
                </button>
              ))}
            </div>
          </div>
        </>
      )}

      {/* 테마 검색 결과 */}
      {showThemeResults && themeResults.themes?.length > 0 && (
        <div className="mt-6">
          <h3 className="text-sm font-medium text-base-content/60 mb-3 flex items-center gap-2">
            <Tag size={14} />
            관련 테마
          </h3>
          {themeResults.themes.map((theme) => (
            <div key={theme.id} className="bg-purple-50 rounded-xl p-3 mb-2">
              <div className="flex items-center gap-2">
                <Tag size={16} className="text-purple-600" />
                <span className="font-semibold text-purple-700">{theme.name}</span>
              </div>
              <p className="text-sm text-purple-600/80 mt-1">{theme.description}</p>
            </div>
          ))}

          {/* 테마 관련 종목 */}
          {themeResults.stocks?.length > 0 && (
            <div className="mt-3 space-y-2">
              <p className="text-sm text-base-content/60">
                테마 관련 종목 {themeResults.stocks.length}개
              </p>
              {themeResults.stocks.map((stock) => (
                <div
                  key={stock.code}
                  onClick={() => handleStockClick(stock.code)}
                  className="card bg-base-100 shadow-sm cursor-pointer hover:shadow-md transition-shadow"
                >
                  <div className="card-body p-4">
                    <div className="flex justify-between items-start">
                      <div>
                        <h3 className="font-bold">{stock.name}</h3>
                        <p className="text-sm text-base-content/60">{stock.code}</p>
                      </div>
                    </div>
                    {stock.themes && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {stock.themes.map((theme) => (
                          <span key={theme} className="badge badge-sm badge-primary badge-outline">
                            {theme}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// 검색어 하이라이트 헬퍼
function highlightMatch(text, query) {
  if (!query) return text;

  const lowerText = text.toLowerCase();
  const lowerQuery = query.toLowerCase();
  const index = lowerText.indexOf(lowerQuery);

  if (index === -1) return text;

  return (
    <>
      {text.slice(0, index)}
      <span className="text-primary font-bold">
        {text.slice(index, index + query.length)}
      </span>
      {text.slice(index + query.length)}
    </>
  );
}
