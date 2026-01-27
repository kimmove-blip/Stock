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
  Sparkles,
  Key,
  AlertTriangle,
  Check,
  X,
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
    trade_mode: 'manual', // auto: 완전자동, semi: 반자동(승인필요), manual: 수동, greenlight: AI자율
    max_per_stock: 200000, // 종목당 최대 금액
    stop_loss_rate: -7, // 손절률 (-20 ~ 0%)
    min_buy_score: 70, // 최소 매수 점수 (50~100)
    sell_score: 40, // 매도 점수 (이 점수 이하면 매도)
    trading_enabled: true, // 자동매매 활성화
    initial_investment: 0, // 초기 투자금
  });

  // LLM 설정 (Green Light 모드용)
  const [llmForm, setLLMForm] = useState({
    llm_provider: 'claude',
    llm_api_key: '',
    llm_model: '',
  });
  const [showLLMKey, setShowLLMKey] = useState(false);

  // 설정 조회 (훅은 항상 최상위에서 호출)
  const { data, isLoading } = useQuery({
    queryKey: ['autoTradeSettings'],
    queryFn: () => autoTradeAPI.getSettings().then((res) => res.data),
    enabled: !!user?.auto_trade_enabled, // 권한 있을 때만 조회
  });

  // LLM 설정 조회
  const { data: llmSettings } = useQuery({
    queryKey: ['llmSettings'],
    queryFn: () => autoTradeAPI.getLLMSettings().then((res) => res.data),
    enabled: !!user?.auto_trade_enabled,
  });

  // API 키 조회 (모의투자 여부 확인용)
  const { data: apiKeyData } = useQuery({
    queryKey: ['autoTradeApiKey'],
    queryFn: () => autoTradeAPI.getApiKey().then((res) => res.data),
    enabled: !!user?.auto_trade_enabled,
  });

  // 설정 데이터가 로드되면 폼에 반영
  useEffect(() => {
    if (data) {
      setFormData((prev) => ({ ...prev, ...data }));
    }
  }, [data]);

  // LLM 설정 데이터가 로드되면 폼에 반영
  useEffect(() => {
    if (llmSettings && llmSettings.is_configured) {
      setLLMForm((prev) => ({
        ...prev,
        llm_provider: llmSettings.llm_provider || 'claude',
        llm_model: llmSettings.llm_model || '',
      }));
    }
  }, [llmSettings]);

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

  // LLM 설정 저장
  const saveLLMMutation = useMutation({
    mutationFn: (data) => autoTradeAPI.saveLLMSettings(data),
    onSuccess: () => {
      queryClient.invalidateQueries(['llmSettings']);
      setLLMForm((prev) => ({ ...prev, llm_api_key: '' }));
      alert('LLM 설정이 저장되었습니다.');
    },
    onError: (error) => {
      alert(error.response?.data?.detail || 'LLM 설정 저장에 실패했습니다.');
    },
  });

  // LLM 설정 삭제
  const deleteLLMMutation = useMutation({
    mutationFn: () => autoTradeAPI.deleteLLMSettings(),
    onSuccess: () => {
      queryClient.invalidateQueries(['llmSettings']);
      setLLMForm({ llm_provider: 'claude', llm_api_key: '', llm_model: '' });
      alert('LLM 설정이 삭제되었습니다.');
    },
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    saveMutation.mutate(formData);
  };

  const handleLLMSubmit = (e) => {
    e.preventDefault();
    if (!llmForm.llm_api_key) {
      alert('API 키를 입력해주세요.');
      return;
    }
    saveLLMMutation.mutate(llmForm);
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
    {
      value: 'greenlight',
      label: '자율 (Green Light)',
      icon: Sparkles,
      description: 'AI가 모든 결정 (모의투자 전용)',
      color: 'bg-emerald-500',
      badge: 'BETA',
    },
  ];

  const llmProviders = [
    { value: 'claude', label: 'Claude (Anthropic)', description: '추천' },
    { value: 'openai', label: 'OpenAI (GPT)', description: '' },
    { value: 'gemini', label: 'Gemini (Google)', description: '' },
  ];

  // 모의투자 여부 확인
  const isMockAccount = apiKeyData?.is_mock !== false;

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
            {tradeModes.map((mode) => {
              // Green Light 모드는 모의투자에서만 선택 가능
              const isDisabled = mode.value === 'greenlight' && !isMockAccount;

              return (
                <label
                  key={mode.value}
                  className={`flex items-center gap-3 p-3 rounded-lg border-2 transition-all ${
                    isDisabled
                      ? 'cursor-not-allowed border-gray-200 bg-gray-50'
                      : 'cursor-pointer'
                  } ${
                    formData.trade_mode === mode.value && !isDisabled
                      ? 'border-purple-500 bg-purple-50'
                      : !isDisabled ? 'border-gray-200 hover:border-gray-300' : ''
                  }`}
                >
                  <input
                    type="radio"
                    name="trade_mode"
                    value={mode.value}
                    checked={formData.trade_mode === mode.value}
                    onChange={(e) => !isDisabled && setFormData({ ...formData, trade_mode: e.target.value })}
                    disabled={isDisabled}
                    className="hidden"
                  />
                  <div className={`w-10 h-10 ${mode.color} ${isDisabled ? 'opacity-50' : ''} rounded-full flex items-center justify-center`}>
                    <mode.icon size={20} className="text-white" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <p className={`font-medium ${isDisabled ? 'text-gray-400' : 'text-gray-800'}`}>{mode.label}</p>
                      {mode.badge && (
                        <span className={`px-1.5 py-0.5 text-[10px] rounded font-medium ${isDisabled ? 'bg-gray-100 text-gray-400' : 'bg-emerald-100 text-emerald-700'}`}>
                          {mode.badge}
                        </span>
                      )}
                    </div>
                    <p className={`text-xs ${isDisabled ? 'text-gray-400' : 'text-gray-500'}`}>{mode.description}</p>
                    {isDisabled && (
                      <p className="text-xs text-orange-500 mt-1">모의투자 계좌에서만 사용 가능</p>
                    )}
                  </div>
                  <div
                    className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                      formData.trade_mode === mode.value && !isDisabled
                        ? 'border-purple-500 bg-purple-500'
                        : 'border-gray-300'
                    }`}
                  >
                    {formData.trade_mode === mode.value && !isDisabled && (
                      <div className="w-2 h-2 bg-white rounded-full" />
                    )}
                  </div>
                </label>
              );
            })}
          </div>
        </div>

        {/* Green Light 모드 - LLM 설정 */}
        {formData.trade_mode === 'greenlight' && (
          <div className="bg-gradient-to-br from-emerald-50 to-teal-50 rounded-xl p-4 shadow-sm border border-emerald-200">
            <h3 className="font-bold text-gray-800 mb-3 flex items-center gap-2">
              <Sparkles size={18} className="text-emerald-600" />
              AI 엔진 설정
              {llmSettings?.is_configured && (
                <span className="ml-auto flex items-center gap-1 text-xs text-emerald-600">
                  <Check size={14} />
                  연결됨
                </span>
              )}
            </h3>

            {/* 경고 배너 */}
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-4">
              <div className="flex items-start gap-2">
                <AlertTriangle size={16} className="text-amber-600 mt-0.5 flex-shrink-0" />
                <div className="text-xs text-amber-700">
                  <p className="font-medium mb-1">Green Light 모드 안내</p>
                  <ul className="space-y-0.5 text-amber-600">
                    <li>- AI가 모든 매매 결정을 자율적으로 수행합니다</li>
                    <li>- 손절/익절 규칙 없이 AI가 직접 판단합니다</li>
                    <li>- 한 종목 집중투자(몰빵)가 가능합니다</li>
                    <li>- 모의투자 계좌에서만 사용 가능합니다</li>
                  </ul>
                </div>
              </div>
            </div>

            {/* LLM Provider 선택 */}
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  AI 엔진 선택
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {llmProviders.map((provider) => (
                    <button
                      key={provider.value}
                      type="button"
                      onClick={() => setLLMForm({ ...llmForm, llm_provider: provider.value })}
                      className={`p-2 rounded-lg border-2 transition-all text-center ${
                        llmForm.llm_provider === provider.value
                          ? 'border-emerald-500 bg-emerald-50'
                          : 'border-gray-200 hover:border-gray-300'
                      }`}
                    >
                      <p className="text-xs font-medium text-gray-800">{provider.label}</p>
                      {provider.description && (
                        <p className="text-[10px] text-emerald-600">{provider.description}</p>
                      )}
                    </button>
                  ))}
                </div>
              </div>

              {/* API Key 입력 */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  API Key
                </label>
                <div className="relative">
                  <input
                    type={showLLMKey ? 'text' : 'password'}
                    value={llmForm.llm_api_key}
                    onChange={(e) => setLLMForm({ ...llmForm, llm_api_key: e.target.value })}
                    placeholder={llmSettings?.is_configured ? '(저장됨) 변경하려면 새 키 입력' : 'API 키를 입력하세요'}
                    className="w-full px-3 py-2 pr-20 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-transparent text-sm"
                  />
                  <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => setShowLLMKey(!showLLMKey)}
                      className="p-1 text-gray-400 hover:text-gray-600"
                    >
                      <Key size={16} />
                    </button>
                  </div>
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  {llmForm.llm_provider === 'claude' && 'Anthropic Console에서 API 키를 발급받으세요'}
                  {llmForm.llm_provider === 'openai' && 'OpenAI Platform에서 API 키를 발급받으세요'}
                  {llmForm.llm_provider === 'gemini' && 'Google AI Studio에서 API 키를 발급받으세요'}
                </p>
              </div>

              {/* 모델 선택 (선택사항) */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  모델 (선택사항)
                </label>
                <input
                  type="text"
                  value={llmForm.llm_model}
                  onChange={(e) => setLLMForm({ ...llmForm, llm_model: e.target.value })}
                  placeholder="기본 모델 사용"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-transparent text-sm"
                />
                <p className="text-xs text-gray-500 mt-1">
                  비워두면 기본 모델 사용 (Claude: claude-sonnet-4-20250514, GPT: gpt-4o)
                </p>
              </div>

              {/* LLM 저장/삭제 버튼 */}
              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={handleLLMSubmit}
                  disabled={saveLLMMutation.isLoading}
                  className="flex-1 flex items-center justify-center gap-2 bg-emerald-600 text-white py-2 rounded-lg font-medium hover:bg-emerald-700 disabled:opacity-50 transition-colors text-sm"
                >
                  <Key size={16} />
                  {saveLLMMutation.isLoading ? '저장 중...' : 'LLM 설정 저장'}
                </button>
                {llmSettings?.is_configured && (
                  <button
                    type="button"
                    onClick={() => {
                      if (confirm('LLM 설정을 삭제하시겠습니까?')) {
                        deleteLLMMutation.mutate();
                      }
                    }}
                    disabled={deleteLLMMutation.isLoading}
                    className="px-4 py-2 border border-red-300 text-red-600 rounded-lg hover:bg-red-50 transition-colors text-sm"
                  >
                    <X size={16} />
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        {/* 투자 설정 (Green Light 모드가 아닐 때만 표시) */}
        {formData.trade_mode !== 'greenlight' && (
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
                  종목당 최대 금액
                </label>
                <div className="relative">
                  <input
                    type="text"
                    inputMode="numeric"
                    value={formatNumber(formData.max_per_stock)}
                    onChange={(e) => {
                      const value = parseNumber(e.target.value);
                      setFormData({ ...formData, max_per_stock: value });
                    }}
                    placeholder="200,000"
                    className="w-full px-3 py-2 pr-10 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-right"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500">원</span>
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  한 종목에 최대 {formatNumber(formData.max_per_stock)}원까지 매수
                </p>
              </div>
            </div>
          </div>
        )}

        {/* 매매 기준 설정 (Green Light 모드가 아닐 때만 표시) */}
        {formData.trade_mode !== 'greenlight' && (
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
        )}


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
              {formData.trade_mode === 'greenlight' ? (
                <>
                  <li>- Green Light 모드는 AI가 자율적으로 매매합니다</li>
                  <li>- 손절/익절 규칙이 없어 큰 손실이 발생할 수 있습니다</li>
                  <li>- 모의투자에서 충분히 테스트 후 사용하세요</li>
                  <li>- LLM API 호출 비용이 발생합니다</li>
                </>
              ) : (
                <>
                  <li>- 자동 모드는 AI가 직접 매매를 실행합니다</li>
                  <li>- 손절률은 리스크 관리에 중요합니다</li>
                  <li>- 매수 점수가 높을수록 신호가 엄격해집니다</li>
                </>
              )}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
