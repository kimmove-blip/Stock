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
  Target,
  ToggleLeft,
  ToggleRight,
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
    max_per_stock: 200000, // 종목당 최대 금액
    stop_loss_rate: -7, // 손절률 (-20 ~ 0%)
    min_buy_score: 70, // 최소 매수 점수 (50~100)
    sell_score: 40, // 매도 점수 (이 점수 이하면 매도)
    trading_enabled: true, // 자동매매 활성화
    initial_investment: 0, // 초기 투자금
    score_version: 'v5', // 스코어 버전 (v1, v2, v5)
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
      value: 'manual',
      label: '수동 (Manual)',
      icon: Settings,
      description: '알림만 받고 직접 매매',
      color: 'bg-gray-500',
    },
    {
      value: 'semi',
      label: '반자동 (Semi-Auto)',
      icon: HandMetal,
      description: '제안 승인 후 실행',
      color: 'bg-yellow-500',
    },
    {
      value: 'auto',
      label: '자동 (Auto)',
      icon: Bot,
      description: '즉시 매수 실행',
      color: 'bg-green-500',
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
        {/* 매매 모드 선택 (드롭다운) */}
        <div className={`bg-white rounded-xl p-4 shadow-sm ${!formData.trading_enabled ? 'opacity-50' : ''}`}>
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-gray-800 flex items-center gap-2">
              <Settings size={16} className="text-purple-600" />
              매매 모드
            </h3>
            <div className="relative">
              <select
                value={formData.trade_mode}
                onChange={(e) => setFormData({ ...formData, trade_mode: e.target.value })}
                disabled={!formData.trading_enabled}
                className="appearance-none bg-gray-100 px-3 py-1.5 pr-8 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-gray-800 text-xs font-medium cursor-pointer disabled:cursor-not-allowed"
              >
                {tradeModes.map((mode) => (
                  <option key={mode.value} value={mode.value}>
                    {mode.label}
                  </option>
                ))}
              </select>
              <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
                <svg className="h-4 w-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </div>
            </div>
          </div>
          <p className="text-[10px] text-gray-500 mt-2">
            {formData.trade_mode === 'manual' && '알림만 받고 직접 매매'}
            {formData.trade_mode === 'semi' && '매수 제안 승인 후 실행'}
            {formData.trade_mode === 'auto' && '조건 충족 시 즉시 매수'}
          </p>
        </div>

        {/* 매매 기준 설정 */}
        <div className={`bg-white rounded-xl p-4 shadow-sm ${!formData.trading_enabled ? 'opacity-50' : ''}`}>
            <h3 className="font-bold text-gray-800 mb-3 flex items-center gap-2">
              <Target size={18} className="text-blue-600" />
              매매 기준
            </h3>
            <div className="space-y-4">
              {/* 스코어 버전 선택 */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  스코어 엔진
                </label>
                <div className="grid grid-cols-4 gap-2">
                  {[
                    { value: 'v1', label: 'V1', desc: '종합 기술' },
                    { value: 'v2', label: 'V2', desc: '추세 추종' },
                    { value: 'v4', label: 'V4', desc: '스나이퍼' },
                    { value: 'v5', label: 'V5', desc: '장대양봉' },
                  ].map((version) => (
                    <button
                      key={version.value}
                      type="button"
                      onClick={() => setFormData({ ...formData, score_version: version.value })}
                      disabled={!formData.trading_enabled}
                      className={`p-3 rounded-lg border-2 text-center transition-all disabled:cursor-not-allowed ${
                        formData.score_version === version.value
                          ? 'border-purple-500 bg-purple-50'
                          : 'border-gray-200 hover:border-gray-300'
                      }`}
                    >
                      <p className={`font-bold ${formData.score_version === version.value ? 'text-purple-600' : 'text-gray-800'}`}>
                        {version.label}
                      </p>
                      <p className="text-xs text-gray-500">{version.desc}</p>
                    </button>
                  ))}
                </div>
                <p className="text-xs text-gray-500 mt-1">V5 장대양봉 전략 권장 (승률 67%)</p>
              </div>
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
                    disabled={!formData.trading_enabled}
                    min={-20}
                    max={0}
                    className="w-full h-3 bg-blue-200 rounded-full appearance-none cursor-pointer disabled:cursor-not-allowed
                      [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-6 [&::-webkit-slider-thumb]:h-6
                      [&::-webkit-slider-thumb]:bg-blue-600 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:shadow-lg
                      [&::-webkit-slider-thumb]:border-4 [&::-webkit-slider-thumb]:border-white"
                  />
                </div>
                <p className="text-xs text-gray-500 mt-1">예: -7% = 7% 손실시 자동 매도</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  매매 점수 범위
                </label>
                <div className="bg-gray-50 rounded-xl p-4">
                  {/* 점수 표시 */}
                  <div className="flex items-center justify-between mb-3">
                    <div className="text-center">
                      <span className="text-xs text-gray-500 block">매도</span>
                      <span className="text-lg font-bold text-red-600">{formData.sell_score}점</span>
                    </div>
                    <div className="flex-1 text-center">
                      <span className="text-xs text-gray-400">이하 매도 ← → 이상 매수</span>
                    </div>
                    <div className="text-center">
                      <span className="text-xs text-gray-500 block">매수</span>
                      <span className="text-lg font-bold text-green-600">{formData.min_buy_score}점</span>
                    </div>
                  </div>
                  {/* 듀얼 레인지 슬라이더 */}
                  <div className="relative h-3 mt-4">
                    {/* 배경 트랙 */}
                    <div className="absolute w-full h-3 bg-gray-200 rounded-full" />
                    {/* 활성 영역 (매도~매수 사이) */}
                    <div
                      className="absolute h-3 bg-gradient-to-r from-red-300 via-yellow-200 to-green-300 rounded-full"
                      style={{
                        left: `${formData.sell_score}%`,
                        width: `${formData.min_buy_score - formData.sell_score}%`
                      }}
                    />
                    {/* 매도 점수 슬라이더 (0~100, 실제 조작은 0~50) */}
                    <input
                      type="range"
                      value={formData.sell_score}
                      onChange={(e) => {
                        const val = parseInt(e.target.value);
                        if (val <= 50 && val < formData.min_buy_score - 10) {
                          setFormData({ ...formData, sell_score: val });
                        }
                      }}
                      disabled={!formData.trading_enabled}
                      min={0}
                      max={100}
                      className="absolute w-full h-3 appearance-none bg-transparent pointer-events-auto cursor-pointer disabled:cursor-not-allowed
                        [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-6 [&::-webkit-slider-thumb]:h-6
                        [&::-webkit-slider-thumb]:bg-red-500 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:shadow-lg
                        [&::-webkit-slider-thumb]:border-4 [&::-webkit-slider-thumb]:border-white [&::-webkit-slider-thumb]:relative [&::-webkit-slider-thumb]:z-20"
                    />
                    {/* 매수 점수 슬라이더 (0~100, 실제 조작은 50~100) */}
                    <input
                      type="range"
                      value={formData.min_buy_score}
                      onChange={(e) => {
                        const val = parseInt(e.target.value);
                        if (val >= 50 && val > formData.sell_score + 10) {
                          setFormData({ ...formData, min_buy_score: val });
                        }
                      }}
                      disabled={!formData.trading_enabled}
                      min={0}
                      max={100}
                      className="absolute w-full h-3 appearance-none bg-transparent pointer-events-auto cursor-pointer disabled:cursor-not-allowed
                        [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-6 [&::-webkit-slider-thumb]:h-6
                        [&::-webkit-slider-thumb]:bg-green-500 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:shadow-lg
                        [&::-webkit-slider-thumb]:border-4 [&::-webkit-slider-thumb]:border-white [&::-webkit-slider-thumb]:relative [&::-webkit-slider-thumb]:z-20"
                    />
                  </div>
                  {/* 눈금 */}
                  <div className="flex justify-between mt-2 text-xs text-gray-400">
                    <span>0</span>
                    <span>25</span>
                    <span>50</span>
                    <span>75</span>
                    <span>100</span>
                  </div>
                </div>
                <p className="text-xs text-gray-500 mt-1">매도점수 이하면 매도, 매수점수 이상이면 매수 제안</p>
              </div>
            </div>
          </div>

        {/* 투자 설정 */}
        <div className={`bg-white rounded-xl p-4 shadow-sm ${!formData.trading_enabled ? 'opacity-50' : ''}`}>
          <h3 className="font-bold text-gray-800 mb-3 flex items-center gap-2">
            <DollarSign size={18} className="text-green-600" />
            투자 설정
          </h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                종목당 최대 금액
              </label>
              <div className="relative">
                <input
                  type="text"
                  value={formatNumber(formData.max_per_stock)}
                  onChange={(e) => {
                    const value = parseNumber(e.target.value);
                    setFormData({ ...formData, max_per_stock: value });
                  }}
                  disabled={!formData.trading_enabled}
                  className="w-full pl-4 pr-12 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-green-500 focus:border-transparent text-right text-lg disabled:bg-gray-100 disabled:cursor-not-allowed"
                  placeholder="0"
                />
                <span className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 text-sm">원</span>
              </div>
              <p className="text-xs text-gray-500 mt-1">한 종목에 투자할 수 있는 최대 금액</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                초기 투자금
              </label>
              <div className="relative">
                <input
                  type="text"
                  value={formatNumber(formData.initial_investment)}
                  onChange={(e) => {
                    const value = parseNumber(e.target.value);
                    setFormData({ ...formData, initial_investment: value });
                  }}
                  disabled={!formData.trading_enabled}
                  className="w-full pl-4 pr-12 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-green-500 focus:border-transparent text-right text-lg disabled:bg-gray-100 disabled:cursor-not-allowed"
                  placeholder="0"
                />
                <span className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 text-sm">원</span>
              </div>
              <p className="text-xs text-gray-500 mt-1">수익률 계산 기준 금액</p>
            </div>
          </div>
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
              <li>- 자동 모드는 AI가 직접 매매를 실행합니다</li>
              <li>- 손절률은 리스크 관리에 중요합니다</li>
              <li>- 매수 점수가 높을수록 신호가 엄격해집니다</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
