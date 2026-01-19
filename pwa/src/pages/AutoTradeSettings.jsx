import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { autoTradeAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import Loading from '../components/Loading';
import {
  Settings,
  Save,
  AlertCircle,
  Bot,
  HandMetal,
  DollarSign,
  TrendingDown,
  TrendingUp,
  Clock,
  ToggleLeft,
  ToggleRight,
} from 'lucide-react';

export default function AutoTradeSettings() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [formData, setFormData] = useState({
    trade_mode: 'manual', // auto: 완전자동, semi: 반자동(승인필요), manual: 수동
    max_investment: 1000000, // 최대 투자금액
    max_per_stock: 200000, // 종목당 최대 투자금액
    stop_loss_rate: 5, // 손절 비율 (%)
    take_profit_rate: 10, // 익절 비율 (%)
    trading_enabled: true, // 자동매매 활성화
    trading_start_time: '09:00', // 매매 시작 시간
    trading_end_time: '15:20', // 매매 종료 시간
  });

  // 자동매매 권한 체크
  if (!user?.auto_trade_enabled) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="text-center">
          <AlertCircle size={48} className="mx-auto text-gray-400 mb-4" />
          <h2 className="text-lg font-bold text-gray-700 mb-2">접근 권한 없음</h2>
          <p className="text-gray-500 text-sm">자동매매 권한이 필요합니다.</p>
        </div>
      </div>
    );
  }

  // 설정 조회
  const { data, isLoading } = useQuery({
    queryKey: ['autoTradeSettings'],
    queryFn: () => autoTradeAPI.getSettings().then((res) => res.data),
    onSuccess: (data) => {
      if (data) {
        setFormData((prev) => ({ ...prev, ...data }));
      }
    },
  });

  // 설정 저장
  const saveMutation = useMutation({
    mutationFn: (data) => autoTradeAPI.saveSettings(data),
    onSuccess: () => {
      queryClient.invalidateQueries(['autoTradeSettings']);
      alert('설정이 저장되었습니다.');
    },
    onError: (error) => {
      alert(error.response?.data?.detail || '설정 저장에 실패했습니다.');
    },
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    saveMutation.mutate(formData);
  };

  const tradeModes = [
    {
      value: 'auto',
      label: '완전 자동',
      icon: Bot,
      description: 'AI가 자동으로 매수/매도 실행',
      color: 'bg-green-500',
    },
    {
      value: 'semi',
      label: '반자동 (승인필요)',
      icon: HandMetal,
      description: 'AI 제안 후 사용자 승인 시 실행',
      color: 'bg-yellow-500',
    },
    {
      value: 'manual',
      label: '수동',
      icon: Settings,
      description: '알림만 받고 직접 매매',
      color: 'bg-gray-500',
    },
  ];

  if (isLoading) return <Loading text="설정 불러오는 중..." />;

  return (
    <div className="max-w-md mx-auto space-y-4">
      {/* 자동매매 활성화 토글 */}
      <div className="bg-white rounded-xl p-4 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {formData.trading_enabled ? (
              <div className="w-10 h-10 bg-green-500 rounded-full flex items-center justify-center">
                <Bot size={20} className="text-white" />
              </div>
            ) : (
              <div className="w-10 h-10 bg-gray-400 rounded-full flex items-center justify-center">
                <Bot size={20} className="text-white" />
              </div>
            )}
            <div>
              <p className="font-bold text-gray-800">자동매매</p>
              <p className="text-sm text-gray-500">
                {formData.trading_enabled ? '활성화됨' : '비활성화됨'}
              </p>
            </div>
          </div>
          <button
            onClick={() => setFormData({ ...formData, trading_enabled: !formData.trading_enabled })}
            className="text-gray-600"
          >
            {formData.trading_enabled ? (
              <ToggleRight size={40} className="text-green-500" />
            ) : (
              <ToggleLeft size={40} className="text-gray-400" />
            )}
          </button>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* 매매 모드 선택 */}
        <div className="bg-white rounded-xl p-4 shadow-sm">
          <h3 className="font-bold text-gray-800 mb-3 flex items-center gap-2">
            <Settings size={18} className="text-purple-600" />
            매매 모드
          </h3>
          <div className="space-y-2">
            {tradeModes.map((mode) => (
              <label
                key={mode.value}
                className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer border-2 transition-all ${
                  formData.trade_mode === mode.value
                    ? 'border-purple-500 bg-purple-50'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
              >
                <input
                  type="radio"
                  name="trade_mode"
                  value={mode.value}
                  checked={formData.trade_mode === mode.value}
                  onChange={(e) => setFormData({ ...formData, trade_mode: e.target.value })}
                  className="hidden"
                />
                <div className={`w-10 h-10 ${mode.color} rounded-full flex items-center justify-center`}>
                  <mode.icon size={20} className="text-white" />
                </div>
                <div className="flex-1">
                  <p className="font-medium text-gray-800">{mode.label}</p>
                  <p className="text-xs text-gray-500">{mode.description}</p>
                </div>
                <div
                  className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                    formData.trade_mode === mode.value
                      ? 'border-purple-500 bg-purple-500'
                      : 'border-gray-300'
                  }`}
                >
                  {formData.trade_mode === mode.value && (
                    <div className="w-2 h-2 bg-white rounded-full" />
                  )}
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* 투자금액 설정 */}
        <div className="bg-white rounded-xl p-4 shadow-sm">
          <h3 className="font-bold text-gray-800 mb-3 flex items-center gap-2">
            <DollarSign size={18} className="text-green-600" />
            투자금액 설정
          </h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                최대 총 투자금액
              </label>
              <div className="relative">
                <input
                  type="number"
                  value={formData.max_investment}
                  onChange={(e) =>
                    setFormData({ ...formData, max_investment: parseInt(e.target.value) || 0 })
                  }
                  min={0}
                  step={100000}
                  className="w-full px-3 py-2 pr-10 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500">원</span>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                현재: {formData.max_investment?.toLocaleString()}원
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                종목당 최대 투자금액
              </label>
              <div className="relative">
                <input
                  type="number"
                  value={formData.max_per_stock}
                  onChange={(e) =>
                    setFormData({ ...formData, max_per_stock: parseInt(e.target.value) || 0 })
                  }
                  min={0}
                  step={50000}
                  className="w-full px-3 py-2 pr-10 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500">원</span>
              </div>
            </div>
          </div>
        </div>

        {/* 손절/익절 설정 */}
        <div className="bg-white rounded-xl p-4 shadow-sm">
          <h3 className="font-bold text-gray-800 mb-3 flex items-center gap-2">
            <TrendingDown size={18} className="text-blue-600" />
            손절/익절 설정
          </h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1 flex items-center gap-1">
                <TrendingDown size={14} className="text-blue-500" />
                손절 비율
              </label>
              <div className="relative">
                <input
                  type="number"
                  value={formData.stop_loss_rate}
                  onChange={(e) =>
                    setFormData({ ...formData, stop_loss_rate: parseFloat(e.target.value) || 0 })
                  }
                  min={0}
                  max={50}
                  step={0.5}
                  className="w-full px-3 py-2 pr-8 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500">%</span>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1 flex items-center gap-1">
                <TrendingUp size={14} className="text-red-500" />
                익절 비율
              </label>
              <div className="relative">
                <input
                  type="number"
                  value={formData.take_profit_rate}
                  onChange={(e) =>
                    setFormData({ ...formData, take_profit_rate: parseFloat(e.target.value) || 0 })
                  }
                  min={0}
                  max={100}
                  step={0.5}
                  className="w-full px-3 py-2 pr-8 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500">%</span>
              </div>
            </div>
          </div>
        </div>

        {/* 매매 시간 설정 */}
        <div className="bg-white rounded-xl p-4 shadow-sm">
          <h3 className="font-bold text-gray-800 mb-3 flex items-center gap-2">
            <Clock size={18} className="text-orange-600" />
            매매 시간 설정
          </h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">시작 시간</label>
              <input
                type="time"
                value={formData.trading_start_time}
                onChange={(e) => setFormData({ ...formData, trading_start_time: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">종료 시간</label>
              <input
                type="time"
                value={formData.trading_end_time}
                onChange={(e) => setFormData({ ...formData, trading_end_time: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
              />
            </div>
          </div>
          <p className="text-xs text-gray-500 mt-2">
            정규장: 09:00 ~ 15:30 / 장전 시간외: 08:30 ~ 09:00
          </p>
        </div>

        {/* 저장 버튼 */}
        <button
          type="submit"
          disabled={saveMutation.isLoading}
          className="w-full flex items-center justify-center gap-2 bg-purple-600 text-white py-3 rounded-xl font-medium hover:bg-purple-700 disabled:opacity-50 transition-colors"
        >
          <Save size={18} />
          {saveMutation.isLoading ? '저장 중...' : '설정 저장'}
        </button>
      </form>

      {/* 주의사항 */}
      <div className="bg-yellow-50 rounded-xl p-4 border border-yellow-200">
        <div className="flex items-start gap-2">
          <AlertCircle size={18} className="text-yellow-600 mt-0.5" />
          <div className="text-sm text-yellow-700">
            <p className="font-medium mb-1">주의사항</p>
            <ul className="space-y-1 text-yellow-600">
              <li>• 완전 자동 모드는 AI가 직접 매매를 실행합니다</li>
              <li>• 투자금액 한도를 넘지 않도록 설정해주세요</li>
              <li>• 손절/익절 비율은 리스크 관리에 중요합니다</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
