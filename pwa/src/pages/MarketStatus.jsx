import { ArrowLeft, BarChart3, TrendingUp, TrendingDown } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function MarketStatus() {
  const navigate = useNavigate();

  // TODO: 실제 API 연동
  const indices = [
    { name: '코스피', value: '2,687.44', change: '+15.23', rate: '+0.57%', positive: true },
    { name: '코스닥', value: '876.32', change: '-3.21', rate: '-0.37%', positive: false },
  ];

  const marketInfo = [
    { label: '거래량', value: '5.2억주' },
    { label: '거래대금', value: '12.3조' },
    { label: '상승', value: '523' },
    { label: '하락', value: '412' },
    { label: '보합', value: '87' },
  ];

  return (
    <div className="max-w-md mx-auto">
      {/* 헤더 */}
      <div className="bg-gradient-to-r from-indigo-500 to-purple-500 -mx-4 -mt-4 px-4 py-6 mb-4">
        <button onClick={() => navigate('/')} className="text-white mb-4">
          <ArrowLeft size={24} />
        </button>
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center">
            <BarChart3 size={28} className="text-white" />
          </div>
          <div className="text-white">
            <h1 className="text-xl font-bold">코스피/코스닥</h1>
            <p className="text-sm opacity-80">국내 시장 현황</p>
          </div>
        </div>
      </div>

      {/* 지수 카드 */}
      <div className="space-y-3 mb-6">
        {indices.map((index) => (
          <div key={index.name} className="bg-white rounded-xl p-4 shadow-sm">
            <div className="flex justify-between items-center">
              <div>
                <p className="text-sm text-gray-500">{index.name}</p>
                <p className="text-2xl font-bold text-gray-800">{index.value}</p>
              </div>
              <div className={`text-right ${index.positive ? 'text-red-500' : 'text-blue-500'}`}>
                <div className="flex items-center gap-1 justify-end">
                  {index.positive ? <TrendingUp size={20} /> : <TrendingDown size={20} />}
                  <span className="font-semibold">{index.rate}</span>
                </div>
                <p className="text-sm">{index.change}</p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* 시장 정보 */}
      <div className="bg-white rounded-xl p-4 shadow-sm">
        <h3 className="font-semibold text-gray-800 mb-4">시장 정보</h3>
        <div className="grid grid-cols-2 gap-4">
          {marketInfo.map((item) => (
            <div key={item.label} className="flex justify-between">
              <span className="text-gray-500 text-sm">{item.label}</span>
              <span className="font-medium text-gray-800">{item.value}</span>
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
