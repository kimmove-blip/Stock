import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { stockAPI, themeAPI } from '../api/client';
import { Search as SearchIcon, X, Tag, TrendingUp } from 'lucide-react';

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
  const [keyword, setKeyword] = useState('');
  const [stockResults, setStockResults] = useState([]);
  const [themeResults, setThemeResults] = useState({ themes: [], stocks: [] });
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [activeTab, setActiveTab] = useState('all'); // 'all', 'stock', 'theme'

  const handleSearch = async () => {
    if (!keyword.trim()) return;

    setLoading(true);
    setSearched(true);

    try {
      // 종목 검색과 테마 검색 동시 실행
      const [stockRes, themeRes] = await Promise.all([
        stockAPI.search(keyword).catch(() => ({ data: [] })),
        themeAPI.search(keyword).catch(() => ({ data: { themes: [], stocks: [] } })),
      ]);

      setStockResults(stockRes.data || []);
      setThemeResults(themeRes.data || { themes: [], stocks: [] });
    } catch (error) {
      console.error('Search failed:', error);
      setStockResults([]);
      setThemeResults({ themes: [], stocks: [] });
    } finally {
      setLoading(false);
    }
  };

  const handleThemeClick = async (themeId) => {
    setLoading(true);
    setSearched(true);
    setActiveTab('theme');

    try {
      const { data } = await themeAPI.detail(themeId);
      setThemeResults({
        themes: [{ id: data.id, name: data.name, description: data.description }],
        stocks: data.stocks.map((s) => ({ ...s, themes: [data.name] })),
      });
      setStockResults([]);
      setKeyword(data.name);
    } catch (error) {
      console.error('Theme search failed:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleClear = () => {
    setKeyword('');
    setStockResults([]);
    setThemeResults({ themes: [], stocks: [] });
    setSearched(false);
    setActiveTab('all');
  };

  const hasStockResults = stockResults.length > 0;
  const hasThemeResults = themeResults.themes?.length > 0 || themeResults.stocks?.length > 0;
  const totalResults = stockResults.length + (themeResults.stocks?.length || 0);

  return (
    <div>
      <h2 className="text-xl font-bold mb-4">종목/테마 검색</h2>

      {/* 검색 입력 */}
      <div className="form-control">
        <div className="join w-full">
          <input
            type="text"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            className="input input-bordered join-item flex-1"
            placeholder="종목명, 종목코드 또는 테마 입력"
          />
          {keyword && (
            <button onClick={handleClear} className="btn btn-ghost join-item">
              <X size={18} />
            </button>
          )}
          <button
            onClick={handleSearch}
            className="btn btn-primary join-item"
            disabled={loading}
          >
            {loading ? (
              <span className="loading loading-spinner loading-sm"></span>
            ) : (
              <SearchIcon size={18} />
            )}
          </button>
        </div>
      </div>

      {/* 빠른 검색 - 검색 전에만 표시 */}
      {!searched && (
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
                  onClick={() => {
                    setKeyword(name);
                    setActiveTab('stock');
                    setTimeout(() => handleSearch(), 0);
                  }}
                  className="btn btn-sm btn-outline"
                >
                  {name}
                </button>
              ))}
            </div>
          </div>
        </>
      )}

      {/* 검색 결과 */}
      {searched && (
        <div className="mt-6">
          {/* 탭 - 종목/테마 결과 모두 있을 때 */}
          {hasStockResults && hasThemeResults && (
            <div className="tabs tabs-boxed mb-4">
              <button
                className={`tab ${activeTab === 'all' ? 'tab-active' : ''}`}
                onClick={() => setActiveTab('all')}
              >
                전체 ({totalResults})
              </button>
              <button
                className={`tab ${activeTab === 'stock' ? 'tab-active' : ''}`}
                onClick={() => setActiveTab('stock')}
              >
                종목 ({stockResults.length})
              </button>
              <button
                className={`tab ${activeTab === 'theme' ? 'tab-active' : ''}`}
                onClick={() => setActiveTab('theme')}
              >
                테마 ({themeResults.stocks?.length || 0})
              </button>
            </div>
          )}

          {/* 테마 정보 표시 */}
          {(activeTab === 'all' || activeTab === 'theme') && themeResults.themes?.length > 0 && (
            <div className="mb-4">
              {themeResults.themes.map((theme) => (
                <div key={theme.id} className="bg-purple-50 rounded-xl p-3 mb-2">
                  <div className="flex items-center gap-2">
                    <Tag size={16} className="text-purple-600" />
                    <span className="font-semibold text-purple-700">{theme.name}</span>
                  </div>
                  <p className="text-sm text-purple-600/80 mt-1">{theme.description}</p>
                </div>
              ))}
            </div>
          )}

          <p className="text-sm text-base-content/60 mb-3">
            검색 결과: {activeTab === 'stock' ? stockResults.length : activeTab === 'theme' ? (themeResults.stocks?.length || 0) : totalResults}건
          </p>

          {/* 종목 검색 결과 */}
          {(activeTab === 'all' || activeTab === 'stock') && stockResults.length > 0 && (
            <div className="space-y-2">
              {stockResults.map((stock) => (
                <div
                  key={stock.code}
                  onClick={() => navigate(`/stock/${stock.code}`)}
                  className="card bg-base-100 shadow-sm cursor-pointer hover:shadow-md transition-shadow"
                >
                  <div className="card-body p-4 flex-row justify-between items-center">
                    <div>
                      <h3 className="font-bold">{stock.name}</h3>
                      <p className="text-sm text-base-content/60">{stock.code}</p>
                    </div>
                    {stock.market && (
                      <span className="badge badge-ghost">{stock.market}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* 테마 관련 종목 결과 */}
          {(activeTab === 'all' || activeTab === 'theme') && themeResults.stocks?.length > 0 && (
            <div className="space-y-2 mt-2">
              {themeResults.stocks.map((stock) => (
                <div
                  key={stock.code}
                  onClick={() => navigate(`/stock/${stock.code}`)}
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

          {totalResults === 0 && !loading && (
            <div className="text-center py-10 text-base-content/60">
              검색 결과가 없습니다
            </div>
          )}
        </div>
      )}
    </div>
  );
}
