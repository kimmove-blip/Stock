import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { watchlistAPI, stockAPI } from '../api/client';
import Loading from '../components/Loading';
import { Plus, Trash2, Search, TrendingUp, TrendingDown } from 'lucide-react';

export default function Watchlist() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selectedCategory, setSelectedCategory] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [searchResults, setSearchResults] = useState([]);

  const { data, isLoading, error } = useQuery({
    queryKey: ['watchlist', selectedCategory],
    queryFn: () => watchlistAPI.list(selectedCategory).then((res) => res.data),
  });

  const addMutation = useMutation({
    mutationFn: (stock) =>
      watchlistAPI.add({
        stock_code: stock.code,
        stock_name: stock.name,
        category: selectedCategory || '기본',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries(['watchlist']);
      setShowAddModal(false);
      setSearchKeyword('');
      setSearchResults([]);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: ({ code, category }) => watchlistAPI.delete(code, category),
    onSuccess: () => queryClient.invalidateQueries(['watchlist']),
  });

  const handleSearch = async () => {
    if (!searchKeyword.trim()) return;
    try {
      const { data } = await stockAPI.search(searchKeyword);
      setSearchResults(data);
    } catch (error) {
      console.error('Search failed:', error);
    }
  };

  if (isLoading) return <Loading text="관심종목 불러오는 중..." />;

  if (error) {
    return (
      <div className="alert alert-error">
        <span>데이터를 불러올 수 없습니다</span>
      </div>
    );
  }

  const categories = data?.categories || ['기본'];

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold">관심종목</h2>
        <button onClick={() => setShowAddModal(true)} className="btn btn-primary btn-sm">
          <Plus size={16} /> 추가
        </button>
      </div>

      {/* 카테고리 탭 */}
      <div className="tabs tabs-boxed mb-4">
        <button
          onClick={() => setSelectedCategory('')}
          className={`tab ${selectedCategory === '' ? 'tab-active' : ''}`}
        >
          전체
        </button>
        {categories.map((cat) => (
          <button
            key={cat}
            onClick={() => setSelectedCategory(cat)}
            className={`tab ${selectedCategory === cat ? 'tab-active' : ''}`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* 종목 리스트 */}
      <div className="space-y-2">
        {data?.items?.map((item) => {
          const isPositive = (item.change_rate || 0) >= 0;
          return (
            <div key={`${item.stock_code}-${item.category}`} className="card bg-base-100 shadow-sm">
              <div className="card-body p-4 flex-row justify-between items-center">
                <div
                  onClick={() => navigate(`/stock/${item.stock_code}`)}
                  className="cursor-pointer flex-1"
                >
                  <h3 className="font-bold">{item.stock_name}</h3>
                  <p className="text-xs text-base-content/60">{item.stock_code}</p>
                </div>

                <div className="flex items-center gap-3">
                  {item.current_price && (
                    <div className="text-right">
                      <p className="font-semibold">{item.current_price.toLocaleString()}원</p>
                      <p className={`text-sm flex items-center justify-end ${isPositive ? 'text-error' : 'text-info'}`}>
                        {isPositive ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                        <span className="ml-1">{isPositive ? '+' : ''}{item.change_rate?.toFixed(2)}%</span>
                      </p>
                    </div>
                  )}

                  <button
                    onClick={() => {
                      if (confirm('삭제하시겠습니까?')) {
                        deleteMutation.mutate({
                          code: item.stock_code,
                          category: item.category || '기본',
                        });
                      }
                    }}
                    className="btn btn-ghost btn-xs text-error"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {data?.items?.length === 0 && (
        <div className="text-center py-10 text-base-content/60">
          관심종목이 없습니다
        </div>
      )}

      {/* 종목 추가 모달 */}
      {showAddModal && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">관심종목 추가</h3>

            <div className="form-control mt-4">
              <div className="join w-full">
                <input
                  type="text"
                  value={searchKeyword}
                  onChange={(e) => setSearchKeyword(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  className="input input-bordered join-item flex-1"
                  placeholder="종목명 또는 코드"
                />
                <button onClick={handleSearch} className="btn btn-primary join-item">
                  <Search size={18} />
                </button>
              </div>
            </div>

            <div className="mt-4 max-h-60 overflow-y-auto">
              {searchResults.map((stock) => (
                <div
                  key={stock.code}
                  onClick={() => addMutation.mutate(stock)}
                  className="p-3 hover:bg-base-200 cursor-pointer rounded flex justify-between items-center"
                >
                  <div>
                    <p className="font-medium">{stock.name}</p>
                    <p className="text-sm text-base-content/60">{stock.code}</p>
                  </div>
                  <Plus size={18} className="text-primary" />
                </div>
              ))}
            </div>

            <div className="modal-action">
              <button
                onClick={() => {
                  setShowAddModal(false);
                  setSearchKeyword('');
                  setSearchResults([]);
                }}
                className="btn"
              >
                닫기
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
