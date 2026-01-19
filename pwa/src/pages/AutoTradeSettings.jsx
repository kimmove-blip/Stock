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
  Target,
  Clock,
  ToggleLeft,
  ToggleRight,
  Layers,
  Calendar,
  Activity,
} from 'lucide-react';

// 숫자를 콤마 포맷으로 변환
const formatNumber = (num) => {
  if (num === '' || num === null || num === undefined) return '';
  return Number(num).toLocaleString('ko-KR');
};

// 콤마 포맷 문자열을 숫자로 변환
const parseNumber = (str) => {
  if (!str) return 0;
  return parseInt(str.replace(/,/g, '')) || 0;
};

export default function AutoTradeSettings() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [formData, setFormData] = useState({
    trade_mode: 'manual', // auto: 완전자동, semi: 반자동(승인필요), manual: 수동
    max_investment: 1000000, // 최대 투자금액
    stock_ratio: 5, // 종목당 투자비율 (1~20%)
    stop_loss_rate: -7, // 손절률 (-20 ~ 0%)
    min_buy_score: 70, // 최소 매수 점수 (50~100)
    sell_score: 40, // 매도 점수 (이 점수 이하면 매도)
    max_holdings: 10, // 최대 보유 종목 (1~20)
    max_daily_trades: 10, // 일일 최대 거래 (1~50)
    max_holding_days: 14, // 최대 보유 기간 (1~30일)
    trading_enabled: true, // 자동매매 활성화
    trading_start_time: '09:00', // 매매 시작 시간
    trading_end_time: '15:20', // 매매 종료 시간
    initial_investment: 0, // 초기 투자금
  });

  // 설정 조회 (훅은 항상 최상위에서 호출)
  const { data, isLoading } = useQuery({
    queryKey: ['autoTradeSettings'],
    queryFn: () => autoTradeAPI.getSettings().then((res) => res.data),
    enabled: !!user?.auto_trade_enabled, // 권한 있을 때만 조회
  });

  // 설정 데이터가 로드되면 폼에 반영
  useEffect(() => {
    if (data) {
      setFormData((prev) => ({ ...prev, ...data }));
    }
  }, [data]);

  // 설정 저장
  const saveMutation = useMutation({
    mutationFn: (formData) => autoTradeAPI.saveSettings(formData),
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

  // 자동매매 권한 체크 (훅 호출 이후에 조건부 반환)
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

  const tradeModes = [
    {
      value: 'auto',
      label: '자동매매 (Auto)',
      icon: Bot,
      description: '즉시 매수 실행',
      color: 'bg-green-500',
    },
    {
      value: 'semi',
      label: '반자동 (Semi-Auto)',
      icon: HandMetal,
      description: '제안 승인 후 실행',
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
    <div className="max-w-md mx-auto space-y-4 pb-8">
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

        {/* 투자 설정 */}
        <div className="bg-white rounded-xl p-4 shadow-sm">
          <h3 className="font-bold text-gray-800 mb-3 flex items-center gap-2">
            <DollarSign size={18} className="text-green-600" />
            투자 설정
          </h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                초기 투자금
              </label>
              <div className="relative">
                <input
                  type="text"
                  inputMode="numeric"
                  value={formatNumber(formData.initial_investment)}
                  onChange={(e) => {
                    const value = parseNumber(e.target.value);
                    setFormData({ ...formData, initial_investment: value });
                  }}
                  placeholder="0"
                  className="w-full px-3 py-2 pr-10 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-right"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500">원</span>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                성과분석에서 총수익률 계산에 사용됩니다
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                최대 투자금액
              </label>
              <div className="relative">
                <input
                  type="text"
                  inputMode="numeric"
                  value={formatNumber(formData.max_investment)}
                  onChange={(e) => {
                    const value = parseNumber(e.target.value);
                    setFormData({ ...formData, max_investment: value });
                  }}
                  placeholder="0"
                  className="w-full px-3 py-2 pr-10 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-right"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500">원</span>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                현재: {formatNumber(formData.max_investment)}원
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                종목당 투자비율
              </label>
              <div className="bg-gray-100 rounded-xl p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-gray-500">1%</span>
                  <span className="text-lg font-bold text-purple-600">{formData.stock_ratio}%</span>
                  <span className="text-xs text-gray-500">20%</span>
                </div>
                <input
                  type="range"
                  value={formData.stock_ratio}
                  onChange={(e) =>
                    setFormData({ ...formData, stock_ratio: parseInt(e.target.value) })
                  }
                  min={1}
                  max={20}
                  className="w-full h-3 bg-gray-300 rounded-full appearance-none cursor-pointer
                    [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-6 [&::-webkit-slider-thumb]:h-6
                    [&::-webkit-slider-thumb]:bg-purple-600 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:shadow-lg
                    [&::-webkit-slider-thumb]:border-4 [&::-webkit-slider-thumb]:border-white"
                />
              </div>
              <p className="text-xs text-gray-500 mt-1">예: 5% = 투자금의 5%씩 매수</p>
            </div>
          </div>
        </div>

        {/* 매매 기준 설정 */}
        <div className="bg-white rounded-xl p-4 shadow-sm">
          <h3 className="font-bold text-gray-800 mb-3 flex items-center gap-2">
            <Target size={18} className="text-blue-600" />
            매매 기준
          </h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                손절률
              </label>
              <div className="bg-blue-50 rounded-xl p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-gray-500">-20%</span>
                  <span className="text-lg font-bold text-blue-600">{formData.stop_loss_rate}%</span>
                  <span className="text-xs text-gray-500">0%</span>
                </div>
                <input
                  type="range"
                  value={formData.stop_loss_rate}
                  onChange={(e) =>
                    setFormData({ ...formData, stop_loss_rate: parseInt(e.target.value) })
                  }
                  min={-20}
                  max={0}
                  className="w-full h-3 bg-blue-200 rounded-full appearance-none cursor-pointer
                    [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-6 [&::-webkit-slider-thumb]:h-6
                    [&::-webkit-slider-thumb]:bg-blue-600 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:shadow-lg
                    [&::-webkit-slider-thumb]:border-4 [&::-webkit-slider-thumb]:border-white"
                />
              </div>
              <p className="text-xs text-gray-500 mt-1">예: -7% = 7% 손실시 자동 매도</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                최소 매수 점수
              </label>
              <div className="bg-green-50 rounded-xl p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-gray-500">50</span>
                  <span className="text-lg font-bold text-green-600">{formData.min_buy_score}점</span>
                  <span className="text-xs text-gray-500">100</span>
                </div>
                <input
                  type="range"
                  value={formData.min_buy_score}
                  onChange={(e) =>
                    setFormData({ ...formData, min_buy_score: parseInt(e.target.value) })
                  }
                  min={50}
                  max={100}
                  className="w-full h-3 bg-green-200 rounded-full appearance-none cursor-pointer
                    [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-6 [&::-webkit-slider-thumb]:h-6
                    [&::-webkit-slider-thumb]:bg-green-600 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:shadow-lg
                    [&::-webkit-slider-thumb]:border-4 [&::-webkit-slider-thumb]:border-white"
                />
              </div>
              <p className="text-xs text-gray-500 mt-1">높을수록 매수 기준이 엄격해집니다</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                매도 점수
              </label>
              <div className="bg-red-50 rounded-xl p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-gray-500">0</span>
                  <span className="text-lg font-bold text-red-600">{formData.sell_score}점</span>
                  <span className="text-xs text-gray-500">50</span>
                </div>
                <input
                  type="range"
                  value={formData.sell_score}
                  onChange={(e) =>
                    setFormData({ ...formData, sell_score: parseInt(e.target.value) })
                  }
                  min={0}
                  max={50}
                  className="w-full h-3 bg-red-200 rounded-full appearance-none cursor-pointer
                    [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-6 [&::-webkit-slider-thumb]:h-6
                    [&::-webkit-slider-thumb]:bg-red-600 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:shadow-lg
                    [&::-webkit-slider-thumb]:border-4 [&::-webkit-slider-thumb]:border-white"
                />
              </div>
              <p className="text-xs text-gray-500 mt-1">이 점수 이하로 떨어지면 매도 제안</p>
            </div>
          </div>
        </div>

        {/* 거래 제한 설정 */}
        <div className="bg-white rounded-xl p-4 shadow-sm">
          <h3 className="font-bold text-gray-800 mb-3 flex items-center gap-2">
            <Layers size={18} className="text-orange-600" />
            거래 제한
          </h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                최대 보유 종목
              </label>
              <div className="relative">
                <input
                  type="text"
                  inputMode="numeric"
                  value={formData.max_holdings || ''}
                  onChange={(e) => {
                    const val = parseInt(e.target.value) || 0;
                    setFormData({ ...formData, max_holdings: Math.min(Math.max(val, 0), 20) });
                  }}
                  onBlur={(e) => {
                    if (!formData.max_holdings || formData.max_holdings < 1) {
                      setFormData({ ...formData, max_holdings: 1 });
                    }
                  }}
                  placeholder="1"
                  className="w-full px-3 py-2 pr-8 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-center"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500">개</span>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                일일 최대 거래
              </label>
              <div className="relative">
                <input
                  type="text"
                  inputMode="numeric"
                  value={formData.max_daily_trades || ''}
                  onChange={(e) => {
                    const val = parseInt(e.target.value) || 0;
                    setFormData({ ...formData, max_daily_trades: Math.min(Math.max(val, 0), 50) });
                  }}
                  onBlur={(e) => {
                    if (!formData.max_daily_trades || formData.max_daily_trades < 1) {
                      setFormData({ ...formData, max_daily_trades: 1 });
                    }
                  }}
                  placeholder="1"
                  className="w-full px-3 py-2 pr-8 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-center"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500">회</span>
              </div>
            </div>
          </div>
          <div className="mt-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              최대 보유 기간
            </label>
            <div className="bg-orange-50 rounded-xl p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-500">1일</span>
                <div className="flex items-center gap-1">
                  <Calendar size={16} className="text-orange-600" />
                  <span className="text-lg font-bold text-orange-600">{formData.max_holding_days}일</span>
                </div>
                <span className="text-xs text-gray-500">30일</span>
              </div>
              <input
                type="range"
                value={formData.max_holding_days}
                onChange={(e) =>
                  setFormData({ ...formData, max_holding_days: parseInt(e.target.value) })
                }
                min={1}
                max={30}
                className="w-full h-3 bg-orange-200 rounded-full appearance-none cursor-pointer
                  [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-6 [&::-webkit-slider-thumb]:h-6
                  [&::-webkit-slider-thumb]:bg-orange-600 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:shadow-lg
                  [&::-webkit-slider-thumb]:border-4 [&::-webkit-slider-thumb]:border-white"
              />
            </div>
            <p className="text-xs text-gray-500 mt-1">이 기간 초과 시 매도 제안</p>
          </div>
        </div>

        {/* 매매 시간 설정 */}
        <div className="bg-white rounded-xl p-4 shadow-sm">
          <h3 className="font-bold text-gray-800 mb-3 flex items-center gap-2">
            <Clock size={18} className="text-indigo-600" />
            매매 시간
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
              <li>• 자동 모드는 AI가 직접 매매를 실행합니다</li>
              <li>• 손절률은 리스크 관리에 중요합니다</li>
              <li>• 매수 점수가 높을수록 신호가 엄격해집니다</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
