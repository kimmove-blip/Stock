import { TrendingUp, TrendingDown } from 'lucide-react';

export default function StockCard({ stock, onClick, showScore = true, inPortfolio = false, inWatchlist = false }) {
  const isPositive = (stock.change_rate || 0) >= 0;

  return (
    <div
      onClick={onClick}
      className="card bg-base-100 shadow-sm cursor-pointer hover:shadow-md transition-shadow"
    >
      <div className="card-body p-4">
        <div className="flex justify-between items-start">
          <div>
            <div className="flex items-center gap-1.5">
              <h3 className="font-bold text-base">{stock.name}</h3>
              {inPortfolio && (
                <span className="bg-blue-100 text-blue-600 text-[10px] px-1.5 py-0.5 rounded font-medium">
                  보유
                </span>
              )}
              {inWatchlist && (
                <span className="bg-yellow-100 text-yellow-600 text-[10px] px-1.5 py-0.5 rounded font-medium">
                  관심
                </span>
              )}
            </div>
            <p className="text-xs text-base-content/60">{stock.code}</p>
          </div>
          {showScore && stock.score !== undefined && (
            <div className="badge badge-primary badge-lg">{stock.score}점</div>
          )}
        </div>

        <div className="flex justify-between items-end mt-2">
          <div>
            {stock.current_price && (
              <p className="text-lg font-semibold">
                {stock.current_price.toLocaleString()}원
              </p>
            )}
          </div>
          <div className={`flex items-center ${isPositive ? 'text-error' : 'text-info'}`}>
            {isPositive ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
            <span className="ml-1 font-medium">
              {isPositive ? '+' : ''}{stock.change_rate?.toFixed(2) || 0}%
            </span>
          </div>
        </div>

        {stock.opinion && (
          <div className="mt-2">
            <span className={`badge ${
              stock.opinion === '매수' ? 'badge-success' :
              stock.opinion === '과열 주의' || stock.opinion === '손절' ? 'badge-error' :
              stock.opinion === '주의' ? 'badge-warning' :
              'badge-ghost'
            }`}>
              {stock.opinion}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
