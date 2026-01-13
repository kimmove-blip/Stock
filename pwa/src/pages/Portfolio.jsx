import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { portfolioAPI, stockAPI } from '../api/client';
import Loading from '../components/Loading';
import { Plus, Trash2, TrendingUp, TrendingDown, Search } from 'lucide-react';

export default function Portfolio() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showAddModal, setShowAddModal] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [selectedStock, setSelectedStock] = useState(null);
  const [buyPrice, setBuyPrice] = useState('');
  const [quantity, setQuantity] = useState(1);

  const { data, isLoading, error } = useQuery({
    queryKey: ['portfolio'],
    queryFn: () => portfolioAPI.list().then((res) => res.data),
  });

  const addMutation = useMutation({
    mutationFn: (data) => portfolioAPI.add(data),
    onSuccess: () => {
      queryClient.invalidateQueries(['portfolio']);
      setShowAddModal(false);
      resetForm();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id) => portfolioAPI.delete(id),
    onSuccess: () => queryClient.invalidateQueries(['portfolio']),
  });

  const resetForm = () => {
    setSearchKeyword('');
    setSearchResults([]);
    setSelectedStock(null);
    setBuyPrice('');
    setQuantity(1);
  };

  const handleSearch = async () => {
    if (!searchKeyword.trim()) return;
    try {
      const { data } = await stockAPI.search(searchKeyword);
      setSearchResults(data);
    } catch (error) {
      console.error('Search failed:', error);
    }
  };

  const handleAdd = () => {
    if (!selectedStock) return;
    addMutation.mutate({
      stock_code: selectedStock.code,
      stock_name: selectedStock.name,
      buy_price: parseInt(buyPrice) || 0,
      quantity: parseInt(quantity) || 1,
    });
  };

  if (isLoading) return <Loading text="보유종목 불러오는 중..." />;

  if (error) {
    return (
      <div className="alert alert-error">
        <span>데이터를 불러올 수 없습니다</span>
      </div>
    );
  }

  const summary = data?.summary || {
    total_investment: 0,
    total_value: 0,
    total_profit_loss: 0,
    total_profit_loss_rate: 0,
    stock_count: 0,
  };

  const isPositive = summary.total_profit_loss >= 0;

  return (
    <div>
      {/* 요약 카드 */}
      <div className="card bg-base-100 shadow mb-4">
        <div className="card-body p-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-base-content/60">투자금액</p>
              <p className="font-semibold">{summary.total_investment.toLocaleString()}원</p>
            </div>
            <div>
              <p className="text-xs text-base-content/60">평가금액</p>
              <p className="font-semibold">{summary.total_value.toLocaleString()}원</p>
            </div>
            <div>
              <p className="text-xs text-base-content/60">손익</p>
              <p className={`font-semibold ${isPositive ? 'text-error' : 'text-info'}`}>
                {isPositive ? '+' : ''}{summary.total_profit_loss.toLocaleString()}원
              </p>
            </div>
            <div>
              <p className="text-xs text-base-content/60">수익률</p>
              <p className={`font-semibold flex items-center ${isPositive ? 'text-error' : 'text-info'}`}>
                {isPositive ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
                <span className="ml-1">
                  {isPositive ? '+' : ''}{summary.total_profit_loss_rate.toFixed(2)}%
                </span>
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* 종목 추가 버튼 */}
      <button
        onClick={() => setShowAddModal(true)}
        className="btn btn-primary btn-sm mb-4"
      >
        <Plus size={16} /> 종목 추가
      </button>

      {/* 종목 리스트 */}
      <div className="space-y-3">
        {data?.items?.map((item) => (
          <div key={item.id} className="card bg-base-100 shadow-sm">
            <div className="card-body p-4">
              <div className="flex justify-between items-start">
                <div onClick={() => navigate(`/stock/${item.stock_code}`)} className="cursor-pointer">
                  <h3 className="font-bold">{item.stock_name}</h3>
                  <p className="text-xs text-base-content/60">{item.stock_code}</p>
                </div>
                <button
                  onClick={() => {
                    if (confirm('삭제하시겠습니까?')) {
                      deleteMutation.mutate(item.id);
                    }
                  }}
                  className="btn btn-ghost btn-xs text-error"
                >
                  <Trash2 size={14} />
                </button>
              </div>

              <div className="grid grid-cols-3 gap-2 mt-2 text-sm">
                <div>
                  <p className="text-xs text-base-content/60">매수가</p>
                  <p>{item.buy_price?.toLocaleString()}원</p>
                </div>
                <div>
                  <p className="text-xs text-base-content/60">현재가</p>
                  <p>{item.current_price?.toLocaleString() || '-'}원</p>
                </div>
                <div>
                  <p className="text-xs text-base-content/60">수량</p>
                  <p>{item.quantity}주</p>
                </div>
              </div>

              <div className="flex justify-between items-center mt-2">
                <span className={`text-sm font-semibold ${(item.profit_loss_rate || 0) >= 0 ? 'text-error' : 'text-info'}`}>
                  {(item.profit_loss_rate || 0) >= 0 ? '+' : ''}{item.profit_loss_rate?.toFixed(2) || 0}%
                </span>
                {item.ai_opinion && (
                  <span className={`badge badge-sm ${
                    item.ai_opinion === '매수' ? 'badge-success' :
                    item.ai_opinion === '매도' || item.ai_opinion === '손절' ? 'badge-error' :
                    'badge-ghost'
                  }`}>
                    {item.ai_opinion}
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {data?.items?.length === 0 && (
        <div className="text-center py-10 text-base-content/60">
          보유종목이 비어있습니다
        </div>
      )}

      {/* 종목 추가 모달 */}
      {showAddModal && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">종목 추가</h3>

            {!selectedStock ? (
              <>
                <div className="form-control mt-4">
                  <div className="input-group">
                    <input
                      type="text"
                      value={searchKeyword}
                      onChange={(e) => setSearchKeyword(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                      className="input input-bordered flex-1"
                      placeholder="종목명 또는 코드"
                    />
                    <button onClick={handleSearch} className="btn btn-primary">
                      <Search size={18} />
                    </button>
                  </div>
                </div>

                <div className="mt-4 max-h-60 overflow-y-auto">
                  {searchResults.map((stock) => (
                    <div
                      key={stock.code}
                      onClick={() => setSelectedStock(stock)}
                      className="p-3 hover:bg-base-200 cursor-pointer rounded"
                    >
                      <p className="font-medium">{stock.name}</p>
                      <p className="text-sm text-base-content/60">{stock.code}</p>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <>
                <div className="mt-4 p-3 bg-base-200 rounded">
                  <p className="font-bold">{selectedStock.name}</p>
                  <p className="text-sm text-base-content/60">{selectedStock.code}</p>
                </div>

                <div className="form-control mt-4">
                  <label className="label">
                    <span className="label-text">매수가</span>
                  </label>
                  <input
                    type="number"
                    value={buyPrice}
                    onChange={(e) => setBuyPrice(e.target.value)}
                    className="input input-bordered"
                    placeholder="매수가 입력"
                  />
                </div>

                <div className="form-control mt-4">
                  <label className="label">
                    <span className="label-text">수량</span>
                  </label>
                  <input
                    type="number"
                    value={quantity}
                    onChange={(e) => setQuantity(e.target.value)}
                    className="input input-bordered"
                    min="1"
                  />
                </div>

                <div className="modal-action">
                  <button onClick={() => setSelectedStock(null)} className="btn btn-ghost">
                    뒤로
                  </button>
                  <button
                    onClick={handleAdd}
                    className="btn btn-primary"
                    disabled={addMutation.isPending}
                  >
                    {addMutation.isPending ? <span className="loading loading-spinner"></span> : '추가'}
                  </button>
                </div>
              </>
            )}

            {!selectedStock && (
              <div className="modal-action">
                <button onClick={() => { setShowAddModal(false); resetForm(); }} className="btn">
                  취소
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
