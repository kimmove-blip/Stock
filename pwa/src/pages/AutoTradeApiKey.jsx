import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { autoTradeAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import Loading from '../components/Loading';
import {
  Key,
  Eye,
  EyeOff,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Save,
  Trash2,
  ExternalLink,
} from 'lucide-react';

export default function AutoTradeApiKey() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [showSecret, setShowSecret] = useState(false);
  const [formData, setFormData] = useState({
    app_key: '',
    app_secret: '',
    account_number: '',
    account_product_code: '01',
    is_mock: true, // true: 모의투자, false: 실제투자
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

  // API 키 설정 조회
  const { data, isLoading } = useQuery({
    queryKey: ['autoTradeApiKey'],
    queryFn: () => autoTradeAPI.getApiKey().then((res) => res.data),
    onSuccess: (data) => {
      if (data) {
        setFormData({
          app_key: data.app_key || '',
          app_secret: '', // 보안상 시크릿은 표시하지 않음
          account_number: data.account_number || '',
          account_product_code: data.account_product_code || '01',
          is_mock: data.is_mock !== false, // 기본값 true (모의투자)
        });
      }
    },
  });

  // API 키 저장
  const saveMutation = useMutation({
    mutationFn: (data) => autoTradeAPI.saveApiKey(data),
    onSuccess: () => {
      queryClient.invalidateQueries(['autoTradeApiKey']);
      alert('API 키가 저장되었습니다.');
    },
    onError: (error) => {
      alert(error.response?.data?.detail || 'API 키 저장에 실패했습니다.');
    },
  });

  // API 키 삭제
  const deleteMutation = useMutation({
    mutationFn: () => autoTradeAPI.deleteApiKey(),
    onSuccess: () => {
      queryClient.invalidateQueries(['autoTradeApiKey']);
      setFormData({
        app_key: '',
        app_secret: '',
        account_number: '',
        account_product_code: '01',
        is_mock: true,
      });
      alert('API 키가 삭제되었습니다.');
    },
    onError: (error) => {
      alert(error.response?.data?.detail || 'API 키 삭제에 실패했습니다.');
    },
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!formData.app_key || !formData.app_secret || !formData.account_number) {
      alert('모든 필수 항목을 입력해주세요.');
      return;
    }
    saveMutation.mutate(formData);
  };

  const handleDelete = () => {
    if (confirm('API 키를 삭제하시겠습니까? 자동매매 연동이 해제됩니다.')) {
      deleteMutation.mutate();
    }
  };

  if (isLoading) return <Loading text="API 키 설정 불러오는 중..." />;

  const isConnected = data?.is_connected;

  return (
    <div className="max-w-md mx-auto space-y-4">
      {/* 연동 상태 */}
      <div
        className={`rounded-xl p-4 ${
          isConnected
            ? data?.is_mock
              ? 'bg-blue-50 border border-blue-200'
              : 'bg-green-50 border border-green-200'
            : 'bg-gray-50 border border-gray-200'
        }`}
      >
        <div className="flex items-center gap-3">
          {isConnected ? (
            <>
              <CheckCircle2 size={24} className={data?.is_mock ? 'text-blue-600' : 'text-green-600'} />
              <div>
                <div className="flex items-center gap-2">
                  <p className={`font-bold ${data?.is_mock ? 'text-blue-700' : 'text-green-700'}`}>
                    API 연동됨
                  </p>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full ${
                      data?.is_mock
                        ? 'bg-blue-100 text-blue-600'
                        : 'bg-red-100 text-red-600'
                    }`}
                  >
                    {data?.is_mock ? '🎮 모의투자' : '💰 실제투자'}
                  </span>
                </div>
                <p className={`text-sm ${data?.is_mock ? 'text-blue-600' : 'text-green-600'}`}>
                  {data?.is_mock
                    ? '모의투자 계좌와 연동되었습니다'
                    : '실제투자 계좌와 연동되었습니다'}
                </p>
              </div>
            </>
          ) : (
            <>
              <XCircle size={24} className="text-gray-400" />
              <div>
                <p className="font-bold text-gray-700">미연동</p>
                <p className="text-sm text-gray-500">API 키를 입력하여 연동해주세요</p>
              </div>
            </>
          )}
        </div>
      </div>

      {/* API 키 발급 안내 */}
      <div className="bg-blue-50 rounded-xl p-4 border border-blue-200">
        <div className="flex items-start gap-3">
          <Key size={20} className="text-blue-600 mt-0.5" />
          <div className="flex-1">
            <p className="font-bold text-blue-700 mb-1">API 키 발급 방법</p>
            <ol className="text-sm text-blue-600 space-y-1 list-decimal list-inside">
              <li>한국투자증권 홈페이지 접속</li>
              <li>마이페이지 → Open API → KIS Developers 클릭</li>
              <li>API 신청하기 → 종합계좌 선택</li>
              <li>발급된 APP Key, Secret 입력</li>
            </ol>
            <a
              href="https://apiportal.koreainvestment.com"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-sm text-blue-700 font-medium mt-2 hover:underline"
            >
              KIS Developers 바로가기
              <ExternalLink size={14} />
            </a>
          </div>
        </div>
      </div>

      {/* API 키 입력 폼 */}
      <form onSubmit={handleSubmit} className="bg-white rounded-xl p-4 shadow-sm space-y-4">
        {/* 모의투자/실제투자 선택 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            투자 모드 선택 <span className="text-red-500">*</span>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setFormData({ ...formData, is_mock: true })}
              className={`p-3 rounded-lg border-2 transition-all ${
                formData.is_mock
                  ? 'border-blue-500 bg-blue-50 text-blue-700'
                  : 'border-gray-200 text-gray-600 hover:border-gray-300'
              }`}
            >
              <div className="text-center">
                <span className="text-2xl mb-1 block">🎮</span>
                <p className="font-medium">모의투자</p>
                <p className="text-xs text-gray-500">가상 자금으로 연습</p>
              </div>
            </button>
            <button
              type="button"
              onClick={() => setFormData({ ...formData, is_mock: false })}
              className={`p-3 rounded-lg border-2 transition-all ${
                !formData.is_mock
                  ? 'border-red-500 bg-red-50 text-red-700'
                  : 'border-gray-200 text-gray-600 hover:border-gray-300'
              }`}
            >
              <div className="text-center">
                <span className="text-2xl mb-1 block">💰</span>
                <p className="font-medium">실제투자</p>
                <p className="text-xs text-gray-500">실제 자금으로 매매</p>
              </div>
            </button>
          </div>
          {!formData.is_mock && (
            <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-xs text-red-600 font-medium">
                ⚠️ 실제투자 모드는 실제 자금으로 매매가 이루어집니다. 신중하게 선택해주세요.
              </p>
            </div>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            APP Key <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={formData.app_key}
            onChange={(e) => setFormData({ ...formData, app_key: e.target.value })}
            placeholder="발급받은 APP Key 입력"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            APP Secret <span className="text-red-500">*</span>
          </label>
          <div className="relative">
            <input
              type={showSecret ? 'text' : 'password'}
              value={formData.app_secret}
              onChange={(e) => setFormData({ ...formData, app_secret: e.target.value })}
              placeholder={isConnected ? '변경 시에만 입력' : '발급받은 APP Secret 입력'}
              className="w-full px-3 py-2 pr-10 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
            />
            <button
              type="button"
              onClick={() => setShowSecret(!showSecret)}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600"
            >
              {showSecret ? <EyeOff size={20} /> : <Eye size={20} />}
            </button>
          </div>
          {isConnected && (
            <p className="text-xs text-gray-500 mt-1">기존 Secret은 보안상 표시되지 않습니다</p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            계좌번호 <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={formData.account_number}
            onChange={(e) =>
              setFormData({ ...formData, account_number: e.target.value.replace(/[^0-9]/g, '') })
            }
            placeholder="계좌번호 (숫자만, 8자리)"
            maxLength={8}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">상품코드</label>
          <select
            value={formData.account_product_code}
            onChange={(e) => setFormData({ ...formData, account_product_code: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
          >
            <option value="01">01 (종합계좌)</option>
            <option value="02">02</option>
          </select>
        </div>

        <div className="flex gap-2 pt-2">
          <button
            type="submit"
            disabled={saveMutation.isLoading}
            className="flex-1 flex items-center justify-center gap-2 bg-purple-600 text-white py-3 rounded-lg font-medium hover:bg-purple-700 disabled:opacity-50 transition-colors"
          >
            <Save size={18} />
            {saveMutation.isLoading ? '저장 중...' : '저장'}
          </button>
          {isConnected && (
            <button
              type="button"
              onClick={handleDelete}
              disabled={deleteMutation.isLoading}
              className="flex items-center justify-center gap-2 px-4 py-3 bg-red-50 text-red-600 rounded-lg font-medium hover:bg-red-100 disabled:opacity-50 transition-colors"
            >
              <Trash2 size={18} />
            </button>
          )}
        </div>
      </form>

      {/* 주의사항 */}
      <div className="bg-yellow-50 rounded-xl p-4 border border-yellow-200">
        <div className="flex items-start gap-2">
          <AlertCircle size={18} className="text-yellow-600 mt-0.5" />
          <div className="text-sm text-yellow-700">
            <p className="font-medium mb-1">주의사항</p>
            <ul className="space-y-1 text-yellow-600">
              <li>• API 키는 암호화하여 안전하게 저장됩니다</li>
              <li>• 실거래용 API 키는 실제 매매가 이루어집니다</li>
              <li>• 모의투자용 API 키로 먼저 테스트를 권장합니다</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
