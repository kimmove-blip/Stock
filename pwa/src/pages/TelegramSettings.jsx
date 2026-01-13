import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { MessageCircle, Send, CheckCircle, AlertCircle, ExternalLink, Copy, Check } from 'lucide-react';
import { telegramAPI } from '../api/client';

const BOT_USERNAME = 'Stock_Screening_Bot'; // 봇 유저네임

export default function TelegramSettings() {
  const queryClient = useQueryClient();
  const [chatId, setChatId] = useState('');
  const [copied, setCopied] = useState(false);

  // 현재 설정 조회
  const { data: settings, isLoading } = useQuery({
    queryKey: ['telegram-settings'],
    queryFn: () => telegramAPI.getSettings().then((res) => res.data),
  });

  useEffect(() => {
    if (settings?.chat_id) {
      setChatId(settings.chat_id);
    }
  }, [settings]);

  // 검증 및 저장
  const verifyMutation = useMutation({
    mutationFn: (chatId) => telegramAPI.verify(chatId),
    onSuccess: () => {
      queryClient.invalidateQueries(['telegram-settings']);
      alert('텔레그램이 연동되었습니다!');
    },
    onError: (error) => {
      alert(error.response?.data?.detail || '연동에 실패했습니다');
    },
  });

  // 테스트 메시지
  const testMutation = useMutation({
    mutationFn: (chatId) => telegramAPI.test(chatId),
    onSuccess: () => {
      alert('테스트 메시지가 전송되었습니다');
    },
    onError: (error) => {
      alert(error.response?.data?.detail || '전송에 실패했습니다');
    },
  });

  // 알림 토글
  const toggleMutation = useMutation({
    mutationFn: (enabled) => telegramAPI.updateSettings({ alerts_enabled: enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries(['telegram-settings']);
    },
  });

  const handleVerify = () => {
    if (!chatId.trim()) {
      alert('Chat ID를 입력해주세요');
      return;
    }
    verifyMutation.mutate(chatId.trim());
  };

  const handleTest = () => {
    if (!chatId.trim()) {
      alert('Chat ID를 입력해주세요');
      return;
    }
    testMutation.mutate(chatId.trim());
  };

  const handleCopyBotLink = () => {
    navigator.clipboard.writeText(`https://t.me/${BOT_USERNAME}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (isLoading) {
    return (
      <div className="flex justify-center items-center py-20">
        <span className="loading loading-spinner loading-lg text-purple-600"></span>
      </div>
    );
  }

  return (
    <div className="max-w-md mx-auto">
      {/* 헤더 카드 */}
      <div className="bg-gradient-to-r from-blue-500 to-cyan-500 rounded-xl p-6 text-white mb-6">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-12 h-12 bg-white/20 rounded-full flex items-center justify-center">
            <MessageCircle size={24} />
          </div>
          <div>
            <h2 className="font-bold text-lg">텔레그램 알림</h2>
            <p className="text-sm opacity-80">실시간 주식 알림 받기</p>
          </div>
        </div>

        {settings?.is_verified ? (
          <div className="flex items-center gap-2 bg-white/20 rounded-lg px-3 py-2">
            <CheckCircle size={18} />
            <span className="text-sm">연동됨</span>
          </div>
        ) : (
          <div className="flex items-center gap-2 bg-white/20 rounded-lg px-3 py-2">
            <AlertCircle size={18} />
            <span className="text-sm">연동 필요</span>
          </div>
        )}
      </div>

      {/* 연동 가이드 */}
      <div className="bg-white rounded-xl shadow-sm p-4 mb-4">
        <h3 className="font-bold text-gray-800 mb-4">연동 방법</h3>

        <div className="space-y-4">
          {/* Step 1 */}
          <div className="flex gap-3">
            <div className="w-6 h-6 bg-purple-600 text-white rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0">
              1
            </div>
            <div className="flex-1">
              <p className="text-gray-700 mb-2">텔레그램 봇에게 메시지 보내기</p>
              <button
                onClick={() => window.open(`https://t.me/${BOT_USERNAME}`, '_blank')}
                className="btn btn-sm btn-outline btn-primary gap-2"
              >
                <ExternalLink size={14} />
                봇 채팅 열기
              </button>
              <button
                onClick={handleCopyBotLink}
                className="btn btn-sm btn-ghost gap-2 ml-2"
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
                {copied ? '복사됨' : '링크 복사'}
              </button>
            </div>
          </div>

          {/* Step 2 */}
          <div className="flex gap-3">
            <div className="w-6 h-6 bg-purple-600 text-white rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0">
              2
            </div>
            <div className="flex-1">
              <p className="text-gray-700 mb-2">
                봇에게 <code className="bg-gray-100 px-1 rounded">/start</code> 메시지 전송
              </p>
              <p className="text-xs text-gray-500">봇이 Chat ID를 알려줍니다</p>
            </div>
          </div>

          {/* Step 3 */}
          <div className="flex gap-3">
            <div className="w-6 h-6 bg-purple-600 text-white rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0">
              3
            </div>
            <div className="flex-1">
              <p className="text-gray-700 mb-2">Chat ID 입력 후 연동</p>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={chatId}
                  onChange={(e) => setChatId(e.target.value)}
                  placeholder="Chat ID 입력"
                  className="input input-bordered input-sm flex-1"
                />
                <button
                  onClick={handleVerify}
                  disabled={verifyMutation.isPending}
                  className="btn btn-sm btn-primary"
                >
                  {verifyMutation.isPending ? (
                    <span className="loading loading-spinner loading-xs"></span>
                  ) : (
                    '연동'
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 알림 설정 */}
      {settings?.is_verified && (
        <div className="bg-white rounded-xl shadow-sm p-4 mb-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-bold text-gray-800">알림 받기</h3>
              <p className="text-sm text-gray-500">하락/매도 신호 알림</p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={settings?.alerts_enabled || false}
                onChange={(e) => toggleMutation.mutate(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-purple-600"></div>
            </label>
          </div>
        </div>
      )}

      {/* 테스트 버튼 */}
      {settings?.chat_id && (
        <div className="bg-white rounded-xl shadow-sm p-4 mb-4">
          <button
            onClick={handleTest}
            disabled={testMutation.isPending}
            className="btn btn-outline btn-primary w-full gap-2"
          >
            {testMutation.isPending ? (
              <span className="loading loading-spinner loading-xs"></span>
            ) : (
              <Send size={16} />
            )}
            테스트 메시지 보내기
          </button>
        </div>
      )}

      {/* 알림 종류 안내 */}
      <div className="bg-gray-50 rounded-xl p-4">
        <h3 className="font-bold text-gray-700 mb-3">받을 수 있는 알림</h3>
        <ul className="space-y-2 text-sm text-gray-600">
          <li className="flex items-center gap-2">
            <span className="text-red-500">1</span>
            보유종목 손실률 -10% 이상
          </li>
          <li className="flex items-center gap-2">
            <span className="text-orange-500">2</span>
            매도 신호 감지 (데드크로스 등)
          </li>
          <li className="flex items-center gap-2">
            <span className="text-yellow-500">3</span>
            하락 위험 징후 감지
          </li>
        </ul>
      </div>
    </div>
  );
}
