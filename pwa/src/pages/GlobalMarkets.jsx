import { ArrowLeft, Globe, TrendingUp, TrendingDown } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function GlobalMarkets() {
  const navigate = useNavigate();

  // TODO: 실제 API 연동
  const indices = [
    { name: 'S&P 500', country: '미국', value: '5,234.18', change: '+45.67', rate: '+0.88%', positive: true },
    { name: 'NASDAQ', country: '미국', value: '16,428.82', change: '+123.45', rate: '+0.76%', positive: true },
    { name: 'DOW', country: '미국', value: '39,127.14', change: '-87.23', rate: '-0.22%', positive: false },
    { name: 'NIKKEI 225', country: '일본', value: '38,487.90', change: '+234.56', rate: '+0.61%', positive: true },
    { name: 'Hang Seng', country: '홍콩', value: '17,234.56', change: '-123.45', rate: '-0.71%', positive: false },
  ];

  const currencies = [
    { name: 'USD/KRW', value: '1,342.50', change: '+3.20' },
    { name: 'EUR/KRW', value: '1,456.78', change: '-2.10' },
    { name: 'JPY/KRW', value: '8.92', change: '+0.05' },
  ];

  return (
    <div className="max-w-md mx-auto">
      {/* 헤더 */}
      <div className="bg-gradient-to-r from-pink-500 to-rose-500 -mx-4 -mt-4 px-4 py-6 mb-4">
        <button onClick={() => navigate('/')} className="text-white mb-4">
          <ArrowLeft size={24} />
        </button>
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center">
            <Globe size={28} className="text-white" />
          </div>
          <div className="text-white">
            <h1 className="text-xl font-bold">해외주식 현황</h1>
            <p className="text-sm opacity-80">글로벌 시장 지수</p>
          </div>
        </div>
      </div>

      {/* 주요 지수 */}
      <div className="space-y-3 mb-6">
        {indices.map((index) => (
          <div key={index.name} className="bg-white rounded-xl p-4 shadow-sm">
            <div className="flex justify-between items-center">
              <div>
                <div className="flex items-center gap-2">
                  <p className="font-semibold text-gray-800">{index.name}</p>
                  <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded">{index.country}</span>
                </div>
                <p className="text-lg font-bold text-gray-800 mt-1">{index.value}</p>
              </div>
              <div className={`text-right ${index.positive ? 'text-red-500' : 'text-blue-500'}`}>
                <div className="flex items-center gap-1 justify-end">
                  {index.positive ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
                  <span className="font-semibold">{index.rate}</span>
                </div>
                <p className="text-sm">{index.change}</p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* 환율 */}
      <div className="bg-white rounded-xl p-4 shadow-sm">
        <h3 className="font-semibold text-gray-800 mb-4">환율</h3>
        <div className="space-y-3">
          {currencies.map((curr) => (
            <div key={curr.name} className="flex justify-between items-center">
              <span className="text-gray-600">{curr.name}</span>
              <div className="text-right">
                <span className="font-semibold text-gray-800">{curr.value}</span>
                <span className={`ml-2 text-sm ${parseFloat(curr.change) >= 0 ? 'text-red-500' : 'text-blue-500'}`}>
                  {curr.change}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <p className="text-center text-sm text-gray-400 py-6">
        실시간 API 연동 예정
      </p>
    </div>
  );
}
