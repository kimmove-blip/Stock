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
  Plus,
  Trash2,
  Eye,
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

// 조건 문자열 파싱
const parseConditions = (str) => {
  if (!str) return [];
  const parts = str.split(/\s+(AND|OR)\s+/i);
  const conditions = [];
  let currentOperator = 'AND';

  for (let i = 0; i < parts.length; i++) {
    const part = parts[i].trim();
    if (part.toUpperCase() === 'AND' || part.toUpperCase() === 'OR') {
      currentOperator = part.toUpperCase();
    } else {
      const match = part.match(/^(V\d+)\s*(>=|<=|>|<|=)\s*(\d+)$/i);
      if (match) {
        conditions.push({
          score: match[1].toUpperCase(),
          operator: match[2],
          value: parseInt(match[3]),
          connector: currentOperator,
        });
      }
    }
  }
  return conditions;
};

// 조건 배열을 문자열로 변환
const conditionsToString = (conditions) => {
  if (!conditions || conditions.length === 0) return '';
  return conditions.map((c, i) => {
    const prefix = i > 0 ? ` ${c.connector} ` : '';
    return `${prefix}${c.score}${c.operator}${c.value}`;
  }).join('');
};

// 조건 빌더 컴포넌트
const ConditionBuilder = ({ conditions, onChange, disabled, label }) => {
  const scores = ['V1', 'V2', 'V4', 'V5'];
  const operators = ['>=', '<=', '>', '<'];

  const addCondition = () => {
    onChange([...conditions, { score: 'V1', operator: '>=', value: 60, connector: 'AND' }]);
  };

  const removeCondition = (index) => {
    onChange(conditions.filter((_, i) => i !== index));
  };

  const updateCondition = (index, field, value) => {
    const newConditions = [...conditions];
    newConditions[index] = { ...newConditions[index], [field]: value };
    onChange(newConditions);
  };

  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-gray-700">{label}</label>
      {conditions.map((cond, index) => (
        <div key={index} className="flex items-center gap-2 flex-wrap">
          {index > 0 && (
            <select
              value={cond.connector}
              onChange={(e) => updateCondition(index, 'connector', e.target.value)}
              disabled={disabled}
              className="px-2 py-1 border rounded text-xs font-medium bg-gray-100"
            >
              <option value="AND">AND</option>
              <option value="OR">OR</option>
            </select>
          )}
          <select
            value={cond.score}
            onChange={(e) => updateCondition(index, 'score', e.target.value)}
            disabled={disabled}
            className="px-2 py-1 border rounded text-sm"
          >
            {scores.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <select
            value={cond.operator}
            onChange={(e) => updateCondition(index, 'operator', e.target.value)}
            disabled={disabled}
            className="px-2 py-1 border rounded text-sm"
          >
            {operators.map((op) => (
              <option key={op} value={op}>{op}</option>
            ))}
          </select>
          <input
            type="number"
            value={cond.value}
            onChange={(e) => updateCondition(index, 'value', parseInt(e.target.value) || 0)}
            disabled={disabled}
            min={0}
            max={100}
            className="w-16 px-2 py-1 border rounded text-sm text-center"
          />
          <button
            type="button"
            onClick={() => removeCondition(index)}
            disabled={disabled || conditions.length <= 1}
            className="p-1 text-red-500 hover:bg-red-50 rounded disabled:opacity-30"
          >
            <Trash2 size={16} />
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={addCondition}
        disabled={disabled}
        className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 disabled:opacity-50"
      >
        <Plus size={14} /> 조건 추가
      </button>
    </div>
  );
};

// 미리보기 모달 컴포넌트
const PreviewModal = ({ isOpen, onClose, data, isLoading }) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl max-w-lg w-full max-h-[80vh] overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b">
          <h3 className="font-bold text-gray-800">조건 미리보기</h3>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded">
            <X size={20} />
          </button>
        </div>

        <div className="p-4 overflow-y-auto max-h-[60vh]">
          {isLoading ? (
            <div className="text-center py-8 text-gray-500">로딩 중...</div>
          ) : data ? (
            <div className="space-y-4">
              <p className="text-xs text-gray-500">기준: {data.csv_time}</p>

              {/* 매수 후보 */}
              {data.buy_conditions && (
                <div>
                  <h4 className="font-medium text-green-700 mb-2">
                    매수 후보 ({data.buy_total}개)
                  </h4>
                  <p className="text-xs text-gray-500 mb-2">{data.buy_conditions}</p>
                  {data.buy_candidates?.length > 0 ? (
                    <div className="space-y-1">
                      {data.buy_candidates.map((stock) => (
                        <div key={stock.code} className="flex items-center justify-between p-2 bg-green-50 rounded text-sm">
                          <div>
                            <span className="font-medium">{stock.name}</span>
                            <span className="text-gray-500 ml-2 text-xs">{stock.code}</span>
                          </div>
                          <div className="text-right">
                            <span className={stock.change_pct >= 0 ? 'text-red-600' : 'text-blue-600'}>
                              {stock.change_pct >= 0 ? '+' : ''}{stock.change_pct}%
                            </span>
                            <div className="text-xs text-gray-500">
                              V1:{stock.v1} V2:{stock.v2} V4:{stock.v4} V5:{stock.v5}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-gray-500 text-sm">조건 충족 종목 없음</p>
                  )}
                </div>
              )}

              {/* 매도 후보 */}
              {data.sell_conditions && (
                <div>
                  <h4 className="font-medium text-red-700 mb-2">
                    매도 대상 ({data.sell_total}개)
                  </h4>
                  <p className="text-xs text-gray-500 mb-2">{data.sell_conditions}</p>
                  {data.sell_candidates?.length > 0 ? (
                    <div className="space-y-1">
                      {data.sell_candidates.map((stock) => (
                        <div key={stock.code} className="flex items-center justify-between p-2 bg-red-50 rounded text-sm">
                          <div>
                            <span className="font-medium">{stock.name}</span>
                            <span className="text-gray-500 ml-2 text-xs">{stock.quantity}주</span>
                          </div>
                          <div className="text-right">
                            <span className={stock.profit_rate >= 0 ? 'text-red-600' : 'text-blue-600'}>
                              {stock.profit_rate >= 0 ? '+' : ''}{stock.profit_rate?.toFixed(1)}%
                            </span>
                            <div className="text-xs text-gray-500">
                              V1:{stock.v1} V2:{stock.v2} V4:{stock.v4} V5:{stock.v5}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-gray-500 text-sm">매도 대상 없음</p>
                  )}
                </div>
              )}
            </div>
          ) : (
            <p className="text-gray-500 text-center py-8">데이터 없음</p>
          )}
        </div>

        <div className="p-4 border-t">
          <button
            onClick={onClose}
            className="w-full py-2 bg-gray-200 rounded-lg font-medium hover:bg-gray-300"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
};

export default function AutoTradeSettings() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [formData, setFormData] = useState({
    trade_mode: 'manual',
    max_per_stock: 200000,
    stop_loss_rate: -7,
    trading_enabled: true,
    strategy: 'simple',
    score_version: 'v2',
    min_buy_score: 70,
    sell_score: 40,
  });

  // 다중 조건 상태
  const [buyConditions, setBuyConditions] = useState([
    { score: 'V2', operator: '>=', value: 70, connector: 'AND' }
  ]);
  const [sellConditions, setSellConditions] = useState([
    { score: 'V2', operator: '<=', value: 40, connector: 'AND' }
  ]);

  // 미리보기 상태
  const [showPreview, setShowPreview] = useState(false);
  const [previewData, setPreviewData] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // 설정 조회
  const { data, isLoading } = useQuery({
    queryKey: ['autoTradeSettings'],
    queryFn: () => autoTradeAPI.getSettings().then((res) => res.data),
    enabled: !!user?.auto_trade_enabled,
  });

  // 설정 데이터가 로드되면 폼에 반영
  useEffect(() => {
    if (data) {
      setFormData((prev) => ({ ...prev, ...data }));

      if (data.strategy === 'v1_composite') {
        setBuyConditions([
          { score: 'V1', operator: '>=', value: 60, connector: 'AND' },
          { score: 'V5', operator: '>=', value: 50, connector: 'AND' },
          { score: 'V4', operator: '>', value: 40, connector: 'AND' },
        ]);
        setSellConditions([
          { score: 'V4', operator: '<=', value: 30, connector: 'OR' },
          { score: 'V1', operator: '<=', value: 40, connector: 'OR' },
        ]);
      } else if (data.buy_conditions) {
        setBuyConditions(parseConditions(data.buy_conditions));
        setSellConditions(parseConditions(data.sell_conditions));
      } else {
        setBuyConditions([
          { score: data.score_version?.toUpperCase() || 'V2', operator: '>=', value: data.min_buy_score || 70, connector: 'AND' }
        ]);
        setSellConditions([
          { score: data.score_version?.toUpperCase() || 'V2', operator: '<=', value: data.sell_score || 40, connector: 'AND' }
        ]);
      }
    }
  }, [data]);

  // 미리보기 실행
  const handlePreview = async () => {
    setPreviewLoading(true);
    setShowPreview(true);

    try {
      const response = await autoTradeAPI.previewConditions({
        buy_conditions: conditionsToString(buyConditions),
        sell_conditions: conditionsToString(sellConditions),
      });
      setPreviewData(response.data);
    } catch (error) {
      console.error('Preview error:', error);
      setPreviewData(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  // 저장
  const saveMutation = useMutation({
    mutationFn: (data) => {
      const saveData = {
        ...data,
        buy_conditions: conditionsToString(buyConditions),
        sell_conditions: conditionsToString(sellConditions),
      };
      return autoTradeAPI.saveSettings(saveData);
    },
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

  const tradeModes = [
    { value: 'manual', label: '수동', icon: Settings, description: '알림만 받고 직접 매매', color: 'bg-gray-500' },
    { value: 'semi', label: '반자동', icon: HandMetal, description: '제안 승인 후 실행', color: 'bg-yellow-500' },
    { value: 'auto', label: '자동', icon: Bot, description: '즉시 매수 실행', color: 'bg-green-500' },
  ];

  if (isLoading) return <Loading text="설정 불러오는 중..." />;

  return (
    <div className="max-w-md mx-auto space-y-4 pb-8">
      {/* 자동매매 활성화 토글 */}
      <div className="bg-white rounded-xl p-4 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 ${formData.trading_enabled ? 'bg-green-500' : 'bg-gray-400'} rounded-full flex items-center justify-center`}>
              <Bot size={20} className="text-white" />
            </div>
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
        <div className={`bg-white rounded-xl p-4 shadow-sm ${!formData.trading_enabled ? 'opacity-50' : ''}`}>
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-gray-800 flex items-center gap-2">
              <Settings size={16} className="text-purple-600" />
              매매 모드
            </h3>
            <select
              value={formData.trade_mode}
              onChange={(e) => setFormData({ ...formData, trade_mode: e.target.value })}
              disabled={!formData.trading_enabled}
              className="bg-gray-100 px-3 py-1.5 border border-gray-300 rounded-lg text-xs font-medium"
            >
              {tradeModes.map((mode) => (
                <option key={mode.value} value={mode.value}>{mode.label}</option>
              ))}
            </select>
          </div>
          <p className="text-[10px] text-gray-500 mt-2">
            {tradeModes.find(m => m.value === formData.trade_mode)?.description}
          </p>
        </div>

        {/* 매매 조건 설정 */}
        <div className={`bg-white rounded-xl p-4 shadow-sm ${!formData.trading_enabled ? 'opacity-50' : ''}`}>
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-bold text-gray-800 flex items-center gap-2">
              <Target size={18} className="text-blue-600" />
              매매 조건
            </h3>
            <button
              type="button"
              onClick={handlePreview}
              disabled={!formData.trading_enabled}
              className="flex items-center gap-1 px-3 py-1.5 bg-blue-100 text-blue-700 rounded-lg text-xs font-medium hover:bg-blue-200 disabled:opacity-50"
            >
              <Eye size={14} />
              미리보기
            </button>
          </div>

          <div className="space-y-4">
            {/* 매수 조건 */}
            <div className="p-3 bg-green-50 rounded-lg border border-green-200">
              <ConditionBuilder
                conditions={buyConditions}
                onChange={setBuyConditions}
                disabled={!formData.trading_enabled}
                label="매수 조건"
              />
              <p className="text-xs text-green-600 mt-2">
                현재: {conditionsToString(buyConditions) || '없음'}
              </p>
            </div>

            {/* 매도 조건 */}
            <div className="p-3 bg-red-50 rounded-lg border border-red-200">
              <ConditionBuilder
                conditions={sellConditions}
                onChange={setSellConditions}
                disabled={!formData.trading_enabled}
                label="매도 조건"
              />
              <p className="text-xs text-red-600 mt-2">
                현재: {conditionsToString(sellConditions) || '없음'}
              </p>
            </div>

            {/* 손절률 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">손절률</label>
              <div className="bg-blue-50 rounded-xl p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-gray-500">-20%</span>
                  <span className="text-lg font-bold text-blue-600">{formData.stop_loss_rate}%</span>
                  <span className="text-xs text-gray-500">0%</span>
                </div>
                <input
                  type="range"
                  value={formData.stop_loss_rate}
                  onChange={(e) => setFormData({ ...formData, stop_loss_rate: parseInt(e.target.value) })}
                  disabled={!formData.trading_enabled}
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
          </div>
        </div>

        {/* 투자 설정 */}
        <div className={`bg-white rounded-xl p-4 shadow-sm ${!formData.trading_enabled ? 'opacity-50' : ''}`}>
          <h3 className="font-bold text-gray-800 mb-3 flex items-center gap-2">
            <DollarSign size={18} className="text-green-600" />
            투자 설정
          </h3>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">종목당 최대 금액</label>
            <div className="relative">
              <input
                type="text"
                value={formatNumber(formData.max_per_stock)}
                onChange={(e) => setFormData({ ...formData, max_per_stock: parseNumber(e.target.value) })}
                disabled={!formData.trading_enabled}
                className="w-full pl-4 pr-12 py-3 border border-gray-300 rounded-xl text-right text-lg disabled:bg-gray-100"
                placeholder="0"
              />
              <span className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 text-sm">원</span>
            </div>
            <p className="text-xs text-gray-500 mt-1">한 종목에 투자할 수 있는 최대 금액</p>
          </div>
        </div>

        {/* 저장 버튼 */}
        <button
          type="submit"
          disabled={saveMutation.isLoading}
          className="w-full flex items-center justify-center gap-2 bg-purple-600 text-white py-3 rounded-xl font-medium hover:bg-purple-700 disabled:opacity-50"
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
              <li>- AND: 모든 조건 충족 시 실행</li>
              <li>- OR: 하나라도 충족 시 실행</li>
              <li>- 손절률은 조건과 별도로 항상 적용</li>
            </ul>
          </div>
        </div>
      </div>

      {/* 미리보기 모달 */}
      <PreviewModal
        isOpen={showPreview}
        onClose={() => setShowPreview(false)}
        data={previewData}
        isLoading={previewLoading}
      />
    </div>
  );
}
